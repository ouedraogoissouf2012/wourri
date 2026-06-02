"""
Tests pour `app/services/chat/handlers/french_handler.py` (ADR-0015 PR 1/4).

Couvre le handler FRENCH du Strategy Pattern :
    - FrenchHandler.process() : 4 branches (sans audio, avec audio, TTS echec, weather)
    - Backwards compatibility : try_deepseek_french wrapper + _try_deepseek_french

Pattern de mock : on patche `app.services.deepseek.chat_with_deepseek` et
`app.services.tts_french.synthesize_french` au niveau du module deepseek_router
(pour la retrocompat) ET via l'import direct dans FrenchHandler.process().
Les imports dans process() sont locaux (`from app.services.deepseek import ...`)
donc on patche les modules d'origine.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #276 (PR 1/4)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.handlers import HANDLERS, FrenchHandler
from app.services.chat.handlers._protocol import LanguageHandler
from app.services.chat.nlu_preprocessor import NLUResult


def _make_nlu(intent=None, concepts=None) -> NLUResult:
    return NLUResult(
        message_for_deepseek="ma question",
        intent=intent,
        concepts=concepts or {},
    )


# ─────────────────────────────────────────────
# Protocol compliance
# ─────────────────────────────────────────────


class TestProtocolCompliance:
    """Verifie que FrenchHandler respecte le Protocol LanguageHandler."""

    def test_french_handler_is_in_registry(self):
        """HANDLERS[Language.FRENCH] doit pointer vers une instance de FrenchHandler."""
        assert Language.FRENCH in HANDLERS
        assert isinstance(HANDLERS[Language.FRENCH], FrenchHandler)

    def test_french_handler_satisfies_protocol(self):
        """Verifie que FrenchHandler() est isinstance(LanguageHandler) via duck typing."""
        # Protocol n'a pas de isinstance() strict en Python sans runtime_checkable,
        # mais on verifie que la methode process existe et est async.
        import inspect
        handler = FrenchHandler()
        assert hasattr(handler, "process")
        assert inspect.iscoroutinefunction(handler.process)


# ─────────────────────────────────────────────
# FrenchHandler.process() — 4 branches
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_french_handler_sans_audio():
    """include_audio=False : pas d'appel TTS, audio_url=None, audio_language=None."""
    nlu = _make_nlu()
    handler = FrenchHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse FR"),
    ) as mock_ds, patch(
        "app.services.tts_french.synthesize_french",
        new=AsyncMock(),
    ) as mock_tts:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.FRENCH,
            user_id="u1",
        )

    assert isinstance(result, ChatResult)
    assert result.response == "Reponse FR"
    assert result.audio_url is None
    assert result.audio_language is None
    assert result.language == "french"
    assert result.city == "Abidjan"
    mock_ds.assert_called_once()
    mock_tts.assert_not_called()


@pytest.mark.asyncio
async def test_french_handler_avec_audio_succes():
    """include_audio=True + TTS retourne URL : audio_url + audio_language='Français'."""
    nlu = _make_nlu()
    handler = FrenchHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Plantez le riz"),
    ), patch(
        "app.services.tts_french.synthesize_french",
        new=AsyncMock(return_value="/static/audio/fr_xxx.ogg"),
    ) as mock_tts:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Bouake",
            include_audio=True,
            language=Language.FRENCH,
            user_id="u1",
        )

    assert result.audio_url == "/static/audio/fr_xxx.ogg"
    assert result.audio_language == "Français"
    mock_tts.assert_called_once_with("Plantez le riz")


@pytest.mark.asyncio
async def test_french_handler_avec_audio_echec_tts():
    """include_audio=True + TTS retourne None (echec Piper) : audio_url=None, audio_language=None."""
    nlu = _make_nlu()
    handler = FrenchHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse FR"),
    ), patch(
        "app.services.tts_french.synthesize_french",
        new=AsyncMock(return_value=None),
    ):
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=True,
            language=Language.FRENCH,
            user_id=None,
        )

    assert result.audio_url is None
    # FIX-OCP : audio_language n'est defini que si audio_url existe (Optional)
    assert result.audio_language is None
    assert result.response == "Reponse FR"


@pytest.mark.asyncio
async def test_french_handler_passe_weather_a_deepseek():
    """weather_data est transmis a chat_with_deepseek pour le system prompt meteo."""
    nlu = _make_nlu()
    weather = {
        "city": "Korhogo",
        "temperature": 32,
        "humidity": 65,
        "precipitation": 0,
        "wind_speed": 5,
        "weather_description": "Soleil",
    }
    handler = FrenchHandler()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="Reponse avec meteo"),
    ) as mock_ds:
        await handler.process(
            nlu=nlu,
            weather_data=weather,
            city="Korhogo",
            include_audio=False,
            language=Language.FRENCH,
            user_id="u1",
        )

    # Verifier que weather_data a ete passe en kwarg
    call_kwargs = mock_ds.call_args.kwargs
    assert call_kwargs["weather_data"] == weather
    assert call_kwargs["language"] == Language.FRENCH
    assert call_kwargs["user_id"] == "u1"
    assert call_kwargs["message"] == "ma question"


# ─────────────────────────────────────────────
# Backwards compatibility (PR 1/4 wrapper)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_back_compat_try_deepseek_french_delegue_au_handler():
    """deepseek_router.try_deepseek_french doit deleguer a HANDLERS[FRENCH].process()."""
    from app.services.chat.deepseek_router import try_deepseek_french

    nlu = _make_nlu()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="FR via wrapper"),
    ), patch(
        "app.services.tts_french.synthesize_french",
        new=AsyncMock(return_value="/static/audio/x.ogg"),
    ):
        result = await try_deepseek_french(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=True,
            language=Language.FRENCH,
            user_id="u1",
        )

    assert isinstance(result, ChatResult)
    assert result.response == "FR via wrapper"
    assert result.audio_url == "/static/audio/x.ogg"
    assert result.audio_language == "Français"


@pytest.mark.asyncio
async def test_back_compat_chat_service_method_delegue():
    """ChatService._try_deepseek_french doit toujours retourner un ChatResult."""
    from app.services.chat_service import ChatService

    service = ChatService()
    nlu = _make_nlu()
    with patch(
        "app.services.deepseek.chat_with_deepseek",
        new=AsyncMock(return_value="FR via ChatService"),
    ), patch(
        "app.services.tts_french.synthesize_french",
        new=AsyncMock(return_value=None),
    ):
        result = await service._try_deepseek_french(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.FRENCH,
            user_id=None,
        )

    assert isinstance(result, ChatResult)
    assert result.response == "FR via ChatService"


def test_back_compat_chat_service_method_exists():
    """L'attribut _try_deepseek_french doit toujours exister (back-compat)."""
    from app.services.chat_service import ChatService

    assert hasattr(ChatService, "_try_deepseek_french")
