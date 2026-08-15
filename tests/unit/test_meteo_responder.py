"""Tests pour `app/services/chat/meteo_responder.py` (issue #355 T4).

Couvre le routage météo pur :
    - is_pure_weather_intent (True/False)
    - build_meteo_response : demain (prévision J+1) vs actuel (météo courante)
    - dégradation gracieuse (None) quand la donnée météo est indisponible
    - synthèse TTS optionnelle (include_audio)

Le module TTS (`synthesize_dioula_text`) et le fetch prévision
(`get_weather_forecast_tomorrow`) sont mockés ; `build_meteo_prevision` /
`build_meteo_bambara` tournent en réel (fonctions pures déjà testées).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat.meteo_responder import (
    build_meteo_response,
    is_pure_weather_intent,
)
from app.services.chat.nlu_preprocessor import NLUResult


def _nlu(intent="QUESTION_METEO_AGRICOLE", concepts=None) -> NLUResult:
    return NLUResult(
        message_for_deepseek="quel temps",
        intent=intent,
        concepts=concepts or {},
    )


def _forecast(**over):
    base = {
        "city": "Bouaké",
        "weather_code": 65,
        "temperature_max": 27,
        "temperature_min": 21,
        "precipitation_mm": 12.5,
        "precipitation_probability": 80,
    }
    base.update(over)
    return base


# ─────────────────────────────────────────────
# is_pure_weather_intent
# ─────────────────────────────────────────────


def test_is_pure_weather_intent_true():
    assert is_pure_weather_intent(_nlu(intent="QUESTION_METEO_AGRICOLE")) is True


def test_is_pure_weather_intent_false_autre_intent():
    assert is_pure_weather_intent(_nlu(intent="CONSEIL_PRODUCTION")) is False
    assert is_pure_weather_intent(_nlu(intent=None)) is False


# ─────────────────────────────────────────────
# build_meteo_response — demain (prévision J+1)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demain_utilise_prevision_j1():
    """TEMPS_DEMAIN présent → fetch prévision J+1 → source=meteo_prevision."""
    nlu = _nlu(concepts={"TEMPS_SAISON_PLUIE": True, "TEMPS_DEMAIN": True})
    with patch(
        "app.services.weather.get_weather_forecast_tomorrow",
        new=AsyncMock(return_value=_forecast()),
    ) as mock_fetch:
        result = await build_meteo_response(
            nlu=nlu, weather_data=None, city="Bouaké",
            include_audio=False, language=Language.BOTH,
        )

    mock_fetch.assert_awaited_once_with("Bouaké")
    assert result is not None
    assert result.meta["source"] == "meteo_prevision"
    assert result.meta["intent"] == "QUESTION_METEO_AGRICOLE"
    assert "sanji" in result.response_dioula  # dioula validé (pluie)
    assert "Demain" in result.response  # FR prévisionnel
    assert "80" in result.response  # probabilité remontée
    assert result.audio_url is None
    assert result.language == "both"


@pytest.mark.asyncio
async def test_demain_forecast_indisponible_retourne_none():
    """Prévision J+1 None → None (→ fallback DeepSeek assuré par l'appelant)."""
    nlu = _nlu(concepts={"TEMPS_DEMAIN": True})
    with patch(
        "app.services.weather.get_weather_forecast_tomorrow",
        new=AsyncMock(return_value=None),
    ):
        result = await build_meteo_response(
            nlu=nlu, weather_data={"weather_code": 0, "temperature": 28},
            city="Man", include_audio=False, language=Language.DIOULA,
        )
    assert result is None


# ─────────────────────────────────────────────
# build_meteo_response — actuel (météo courante)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_actuel_sans_temps_demain_utilise_weather_data():
    """Pas de TEMPS_DEMAIN → météo actuelle depuis weather_data (pas de fetch)."""
    nlu = _nlu(concepts={"TEMPS_METEO": True})
    weather = {"city": "Abidjan", "weather_code": 0, "temperature": 28, "precipitation": 0}
    with patch(
        "app.services.weather.get_weather_forecast_tomorrow",
        new=AsyncMock(),
    ) as mock_fetch:
        result = await build_meteo_response(
            nlu=nlu, weather_data=weather, city="Abidjan",
            include_audio=False, language=Language.BOTH,
        )

    mock_fetch.assert_not_called()  # pas de prévision demandée
    assert result is not None
    assert result.meta["source"] == "meteo_actuel"
    assert "tile" in result.response_dioula or "ɲɛ" in result.response_dioula


@pytest.mark.asyncio
async def test_actuel_weather_data_none_retourne_none():
    """Météo actuelle indisponible → None (fallback DeepSeek)."""
    nlu = _nlu(concepts={"TEMPS_METEO": True})
    result = await build_meteo_response(
        nlu=nlu, weather_data=None, city="Man",
        include_audio=False, language=Language.DIOULA,
    )
    assert result is None


# ─────────────────────────────────────────────
# TTS optionnel
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_include_audio_declenche_synthese_dioula():
    """include_audio=True → audio_url renseigné + audio_language=Dioula."""
    nlu = _nlu(concepts={"TEMPS_DEMAIN": True})
    with patch(
        "app.services.weather.get_weather_forecast_tomorrow",
        new=AsyncMock(return_value=_forecast(weather_code=0, temperature_max=36,
                                             precipitation_mm=0, precipitation_probability=5)),
    ), patch(
        "app.services.tts_dioula.synthesize_dioula_text",
        return_value="/audio/prevision.ogg",
    ) as mock_tts:
        result = await build_meteo_response(
            nlu=nlu, weather_data=None, city="Korhogo",
            include_audio=True, language=Language.BOTH,
        )

    assert result.audio_url == "/audio/prevision.ogg"
    assert result.audio_language == "Dioula"
    mock_tts.assert_called_once()
