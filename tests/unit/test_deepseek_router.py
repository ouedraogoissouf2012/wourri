"""
Tests pour `app/services/chat/deepseek_router.py` (refactor P2-09 PR 5/5).

Couvre les 2 fonctions extraites de ChatService :
    - try_deepseek_dioula() : 3 branches (sans audio, avec audio, sans concept)
    - try_deepseek_french() : 2 branches (sans audio, avec audio)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.deepseek_router import try_deepseek_dioula, try_deepseek_french
from app.services.chat.nlu_preprocessor import NLUResult


def _make_nlu(intent="X", concepts=None) -> NLUResult:
    return NLUResult(
        message_for_deepseek="ma question",
        intent=intent,
        concepts=concepts or {},
    )


@pytest.mark.asyncio
async def test_try_deepseek_dioula_sans_audio():
    nlu = _make_nlu(intent="CONSEIL_PRODUCTION", concepts={"CULTURE_RIZ": True})
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Conseil DeepSeek FR"),
    ):
        result = await try_deepseek_dioula(
            nlu, None, "Abidjan", False, Language.DIOULA, "u1",
        )
    assert isinstance(result, ChatResult)
    assert result.response == "Conseil DeepSeek FR"
    assert result.audio_url is None
    assert result.response_dioula == "Conseil DeepSeek FR"
    assert result.meta["source"] == "deepseek_open"
    assert result.meta["cultures"] == ["CULTURE_RIZ"]


@pytest.mark.asyncio
async def test_try_deepseek_dioula_avec_audio_traduit():
    nlu = _make_nlu(intent="X", concepts={"CULTURE_RIZ": True})
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse FR"),
    ), patch(
        "app.services.tts_dioula.synthesize_dioula",
        new=AsyncMock(return_value=("/static/audio/x.wav", "Bambara traduit")),
    ):
        result = await try_deepseek_dioula(
            nlu, None, "Abidjan", True, Language.DIOULA, "u1",
        )
    assert result.response == "Reponse FR"
    assert result.response_dioula == "Bambara traduit"
    assert result.audio_url == "/static/audio/x.wav"
    assert result.audio_language == "Dioula"


@pytest.mark.asyncio
async def test_try_deepseek_dioula_sans_culture_meta_vide():
    nlu = _make_nlu(intent="X", concepts={"ACTION_PLANTER": True})
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse"),
    ):
        result = await try_deepseek_dioula(
            nlu, None, "Abidjan", False, Language.DIOULA, "u1",
        )
    assert result.meta["cultures"] == []


@pytest.mark.asyncio
async def test_try_deepseek_french_sans_audio():
    nlu = _make_nlu(intent=None, concepts={})
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse FR"),
    ):
        result = await try_deepseek_french(
            nlu, None, "Abidjan", False, Language.FRENCH, "u1",
        )
    assert result.response == "Reponse FR"
    assert result.audio_url is None
    assert result.audio_language is None
    assert result.language == "french"


@pytest.mark.asyncio
async def test_try_deepseek_french_avec_audio():
    nlu = _make_nlu(intent=None, concepts={})
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse FR"),
    ), patch(
        "app.services.tts_french.synthesize_french",
        new=AsyncMock(return_value="/static/audio/fr.wav"),
    ):
        result = await try_deepseek_french(
            nlu, None, "Abidjan", True, Language.FRENCH, "u1",
        )
    assert result.audio_url == "/static/audio/fr.wav"
    assert result.audio_language == "Français"
