"""Tests — garde LLM : faits vérifiables + escalade préventive (ADR-0039, #550).

Le garde est le dernier filtre avant le LLM. Il doit :
  - INTERDIRE le LLM sur les familles à réponse vérifiable (météo/prix/date) ;
  - escalader la question dans tous les cas non couverts ;
  - ne JAMAIS casser la réponse si l'escalade échoue.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat.llm_guard import (
    ESCALATION_MESSAGE_FR,
    SOURCE_ESCALATED,
    build_escalation_response,
    escalate,
    factual_intents,
    guard_enabled,
    is_factual_intent,
)
from app.services.chat.nlu_preprocessor import NLUResult


def _nlu(intent=None, concepts=None) -> NLUResult:
    return NLUResult(
        message_for_deepseek="il va pleuvoir demain ?",
        intent=intent,
        concepts=concepts or {},
    )


class TestPerimetre:
    def test_familles_interdites_par_defaut(self):
        """Périmètre arbitré le 2026-09-24 : météo, prix de vente, date."""
        assert factual_intents() == {
            "QUESTION_METEO_AGRICOLE",
            "QUESTION_VENTE",
            "QUESTION_DATE",
        }

    @pytest.mark.parametrize(
        "intent",
        ["QUESTION_METEO_AGRICOLE", "QUESTION_VENTE", "QUESTION_DATE"],
    )
    def test_intents_factuels_bloquent_le_llm(self, intent):
        assert is_factual_intent(_nlu(intent)) is True

    @pytest.mark.parametrize(
        "intent",
        ["CONSEIL_PRODUCTION", "QUESTION_SAISON_PLANTATION", "QUESTION_CULTURE_ZONE", None],
    )
    def test_conseil_general_laisse_passer_le_llm(self, intent):
        """Le conseil agronomique reste servi par le LLM (option B de l'ADR-0039) :
        une coupure totale supprimerait ~40 % des réponses."""
        assert is_factual_intent(_nlu(intent)) is False

    def test_perimetre_externalise_et_ajustable(self):
        """La liste vit dans la config (constraints.md §1.2), pas en dur."""
        fake = MagicMock(llm_factual_intents="QUESTION_METEO_AGRICOLE, QUESTION_SAISON_PLANTATION")
        with patch("app.config.get_settings", return_value=fake):
            assert factual_intents() == {
                "QUESTION_METEO_AGRICOLE",
                "QUESTION_SAISON_PLANTATION",
            }

    def test_liste_vide_desactive_le_regime_factuel(self):
        fake = MagicMock(llm_factual_intents="")
        with patch("app.config.get_settings", return_value=fake):
            assert factual_intents() == frozenset()
            assert is_factual_intent(_nlu("QUESTION_METEO_AGRICOLE")) is False


class TestFlagDeRollback:
    def test_actif_par_defaut(self):
        assert guard_enabled() is True

    def test_desactivable_sans_redeploiement(self):
        fake = MagicMock(llm_guard_enabled=False)
        with patch("app.config.get_settings", return_value=fake):
            assert guard_enabled() is False

    def test_config_indisponible_garde_actif(self):
        """Dégradation sûre : si la config casse, on protège quand même."""
        with patch("app.config.get_settings", side_effect=RuntimeError("boom")):
            assert guard_enabled() is True


class TestEscalade:
    def test_escalade_cree_une_tache(self):
        with patch(
            "app.services.improvement_queue.enqueue_improvement_task"
        ) as mock_q, patch(
            "app.core.pii_utils.anonymize_user_id", return_value="anon-1"
        ):
            escalate(_nlu("QUESTION_METEO_AGRICOLE", {"TEMPS_SAISON_PLUIE": 1.0}),
                     "Bouake", "user-42", "escalated_factual")
        mock_q.assert_called_once()
        kw = mock_q.call_args.kwargs
        assert kw["intent"] == "QUESTION_METEO_AGRICOLE"
        assert kw["user_anon"] == "anon-1"
        assert kw["extra"]["city"] == "Bouake"

    def test_echec_escalade_ne_casse_jamais(self):
        """L'escalade est un effet de bord : son échec ne doit pas priver
        l'agriculteur de sa réponse."""
        with patch(
            "app.services.improvement_queue.enqueue_improvement_task",
            side_effect=RuntimeError("file indisponible"),
        ):
            escalate(_nlu("QUESTION_VENTE"), "Bouake", "u1", "escalated_factual")  # ne lève pas


class TestReponseAccusee:
    @pytest.mark.asyncio
    async def test_accuse_au_lieu_d_une_invention(self):
        with patch("app.services.chat.llm_guard.escalate") as mock_esc, patch(
            "app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)
        ):
            r = await build_escalation_response(
                _nlu("QUESTION_METEO_AGRICOLE"), "Bouake",
                include_audio=False, language=Language.BOTH, user_id="u1",
            )
        assert r is not None  # ne renvoie JAMAIS None : c'est le refus d'inventer
        assert r.response == ESCALATION_MESSAGE_FR
        assert r.meta["source"] == SOURCE_ESCALATED
        assert r.meta["intent"] == "QUESTION_METEO_AGRICOLE"
        mock_esc.assert_called_once()

    @pytest.mark.asyncio
    async def test_le_message_porte_la_promesse_d_expert(self):
        """Arbitrage Q1 de l'ADR-0039 (dette : boucle de retour à construire)."""
        assert "expert" in ESCALATION_MESSAGE_FR
        assert "réponse" in ESCALATION_MESSAGE_FR

    @pytest.mark.asyncio
    async def test_audio_francais_meme_en_both(self):
        """Dette dioula tracée (ADR-0014) : rendu en français, comme date_responder."""
        with patch("app.services.chat.llm_guard.escalate"), patch(
            "app.services.tts_french.synthesize_french",
            new=AsyncMock(return_value="/static/audio/esc.ogg"),
        ):
            r = await build_escalation_response(
                _nlu("QUESTION_DATE"), "Korhogo",
                include_audio=True, language=Language.BOTH, user_id=None,
            )
        assert r.audio_url == "/static/audio/esc.ogg"
        assert r.audio_language == "Français"

    @pytest.mark.asyncio
    async def test_texte_part_meme_sans_audio(self):
        """Un TTS en panne ne doit pas supprimer la réponse."""
        with patch("app.services.chat.llm_guard.escalate"), patch(
            "app.services.tts_french.synthesize_french",
            new=AsyncMock(side_effect=RuntimeError("tts down")),
        ):
            r = await build_escalation_response(
                _nlu("QUESTION_VENTE"), "Bouake",
                include_audio=True, language=Language.FRENCH, user_id="u1",
            )
        assert r.response == ESCALATION_MESSAGE_FR
        assert r.audio_url is None
