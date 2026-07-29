"""
Contrats nominaux des endpoints Chat et ASR.

Les frontières ML sont mockées : ces tests vérifient le câblage HTTP, la
validation Pydantic et la délégation vers les services sans charger de modèle.
"""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.models.schemas import Language
from app.security import limiter
from app.services.chat_service import ChatResult


@pytest.fixture
def client():
    """Client minimal des deux routeurs, sans démarrer le lifespan ML."""
    with patch("app.security._API_SECRET_KEY", None):
        from app.routers import asr, chat

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(chat.router)
        app.include_router(asr.router)

        yield TestClient(app, raise_server_exceptions=False)


def test_chat_delegates_to_chat_service(client):
    """POST /api/chat/ transmet la requête et sérialise le résultat métier."""
    service = MagicMock()
    service.process = AsyncMock(
        return_value=ChatResult(
            response="Conseil en français",
            response_dioula="Ladilikan bamanankan na",
            audio_url="/static/audio/chat-test.wav",
            city="Bouaké",
            language="both",
            audio_language="Dioula",
            meta={"intent": "agriculture", "source": "ivr"},
        )
    )

    with patch("app.routers.chat.get_chat_service", return_value=service):
        response = client.post(
            "/api/chat/",
            json={
                "message": "Comment cultiver le riz à Bouaké ?",
                "city": "Abidjan",
                "language": "both",
                "include_audio": True,
                "user_id": "farmer-48",
                "bambara_text": "malo sɛnɛ",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Conseil en français",
        "response_dioula": "Ladilikan bamanankan na",
        "response_local": None,
        "audio_url": "/static/audio/chat-test.wav",
        "city": "Bouaké",
        "language": "both",
        "audio_language": "Dioula",
        "meta": {"intent": "agriculture", "source": "ivr"},
    }
    service.process.assert_awaited_once_with(
        message="Comment cultiver le riz à Bouaké ?",
        city="Abidjan",
        language=Language.BOTH,
        bambara_text="malo sɛnɛ",
        include_audio=True,
        user_id="farmer-48",
    )


def test_asr_transcribe_bambara_uses_default_chain(client):
    """POST /api/asr/transcribe utilise la chaîne bambara pour `bam`."""
    chain = MagicMock()
    chain.transcribe = AsyncMock(return_value="malo sɛnɛ")

    with patch("app.routers.asr.get_asr_chain", return_value=chain) as factory:
        response = client.post(
            "/api/asr/transcribe",
            files={"audio": ("question.ogg", io.BytesIO(b"fake-audio"), "audio/ogg")},
            data={"language": "bam"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "transcription": "malo sɛnɛ",
        "language": "bam",
        "language_name": "Bambara/Dioula",
    }
    factory.assert_called_once_with()
    chain.transcribe.assert_awaited_once_with(b"fake-audio", "ogg")


def test_asr_transcribe_local_language_uses_generic_chain(client):
    """POST /api/asr/transcribe sélectionne la chaîne de la langue demandée."""
    chain = MagicMock()
    chain.transcribe = AsyncMock(return_value="transcription attié")

    with patch(
        "app.routers.asr.get_generic_asr_chain",
        return_value=chain,
    ) as factory:
        response = client.post(
            "/api/asr/transcribe",
            files={"audio": ("question.mp3", io.BytesIO(b"generic-audio"), "audio/mpeg")},
            data={"language": "ati"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "transcription": "transcription attié",
        "language": "ati",
        "language_name": "Attié",
    }
    factory.assert_called_once_with("ati")
    chain.transcribe.assert_awaited_once_with(b"generic-audio", "mp3")
