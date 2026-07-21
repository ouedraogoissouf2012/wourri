"""
Tests pour la gestion d'erreurs DeepSeek (audit 2026-07-21).

Bug corrigé : `chat_with_deepseek` retournait des STRINGS d'erreur
("Erreur API: 500 - ...") comme si c'était la réponse. En mode dioula,
ces strings étaient traduites en dioula via NLLB puis VOCALISÉES en note
vocale pour l'agriculteur. Le circuit breaker whatsapp-server ne s'ouvrait
jamais (HTTP 200).

Couvre :
    - chat_with_deepseek lève DeepSeekUnavailableError sur : clé absente,
      HTTP non-200, timeout, erreur réseau générique
    - Le message d'exception ne contient PAS le corps de la réponse HTTP
      (risque de fuite de détails internes)
    - ChatService.process RE-RAISE DeepSeekUnavailableError (ne la convertit
      pas en ChatResult HTTP 200)
    - Anti-régression : une exception générique dans un handler retourne
      toujours le ChatResult de fallback (comportement historique préservé)
    - Anti-régression : correct_stt_transcription reste gracieux (retour
      raw_text sur échec, jamais d'exception)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.schemas import Language
from app.services.deepseek import (
    DeepSeekUnavailableError,
    chat_with_deepseek,
    correct_stt_transcription,
)


# ─────────────────────────────────────────────
# Fakes httpx
# ─────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Remplace httpx.AsyncClient : renvoie une réponse fixe ou lève une exception."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_client(response=None, exc=None):
    """Patch httpx.AsyncClient du module deepseek avec le fake."""
    return patch(
        "app.services.deepseek.httpx.AsyncClient",
        lambda *a, **k: _FakeAsyncClient(response=response, exc=exc),
    )


def _patch_api_key(value):
    from app.services import deepseek as deepseek_module
    return patch.object(deepseek_module.settings, "deepseek_api_key", value)


# ─────────────────────────────────────────────
# chat_with_deepseek : cas d'erreur → exception
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cle_absente_leve_unavailable():
    with _patch_api_key(""):
        with pytest.raises(DeepSeekUnavailableError):
            await chat_with_deepseek("bonjour")


@pytest.mark.asyncio
async def test_http_500_leve_unavailable():
    response = _FakeResponse(status_code=500, text="internal stack trace secret")
    with _patch_api_key("sk-test"), _patch_client(response=response):
        with pytest.raises(DeepSeekUnavailableError) as exc_info:
            await chat_with_deepseek("bonjour")
    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_message_exception_sans_corps_reponse():
    """Le corps HTTP (potentiels détails internes) ne fuit pas dans l'exception."""
    response = _FakeResponse(status_code=502, text="internal stack trace secret")
    with _patch_api_key("sk-test"), _patch_client(response=response):
        with pytest.raises(DeepSeekUnavailableError) as exc_info:
            await chat_with_deepseek("bonjour")
    assert "internal stack trace secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_timeout_leve_unavailable():
    with _patch_api_key("sk-test"), _patch_client(exc=httpx.TimeoutException("timeout")):
        with pytest.raises(DeepSeekUnavailableError):
            await chat_with_deepseek("bonjour")


@pytest.mark.asyncio
async def test_erreur_reseau_leve_unavailable_type_only():
    """Erreur réseau générique → exception avec le TYPE seulement (pas l'URL)."""
    exc = httpx.ConnectError("connection refused http://api.deepseek.com?key=secret")
    with _patch_api_key("sk-test"), _patch_client(exc=exc):
        with pytest.raises(DeepSeekUnavailableError) as exc_info:
            await chat_with_deepseek("bonjour")
    assert "ConnectError" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_reponse_200_retourne_le_texte():
    """Chemin nominal inchangé : 200 → contenu retourné."""
    response = _FakeResponse(
        status_code=200,
        json_data={"choices": [{"message": {"content": "Conseil agricole"}}]},
    )
    with _patch_api_key("sk-test"), _patch_client(response=response):
        result = await chat_with_deepseek("bonjour")
    assert result == "Conseil agricole"


# ─────────────────────────────────────────────
# ChatService : propagation vs fallback
# ─────────────────────────────────────────────


class _RaisingHandler:
    def __init__(self, exc):
        self._exc = exc

    async def process(self, **kwargs):
        raise self._exc


@pytest.mark.asyncio
async def test_chat_service_propage_deepseek_unavailable():
    """DeepSeekUnavailableError traverse le catch générique de ChatService
    → FastAPI 500 → circuit breaker whatsapp-server → audio d'excuse."""
    from app.services.chat_service import ChatService

    handler = _RaisingHandler(DeepSeekUnavailableError("DeepSeek HTTP 500"))
    with patch(
        "app.services.weather.get_weather", new=AsyncMock(return_value=None)
    ), patch.dict(
        "app.services.chat.handlers.HANDLERS", {Language.FRENCH: handler}
    ):
        service = ChatService()
        with pytest.raises(DeepSeekUnavailableError):
            await service.process("bonjour", language=Language.FRENCH)


@pytest.mark.asyncio
async def test_chat_service_exception_generique_garde_fallback():
    """Anti-régression : toute autre exception garde le ChatResult de repli
    (comportement historique — pas de 500 pour un bug interne quelconque)."""
    from app.services.chat_service import ChatService

    handler = _RaisingHandler(ValueError("bug interne quelconque"))
    with patch(
        "app.services.weather.get_weather", new=AsyncMock(return_value=None)
    ), patch.dict(
        "app.services.chat.handlers.HANDLERS", {Language.FRENCH: handler}
    ):
        service = ChatService()
        result = await service.process("bonjour", language=Language.FRENCH)
    assert "problèmes de connexion" in result.response


# ─────────────────────────────────────────────
# correct_stt_transcription : reste gracieux
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stt_correction_reste_gracieuse_sur_http_500():
    """La correction STT ne lève JAMAIS : elle retourne raw_text (dégradation
    acceptable pour une correction orthographique)."""
    response = _FakeResponse(status_code=500, text="err")
    with _patch_api_key("sk-test"), _patch_client(response=response):
        result = await correct_stt_transcription("bonjour le riz", Language.FRENCH)
    assert result == "bonjour le riz"


@pytest.mark.asyncio
async def test_stt_correction_reste_gracieuse_sur_timeout():
    with _patch_api_key("sk-test"), _patch_client(exc=httpx.TimeoutException("t")):
        result = await correct_stt_transcription("bonjour le riz", Language.FRENCH)
    assert result == "bonjour le riz"
