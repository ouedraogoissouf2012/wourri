"""Tests — réponse déterministe « quelle culture pour ma zone » (#509 C2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat.culture_zone_responder import (
    build_culture_zone_response,
    is_culture_zone_intent,
)
from app.services.chat.nlu_preprocessor import NLUResult


def _nlu(intent="QUESTION_GENERALE") -> NLUResult:
    return NLUResult(message_for_deepseek="quoi cultiver", intent=intent, concepts={})


def test_is_culture_zone_intent():
    assert is_culture_zone_intent(_nlu("QUESTION_GENERALE")) is True
    assert is_culture_zone_intent(_nlu("QUESTION_METEO_AGRICOLE")) is False
    assert is_culture_zone_intent(_nlu(None)) is False


@pytest.mark.asyncio
async def test_culture_zone_fr_liste_les_cultures():
    with patch("app.data.zones_agricoles.get_cultures_zone",
               return_value=["CULTURE_COTON", "CULTURE_MAIS", "CULTURE_MIL"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_NORD_SAVANE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=[]), \
         patch("app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)):
        r = await build_culture_zone_response(
            _nlu(), "Korhogo", include_audio=False, language=Language.FRENCH,
        )
    assert r is not None
    assert r.meta["source"] == "culture_zone"
    assert "coton" in r.response and "maïs" in r.response and "mil" in r.response
    assert "Korhogo" in r.response
    assert r.language == "french"


@pytest.mark.asyncio
async def test_culture_zone_priorise_la_saison():
    with patch("app.data.zones_agricoles.get_cultures_zone", return_value=["CULTURE_MAIS"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_CENTRE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois",
               return_value=[{"fr": "maïs", "phase": "plantation"}]), \
         patch("app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)):
        r = await build_culture_zone_response(
            _nlu(), "Bouake", include_audio=False, language=Language.FRENCH,
        )
    assert "bonne période" in r.response  # phrase de saison ajoutée


@pytest.mark.asyncio
async def test_culture_zone_dioula_renvoie_none():
    """Dioula/both : formulation à valider nativement → None (fallback DeepSeek)."""
    r = await build_culture_zone_response(
        _nlu(), "Korhogo", include_audio=False, language=Language.DIOULA,
    )
    assert r is None


@pytest.mark.asyncio
async def test_culture_zone_sans_cultures_renvoie_none():
    with patch("app.data.zones_agricoles.get_cultures_zone", return_value=[]):
        r = await build_culture_zone_response(
            _nlu(), "VilleInconnue", include_audio=False, language=Language.FRENCH,
        )
    assert r is None
