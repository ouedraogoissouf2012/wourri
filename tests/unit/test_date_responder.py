"""Tests — réponse déterministe « quelle est la date du jour » (date_responder)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.data.calendrier_agricole import MOIS_FR
from app.models.schemas import Language
from app.services.chat.date_responder import (
    JOURS_FR,
    _format_date_fr,
    build_date_response,
    is_date_intent,
)
from app.services.chat.nlu_preprocessor import NLUResult


def _nlu(intent="QUESTION_DATE") -> NLUResult:
    return NLUResult(message_for_deepseek="quelle est la date", intent=intent, concepts={})


def test_is_date_intent():
    assert is_date_intent(_nlu("QUESTION_DATE")) is True
    assert is_date_intent(_nlu("QUESTION_METEO_AGRICOLE")) is False
    assert is_date_intent(_nlu(None)) is False


def test_format_date_fr_exact():
    """Format français déterministe, sans dépendre de la locale système."""
    dt = datetime(2026, 9, 9)
    jour = JOURS_FR[dt.weekday()]  # même logique que le responder
    assert _format_date_fr(dt) == f"{jour} 9 septembre 2026"


def test_format_date_fr_couvre_les_12_mois():
    for mois in range(1, 13):
        out = _format_date_fr(datetime(2026, mois, 15))
        assert MOIS_FR[mois] in out
        assert "2026" in out


@pytest.mark.asyncio
async def test_build_date_response_donne_la_vraie_date():
    with patch("app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)):
        r = await build_date_response(_nlu(), "Bouake", include_audio=False, language=Language.BOTH)
    assert r is not None
    assert r.meta["source"] == "date"
    now = datetime.now()
    assert "Aujourd'hui, nous sommes le" in r.response
    assert MOIS_FR[now.month] in r.response  # le vrai mois courant
    assert str(now.year) in r.response       # la vraie année


@pytest.mark.asyncio
async def test_build_date_response_audio_fr():
    with patch("app.services.tts_french.synthesize_french",
               new=AsyncMock(return_value="/static/audio/date.ogg")):
        r = await build_date_response(_nlu(), "Abidjan", include_audio=True, language=Language.FRENCH)
    assert r.audio_url == "/static/audio/date.ogg"
    assert r.audio_language == "Français"
