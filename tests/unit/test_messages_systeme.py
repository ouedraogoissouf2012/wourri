"""Messages système d'une langue (ADR-0049) : lecture, dégradation, câblage du repli.

Le fil conducteur : **sans message validé, rien ne change**. C'est la condition pour
déployer ce mécanisme avant que le locuteur ait produit quoi que ce soit.
"""
import json

import pytest

from app.models.schemas import Language
from app.services import messages_systeme as msys
from app.services.chat import nlu_preprocessor
from app.services.chat.handlers import BaouleHandler

REPLI_BCI = {
    "version": "bci-test",
    "langue": "bci",
    "messages": {
        msys.REPLI: {
            "texte": "N timan ɔ ndɛ'n i wlɛ.",
            "texte_fr": "Je n'ai pas compris ta question.",
            "audio": "audio/ddd444.webm",
        }
    },
}


@pytest.fixture
def dossier(tmp_path, monkeypatch):
    """Isole les fichiers lus et vide le cache des deux côtés du test."""
    monkeypatch.setattr(msys, "DOSSIER", tmp_path)
    msys.vider_cache()
    yield tmp_path
    msys.vider_cache()


def _ecrire(dossier, langue, data):
    (dossier / f"messages_systeme_{langue}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


# --------------------------------------------------------------------- lecture


def test_sans_fichier_aucun_message(dossier):
    assert msys.message("bci", msys.REPLI) is None


def test_message_valide_est_lu(dossier):
    _ecrire(dossier, "bci", REPLI_BCI)
    m = msys.message("bci", msys.REPLI)
    assert m.texte == "N timan ɔ ndɛ'n i wlɛ."
    assert m.texte_fr == "Je n'ai pas compris ta question."
    assert m.audio == "audio/ddd444.webm"


def test_role_absent_du_fichier(dossier):
    _ecrire(dossier, "bci", REPLI_BCI)
    assert msys.message("bci", msys.SALUTATION) is None


def test_texte_vide_vaut_pas_de_message(dossier):
    """Mieux vaut le français qu'une réponse vide."""
    _ecrire(dossier, "bci", {"messages": {msys.REPLI: {"texte": "   ", "texte_fr": "x"}}})
    assert msys.message("bci", msys.REPLI) is None


def test_fichier_illisible_degrade_sans_lever(dossier, caplog):
    (dossier / "messages_systeme_bci.json").write_text("{ pas du json", encoding="utf-8")
    assert msys.message("bci", msys.REPLI) is None
    assert "illisible" in caplog.text


def test_une_langue_ne_voit_pas_les_messages_d_une_autre(dossier):
    """ADR-0046 : une tournure dioula n'est pas du baoulé."""
    _ecrire(dossier, "bci", REPLI_BCI)
    assert msys.message("dyu", msys.REPLI) is None


# --------------------------------------------------------------------- audio


def test_url_audio_suit_la_convention_du_serveur_voix(dossier):
    """Contrat avec `scripts/publier_audios.py` : il publie `<stem>.ogg`."""
    _ecrire(dossier, "bci", REPLI_BCI)
    m = msys.message("bci", msys.REPLI)
    assert msys.url_audio(m, "http://voix:8000/audio") == "http://voix:8000/audio/ddd444.ogg"
    assert msys.url_audio(m, "http://voix:8000/audio/") == "http://voix:8000/audio/ddd444.ogg"


def test_pas_d_url_sans_base_ni_sans_audio(dossier):
    _ecrire(dossier, "bci", REPLI_BCI)
    m = msys.message("bci", msys.REPLI)
    assert msys.url_audio(m, "") is None
    sans = msys.MessageSysteme(texte="x", texte_fr="y", audio=None)
    assert msys.url_audio(sans, "http://voix:8000/audio") is None


# --------------------------------------------------------------------- câblage


async def _repli(include_audio=True):
    nlu = nlu_preprocessor.preprocess_nlu("Mmo, a ti ?", None, Language.BAOULE)
    nlu.message_original = "Mmo, a ti ?"
    return await BaouleHandler().process(
        nlu, None, "Bouaké", include_audio, Language.BAOULE, "u1"
    )


@pytest.mark.asyncio
async def test_sans_message_valide_le_repli_ne_change_pas(dossier, monkeypatch):
    """La condition pour déployer avant que le locuteur ait produit : rien ne bouge."""
    monkeypatch.setattr("app.services.chat.llm_guard.escalate", lambda *a, **k: None)
    r = await _repli()
    assert r.response_local is None and r.audio_url is None
    assert "Je n'ai pas compris ta question" in r.response


@pytest.mark.asyncio
async def test_le_repli_valide_est_servi_en_texte_et_en_voix(dossier, monkeypatch):
    _ecrire(dossier, "bci", REPLI_BCI)
    monkeypatch.setattr("app.services.chat.llm_guard.escalate", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.bci_audio_base_url", "http://voix:8000/audio")
    r = await _repli()
    assert r.response_local == "N timan ɔ ndɛ'n i wlɛ."
    assert r.audio_url == "http://voix:8000/audio/ddd444.ogg"
    assert r.audio_language == "Baoulé"
    # Le français garde la liste des sujets, qui est calculée depuis le corpus.
    assert "Je peux t'aider sur" in r.response


@pytest.mark.asyncio
async def test_sans_audio_demande_pas_d_audio(dossier, monkeypatch):
    _ecrire(dossier, "bci", REPLI_BCI)
    monkeypatch.setattr("app.services.chat.llm_guard.escalate", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.bci_audio_base_url", "http://voix:8000/audio")
    r = await _repli(include_audio=False)
    assert r.response_local == "N timan ɔ ndɛ'n i wlɛ."
    assert r.audio_url is None


@pytest.mark.asyncio
async def test_message_sans_enregistrement_part_quand_meme_en_texte(dossier, monkeypatch):
    """Le texte validé vaut mieux que rien, même sans voix encore enregistrée."""
    _ecrire(dossier, "bci", {"messages": {msys.REPLI: {"texte": "N timan.", "texte_fr": "…"}}})
    monkeypatch.setattr("app.services.chat.llm_guard.escalate", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.bci_audio_base_url", "http://voix:8000/audio")
    r = await _repli()
    assert r.response_local == "N timan." and r.audio_url is None
