"""Tests — boucle de retour à l'agriculteur (ADR-0040, #558).

Le bot promet « reviens me voir, je te donnerai la réponse ». Ces tests vérifient
que la promesse est tenue **et** qu'elle l'est sans jamais ré-identifier personne.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.pii_utils import anonymize_user_id
from app.services import improvement_queue as iq
from app.services.chat._types import ChatResult
from app.services.chat.llm_guard import SOURCE_ESCALATED
from app.services.chat.pending_answers import SOURCE_RAPPEL, build_pending_answer

USER = "22541540178@s.whatsapp.net"
AUTRE = "22500000000@s.whatsapp.net"


def _poser(path, user=USER, excerpt="a combien vendre mon riz ?", statut=None):
    """Crée une tâche escaladée, éventuellement promue par l'atelier."""
    out = iq.enqueue_improvement_task(
        intent="QUESTION_VENTE", source=SOURCE_ESCALATED, cultures=["CULTURE_RIZ"],
        excerpt=excerpt, user_anon=anonymize_user_id(user), path=path,
    )
    tid = out["task"]["id"]
    if statut:
        iq.decide_task(tid, statut, path=path)
    return tid


async def _repond_corpus(_question):
    return ChatResult(response="Vois le prix a la cooperative.", city="Bouake",
                      language="both", meta={"source": "ivr_exact"})


async def _repond_accuse(_question):
    """Le moteur ne sait toujours pas répondre : il retombe sur l'accusé du garde."""
    return ChatResult(response="Bonne question. Je préfère ne pas…", city="Bouake",
                      language="both", meta={"source": SOURCE_ESCALATED})


@pytest.fixture
def file_tmp(tmp_path, monkeypatch):
    chemin = tmp_path / "tasks.jsonl"
    monkeypatch.setattr(iq, "DEFAULT_TASKS_PATH", str(chemin))
    return chemin


class TestSelectionDesTaches:
    def test_recherche_par_empreinte_jamais_par_numero(self, file_tmp):
        """Le sens direct (identifiant → empreinte) est le seul emprunté."""
        _poser(file_tmp, statut="production")
        trouve = iq.list_deliverables(anonymize_user_id(USER), path=file_tmp)
        assert len(trouve) == 1
        assert trouve[0]["user"].startswith("usr_")  # empreinte, pas un numéro

    def test_aucun_identifiant_whatsapp_stocke(self, file_tmp):
        _poser(file_tmp, statut="production")
        contenu = file_tmp.read_text(encoding="utf-8")
        assert "@s.whatsapp" not in contenu
        assert USER not in contenu

    def test_tache_non_validee_non_livrable(self, file_tmp):
        _poser(file_tmp)  # reste en bronze
        assert iq.list_deliverables(anonymize_user_id(USER), path=file_tmp) == []

    def test_cloisonnement_entre_agriculteurs(self, file_tmp):
        _poser(file_tmp, user=USER, statut="production")
        assert iq.list_deliverables(anonymize_user_id(AUTRE), path=file_tmp) == []

    def test_tache_deja_remise_non_relivrable(self, file_tmp):
        tid = _poser(file_tmp, statut="production")
        assert iq.mark_delivered(tid, path=file_tmp)["ok"] is True
        assert iq.list_deliverables(anonymize_user_id(USER), path=file_tmp) == []


