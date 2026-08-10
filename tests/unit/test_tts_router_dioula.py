"""Contrats ADR-0023 (#362) : la voix dioula est unifiée.

- POST /api/tts/dioula sert mms-tts-dyu (synthesize_dioula / synthesize_dioula_text)
- POST /api/tts/ avec language=dioula sert la voix DIOULA, plus le bambara malien
- POST /api/tts/bambara est étiqueté honnêtement « bambara »
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

import app.routers.tts as tts_router
from app.models.schemas import Language, TTSRequest


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/tts/dioula",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    }
    return Request(scope)


def test_tts_dioula_endpoint_uses_dyu_voice_for_dioula_text():
    """is_french=False → synthèse directe mms-tts-dyu (synthesize_dioula_text)."""
    with patch.object(
        tts_router, "synthesize_dioula_text", return_value="/static/audio/dyu_x.ogg"
    ) as spy_dyu, patch.object(
        tts_router, "synthesize_bambara_text"
    ) as spy_bam:
        resp = asyncio.run(
            tts_router.tts_dioula(_make_request(), text="N bɛ baara la", is_french=False)
        )

    spy_dyu.assert_called_once_with("N bɛ baara la")
    spy_bam.assert_not_called()  # la voix bambara ne doit JAMAIS servir ici
    assert resp.audio_url == "/static/audio/dyu_x.ogg"
    assert resp.language == "dioula"


def test_tts_dioula_endpoint_translates_french_via_dyu_pipeline():
    """is_french=True → synthesize_dioula (NLLB fra→dyu + TTS dyu)."""
    with patch.object(
        tts_router,
        "synthesize_dioula",
        new=AsyncMock(return_value=("/static/audio/dyu_y.ogg", "Aw ni sɔgɔma")),
    ) as spy:
        resp = asyncio.run(
            tts_router.tts_dioula(_make_request(), text="Bonjour", is_french=True)
        )

    spy.assert_awaited_once_with("Bonjour")
    assert resp.text == "Aw ni sɔgɔma"
    assert resp.language == "dioula"


def test_generic_tts_language_dioula_routes_to_dyu_not_bam():
    """POST /api/tts/ language=dioula → voix dioula (le bug historique servait
    mms-tts-bam en l'étiquetant « dioula »)."""
    with patch.object(
        tts_router,
        "synthesize_dioula",
        new=AsyncMock(return_value=("/static/audio/dyu_z.ogg", "I ni ce")),
    ) as spy_dyu, patch.object(
        tts_router, "synthesize_bambara"
    ) as spy_bam:
        resp = asyncio.run(
            tts_router.text_to_speech(
                _make_request(),
                TTSRequest(text="Merci", language=Language.DIOULA),
            )
        )

    spy_dyu.assert_awaited_once()
    spy_bam.assert_not_called()
    assert resp.language == "dioula"
    assert resp.text == "I ni ce"


def test_tts_bambara_endpoint_is_honestly_labeled():
    """POST /api/tts/bambara sert mms-tts-bam et le DIT (plus d'étiquette
    « dioula » mensongère)."""
    with patch.object(
        tts_router, "synthesize_bambara_text", return_value="/static/audio/bam_x.ogg"
    ):
        resp = asyncio.run(
            tts_router.tts_bambara(_make_request(), text="malo", is_french=False)
        )

    assert resp.language == "bambara"


def test_tts_dioula_endpoint_500_when_synthesis_fails():
    from fastapi import HTTPException

    with patch.object(tts_router, "synthesize_dioula_text", return_value=None):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                tts_router.tts_dioula(_make_request(), text="x", is_french=False)
            )
    assert exc.value.status_code == 500
