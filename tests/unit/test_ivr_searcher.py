"""
Tests pour `app/services/chat/ivr_searcher.py` (refactor P2-09 PR 4/5).

Couvre les 4 fonctions extraites de ChatService :
    - try_ivr_exact() : 4 branches (intent vide, VDB error, no result, success)
    - try_ivr_concept() : 3 branches (action sans culture → clarify, no result, success)
    - clarify_missing_culture() : cas nominal (message bilingue + audio TTS)
    - search_ivr_by_concept() : 4 branches (vide, no cultures, intent_candidat, fallback)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.ivr_searcher import (
    try_ivr_exact,
    try_ivr_concept,
    clarify_missing_culture,
    search_ivr_by_concept,
)
from app.services.chat.nlu_preprocessor import NLUResult


def _make_nlu(intent=None, concepts=None) -> NLUResult:
    """Helper de construction d'un NLUResult pour les tests."""
    return NLUResult(
        message_for_deepseek="msg",
        intent=intent,
        concepts=concepts or {},
    )


# ─────────────────────────────────────────────
# try_ivr_exact — 4 branches
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_try_ivr_exact_intent_vide_retourne_none():
    """Sans intent → return None immediat (pas d'appel corpus)."""
    nlu = _make_nlu(intent=None, concepts={"CULTURE_RIZ": True})
    result = await try_ivr_exact(nlu, "Abidjan", None, True, Language.DIOULA)
    assert result is None


@pytest.mark.asyncio
async def test_try_ivr_exact_vdb_exception_retourne_none():
    """Si corpus_facade leve, on log et retourne None."""
    nlu = _make_nlu(intent="QUESTION_SAISON_PLANTATION", concepts={"CULTURE_RIZ": True})
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        side_effect=RuntimeError("VDB casse"),
    ):
        result = await try_ivr_exact(nlu, "Abidjan", None, False, Language.DIOULA)
    assert result is None


@pytest.mark.asyncio
async def test_try_ivr_exact_pas_de_resultat_retourne_none():
    """Si corpus retourne None (pas de match) → return None."""
    nlu = _make_nlu(intent="X", concepts={})
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=None,
    ):
        result = await try_ivr_exact(nlu, "Abidjan", None, False, Language.DIOULA)
    assert result is None


@pytest.mark.asyncio
async def test_try_ivr_exact_succes_retourne_chat_result():
    """Cas nominal : corpus retourne entry → ChatResult construit."""
    nlu = _make_nlu(
        intent="QUESTION_SAISON_PLANTATION",
        concepts={"CULTURE_RIZ": True},
    )
    fake_entry = {
        "id": "riz_saison_001",
        "reponse_bambara": "Aw ye malo sɛnɛ ka di",
        "reponse_fr": "Plantez le riz tot",
    }
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=fake_entry,
    ), patch(
        "app.services.corpus_facade.get_phrases_for_intent",
        return_value=[],
    ), patch(
        "app.services.chat.ivr_searcher.get_conseil_saisonnier",
        return_value=None,
    ):
        result = await try_ivr_exact(nlu, "Abidjan", None, False, Language.DIOULA)

    assert isinstance(result, ChatResult)
    assert result.response == "Plantez le riz tot"
    assert result.response_dioula == "Aw ye malo sɛnɛ ka di"
    assert result.audio_url is None  # include_audio=False
    assert result.city == "Abidjan"
    assert result.meta["intent"] == "QUESTION_SAISON_PLANTATION"
    assert result.meta["source"] == "ivr_exact"
    assert result.meta["cultures"] == ["CULTURE_RIZ"]


@pytest.mark.asyncio
async def test_try_ivr_exact_inject_meteo_remplace_tags():
    """Si reponse contient `{{METEO_CONTEXTUEL}}` → remplace via meteo_injector."""
    nlu = _make_nlu(intent="X", concepts={"CULTURE_RIZ": True})
    fake_entry = {
        "id": "x",
        "reponse_bambara": "Texte: {{METEO_CONTEXTUEL}}",
        "reponse_fr": "Texte: {{METEO_FR}}",
    }
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=fake_entry,
    ), patch(
        "app.services.corpus_facade.get_phrases_for_intent",
        return_value=[],
    ), patch(
        "app.services.chat.ivr_searcher.get_conseil_saisonnier",
        return_value=None,
    ), patch(
        "app.data.calendrier_agricole.get_cultures_du_mois",
        return_value=None,
    ):
        result = await try_ivr_exact(nlu, "Abidjan", weather, False, Language.DIOULA)

    assert "{{METEO_CONTEXTUEL}}" not in result.response_dioula
    assert "{{METEO_FR}}" not in result.response