class TestRemiseDeLaReponse:
    @pytest.mark.asyncio
    async def test_la_reponse_validee_est_remise_avec_rappel(self, file_tmp):
        _poser(file_tmp, statut="production")
        r = await build_pending_answer(user_id=USER, city="Bouake",
                                       include_audio=False, resolve=_repond_corpus)
        assert r is not None
        assert r.meta["source"] == SOURCE_RAPPEL
        assert "cooperative" in r.response          # la réponse validée
        assert "vendre mon riz" in r.response       # le rappel de la question

    @pytest.mark.asyncio
    async def test_rien_a_remettre_renvoie_none(self, file_tmp):
        """Cas de loin le plus fréquent : sortie immédiate, coût négligeable."""
        assert await build_pending_answer(user_id=USER, city="Bouake",
                                          include_audio=False,
                                          resolve=_repond_corpus) is None

    @pytest.mark.asyncio
    async def test_pas_de_repetition(self, file_tmp):
        _poser(file_tmp, statut="production")
        first = await build_pending_answer(user_id=USER, city="Bouake",
                                           include_audio=False, resolve=_repond_corpus)
        second = await build_pending_answer(user_id=USER, city="Bouake",
                                            include_audio=False, resolve=_repond_corpus)
        assert first is not None and second is None

    @pytest.mark.asyncio
    async def test_un_rejeu_qui_retombe_sur_l_accuse_ne_remet_RIEN(self, file_tmp):
        """Garde essentiel : la tâche est validée dans l'atelier, mais le moteur ne
        la sert toujours pas (cas du mode français, qui ne consulte pas le corpus).
        Sans ce garde, l'agriculteur recevrait « voici la réponse : je préfère ne pas
        te répondre au hasard », et le rejeu créerait une tâche à chaque passage."""
        tid = _poser(file_tmp, statut="production")
        r = await build_pending_answer(user_id=USER, city="Bouake",
                                       include_audio=False, resolve=_repond_accuse)
        assert r is None
        # ...et la tâche n'est PAS marquée : elle sera retentée plus tard.
        assert len(iq.list_deliverables(anonymize_user_id(USER), path=file_tmp)) == 1
        assert tid

    @pytest.mark.asyncio
    async def test_un_echec_de_rejeu_ne_casse_jamais_la_conversation(self, file_tmp):
        _poser(file_tmp, statut="production")

        async def _explose(_q):
            raise RuntimeError("cascade indisponible")

        assert await build_pending_answer(user_id=USER, city="Bouake",
                                          include_audio=False, resolve=_explose) is None

    @pytest.mark.asyncio
    async def test_desactivable_sans_redeploiement(self, file_tmp):
        _poser(file_tmp, statut="production")
        with patch("app.services.chat.pending_answers.enabled", return_value=False):
            assert await build_pending_answer(user_id=USER, city="Bouake",
                                              include_audio=False,
                                              resolve=_repond_corpus) is None

    @pytest.mark.asyncio
    async def test_sans_identifiant_aucune_recherche(self, file_tmp):
        assert await build_pending_answer(user_id=None, city="Bouake",
                                          include_audio=False,
                                          resolve=_repond_corpus) is None


class TestDefautsTrouvesParLaDemonstration:
    """Deux défauts révélés en jouant le cycle complet (2026-10-05)."""

    @pytest.mark.asyncio
    async def test_la_question_recitee_est_celle_de_l_agriculteur(self, file_tmp):
        """Défaut 1 — on recitait la version ENRICHIE par le NLU
        (« [Paysan cultive: riz] Comment et où vendre… »), illisible pour lui."""
        _poser(file_tmp, excerpt="a combien je peux vendre mon riz ?", statut="production")
        r = await build_pending_answer(user_id=USER, city="Bouake",
                                       include_audio=False, resolve=_repond_corpus)
        assert "a combien je peux vendre mon riz ?" in r.response
        assert "[Paysan cultive" not in r.response

    @pytest.mark.asyncio
    async def test_le_rejeu_ne_recree_pas_de_tache(self, file_tmp):
        """Défaut 2 — chaque retour de l'agriculteur dont la question n'est pas
        encore servie recréait une tâche : on escaladait la même question en boucle."""
        from app.services.chat.llm_guard import escalate
        from app.services.chat.nlu_preprocessor import NLUResult

        _poser(file_tmp, statut="production")
        avant = len(file_tmp.read_text(encoding="utf-8").splitlines())

        async def _rejeu_qui_escalade(_q):
            # Reproduit ce que fait la cascade pendant un rejeu : elle tente
            # d'escalader. Le drapeau de rejeu doit l'en empêcher.
            escalate(NLUResult(message_for_deepseek="x", intent="QUESTION_VENTE"),
                     "Bouake", USER, SOURCE_ESCALATED)
            return ChatResult(response="accusé", city="Bouake", language="both",
                              meta={"source": SOURCE_ESCALATED})

        await build_pending_answer(user_id=USER, city="Bouake",
                                   include_audio=False, resolve=_rejeu_qui_escalade)
        apres = len(file_tmp.read_text(encoding="utf-8").splitlines())
        assert apres == avant, "le rejeu a créé une tâche en doublon"

    def test_le_drapeau_de_rejeu_est_bien_restaure(self):
        """Hors rejeu, l'escalade doit redevenir active (sinon on perdrait
        définitivement la remontée préventive)."""
        from app.services.chat.llm_guard import (
            marquer_rejeu, rejeu_en_cours, restaurer_rejeu,
        )
        assert rejeu_en_cours() is False
        jeton = marquer_rejeu(True)
        assert rejeu_en_cours() is True
        restaurer_rejeu(jeton)
        assert rejeu_en_cours() is False
