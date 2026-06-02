"""
Tests pour `app/services/chat/handlers/english_handler.py` (ADR-0015 PR 4/4).

Couvre le handler ENGLISH du Strategy Pattern :
    - EnglishHandler.process() : 4 branches (sans audio, avec audio, TTS echec,
      weather data transmis a DeepSeek)
    - Protocol compliance (handler dans registre HANDLERS)
    - ChatResult.meta["source"] = "deepseek_english" pour observabilite
    - audio_language = "English" si audio genere

Note importante : EnglishHandler bypasse la cascade IVR car le corpus IVR
est uniquement BAM/FR (162 entrees). La logique est donc plus simple que
DioulaHandler (juste DeepSeek + TTS), symetrique a FrenchHandler.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #279 (PR 4/4)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.handlers import HANDLERS, EnglishHandler
from app.services.chat.nlu_preprocessor import NLUResult


def _make_nlu(message="my question") -> NLUResult:
    return NLUResult(
        message_for_deepseek=message,
        intent=None,  # NLU bambara/dioula ne s'applique pas a l'EN
        concepts={},
    )


# ─────────────────────────────────────────────
# Protocol compliance
# ─────────────────────────────────────────────


class TestProtocolCompliance:
    def test_english_handler_is_in_registry(self):
        assert Language.ENGLISH in HANDLERS
        assert isinstance(HANDLERS[Language.ENGLISH], EnglishHandler)

    def test_english_handler_satisfies_protocol(self):
        import inspect
        handler = EnglishHandler()
        assert hasattr(handler, "process")
        assert inspect.iscoroutinefunction(handler.process)

    def test_english_handler_distinct_instance_from_other_handlers(self):
        """EnglishHandler doit etre une instance distincte des autres handlers."""
        assert HANDLERS[Language.ENGLISH] is not HANDLERS[Language.FRENCH]
        assert HANDLERS[Language.ENGLISH] is not HANDLERS[Language.DIOULA]
        assert HANDLERS[Language.ENGLISH] is not HANDLERS[Language.BOTH]


# ─────────────────────────────────────────────
# EnglishHandler.process() — 4 branches
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_english_handler_sans_audio():
    """include_audio=False : pas d'appel TTS, audio_url=None, audio_language=None."""
    nlu = _make_nlu("When should I plant rice?")
    handler = EnglishHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Plant rice in May during the rainy season."),
    ) as mock_ds, patch(
        "app.services.tts_english.synthesize_english",
        new=AsyncMock(),
    ) as mock_tts:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Bouake",
            include_audio=False,
            language=Language.ENGLISH,
            user_id="u1",
        )

    assert isinstance(result, ChatResult)
    assert result.response == "Plant rice in May during the rainy season."
    assert result.audio_url is None
    assert result.audio_language is None
    assert result.language == "english"
    assert result.city == "Bouake"
    assert result.meta == {"source": "deepseek_english"}
    mock_ds.assert_called_once()
    mock_tts.assert_not_called()


@pytest.mark.asyncio
async def test_english_handler_avec_audio_succes():
    """include_audio=True + TTS retourne URL : audio_url + audio_language='English'."""
    nlu = _make_nlu()
    handler = EnglishHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Plant rice now."),
    ), patch(
        "app.services.tts_english.synthesize_english",
        new=AsyncMock(return_value="/static/audio/en_xxx.ogg"),
    ) as mock_tts:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=True,
            language=Language.ENGLISH,
            user_id=None,
        )

    assert result.audio_url == "/static/audio/en_xxx.ogg"
    assert result.audio_language == "English"
    mock_tts.assert_called_once_with("Plant rice now.")


@pytest.mark.asyncio
async def test_english_handler_avec_audio_echec_tts():
    """include_audio=True + TTS retourne None (echec Piper EN ou modele absent) :
    audio_url=None, audio_language=None, mais reponse texte preservee."""
    nlu = _make_nlu()
    handler = EnglishHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reply EN"),
    ), patch(
        "app.services.tts_english.synthesize_english",
        new=AsyncMock(return_value=None),
    ):
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=True,
            language=Language.ENGLISH,
            user_id=None,
        )

    assert result.audio_url is None
    assert result.audio_language is None
    assert result.response == "Reply EN"


@pytest.mark.asyncio
async def test_english_handler_passe_weather_et_user_id_a_deepseek():
    """weather_data et user_id sont transmis a chat_with_deepseek."""
    nlu = _make_nlu("Weather today?")
    weather = {
        "city": "Korhogo",
        "temperature": 32,
        "humidity": 65,
        "precipitation": 0,
        "wind_speed": 5,
        "weather_description": "Sunny",
    }
    handler = EnglishHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Sunny day."),
    ) as mock_ds:
        await handler.process(
            nlu=nlu,
            weather_data=weather,
            city="Korhogo",
            include_audio=False,
            language=Language.ENGLISH,
            user_id="investor-42",
        )

    call_kwargs = mock_ds.call_args.kwargs
    assert call_kwargs["weather_data"] == weather
    assert call_kwargs["language"] == Language.ENGLISH
    assert call_kwargs["user_id"] == "investor-42"
    assert call_kwargs["message"] == "Weather today?"


# ─────────────────────────────────────────────
# Language enum
# ─────────────────────────────────────────────


def test_language_enum_includes_english():
    """Language.ENGLISH doit exister et avoir value='english'."""
    assert Language.ENGLISH.value == "english"
    assert Language("english") is Language.ENGLISH