# ─────────────────────────────────────────────
# try_ivr_concept — 3 branches
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_try_ivr_concept_action_sans_culture_appelle_clarify():
    """Action agricole sans culture → clarify_missing_culture (fix #94)."""
    nlu = _make_nlu(intent=None, concepts={"ACTION_PLANTER": True})
    result = await try_ivr_concept(nlu, "Abidjan", False, Language.DIOULA)
    assert isinstance(result, ChatResult)
    assert result.meta["source"] == "clarification_culture"
    assert "ACTION_PLANTER" in result.meta["detected_actions"]


@pytest.mark.asyncio
async def test_try_ivr_concept_pas_de_resultat_retourne_none():
    """Si search_ivr_by_concept retourne None → None."""
    nlu = _make_nlu(
        intent=None,
        concepts={"CULTURE_INCONNU": True, "ACTION_PLANTER": True},
    )
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=None,
    ):
        result = await try_ivr_concept(nlu, "Abidjan", False, Language.DIOULA)
    assert result is None


@pytest.mark.asyncio
async def test_try_ivr_concept_succes_retourne_chat_result():
    """Cas nominal : corpus retourne entry → ChatResult construit."""
    nlu = _make_nlu(intent=None, concepts={"CULTURE_RIZ": True})
    fake_entry = {
        "id": "riz_xxx",
        "reponse_bambara": "Bam",
        "reponse_fr": "Fr",
    }
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=fake_entry,
    ):
        result = await try_ivr_concept(nlu, "Abidjan", False, Language.DIOULA)
    assert isinstance(result, ChatResult)
    assert result.response_dioula == "Bam"
    assert result.meta["source"] == "ivr_fallback"


# ─────────────────────────────────────────────
# clarify_missing_culture — cas nominal
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clarify_missing_culture_message_bilingue():
    """Cas nominal : message dyu + fr + meta source=clarification."""
    nlu = _make_nlu(intent=None, concepts={"ACTION_PLANTER": True})
    result = await clarify_missing_culture("Abidjan", False, Language.DIOULA, nlu)
    assert isinstance(result, ChatResult)
    assert "Malo, kaba" in result.response_dioula
    assert "De quelle culture" in result.response
    assert result.audio_url is None
    assert result.meta["source"] == "clarification_culture"
    assert "ACTION_PLANTER" in result.meta["detected_actions"]


# ─────────────────────────────────────────────
# search_ivr_by_concept — 4 branches
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_ivr_by_concept_vide_retourne_none():
    """Concepts vide → None immediat."""
    result = await search_ivr_by_concept({})
    assert result is None


@pytest.mark.asyncio
async def test_search_ivr_by_concept_no_cultures_retourne_none():
    """Concepts sans CULTURE_/ANIMAL_ → None (fix #94)."""
    result = await search_ivr_by_concept({"ACTION_PLANTER": True})
    assert result is None


@pytest.mark.asyncio
async def test_search_ivr_by_concept_intent_candidat_hit():
    """Action mappable → intent IVR correspondant trouve dans corpus."""
    concepts = {"CULTURE_RIZ": True, "ACTION_PLANTER": True}
    fake_entry = {
        "id": "riz_plant_001",
        "reponse_bambara": "Bam",
        "reponse_fr": "Fr",
    }
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=fake_entry,
    ):
        result = await search_ivr_by_concept(concepts)
    assert result == {"reponse_bambara": "Bam", "reponse_fr": "Fr"}


@pytest.mark.asyncio
async def test_search_ivr_by_concept_fallback_conseil_production():
    """Si intent_candidat n'a pas de match → fallback CONSEIL_PRODUCTION."""
    concepts = {"CULTURE_RIZ": True}  # pas d'action, pas d'intent_candidat
    fake_entry = {
        "id": "riz_conseil_001",
        "reponse_bambara": "Conseil",
        "reponse_fr": "Conseil FR",
    }
    with patch(
        "app.services.corpus_facade.chercher_reponse_ivr",
        return_value=fake_entry,
    ):
        result = await search_ivr_by_concept(concepts)
    assert result == {"reponse_bambara": "Conseil", "reponse_fr": "Conseil FR"}


# ─────────────────────────────────────────────
# Back-compat
# ─────────────────────────────────────────────


def test_back_compat_chat_result_import_chat_service():
    """`from app.services.chat_service import ChatResult` doit toujours fonctionner."""
    from app.services.chat_service import ChatResult as ChatResult_compat
    assert ChatResult_compat is ChatResult


def test_back_compat_wrappers_chat_service_methods_existent():
    """Les wrappers _try_ivr_* / _clarify / _search restent sur ChatService."""
    from app.services.chat_service import ChatService
    assert hasattr(ChatService, "_try_ivr_exact")
    assert hasattr(ChatService, "_try_ivr_concept")
    assert hasattr(ChatService, "_clarify_missing_culture")
    assert hasattr(ChatService, "_search_ivr_by_concept")
