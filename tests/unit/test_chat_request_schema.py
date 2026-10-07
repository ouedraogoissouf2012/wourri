"""Tests — borne de longueur de `ChatRequest.message` (#536)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.schemas import CHAT_MESSAGE_MAX_CHARS, ChatRequest


def test_message_a_la_borne_accepte():
    assert ChatRequest(message="a" * CHAT_MESSAGE_MAX_CHARS).message


def test_message_au_dela_de_la_borne_refuse():
    with pytest.raises(ValidationError):
        ChatRequest(message="a" * (CHAT_MESSAGE_MAX_CHARS + 1))


def test_meme_borne_que_la_console_de_demo():
    """Les deux points d'entrée mènent au même ChatService (constat C-20)."""
    from app.routers.demo import DemoAgriRequest

    assert DemoAgriRequest(message="a" * CHAT_MESSAGE_MAX_CHARS).message
    with pytest.raises(ValidationError):
        DemoAgriRequest(message="a" * (CHAT_MESSAGE_MAX_CHARS + 1))


def test_transcription_brute_non_bornee():
    """La transcription d'une longue note vocale ne doit pas faire échouer le chat."""
    req = ChatRequest(message="question", bambara_text="n bɛ malo sɛnɛ " * 400)
    assert len(req.bambara_text) > CHAT_MESSAGE_MAX_CHARS


def test_route_chat_repond_422_au_dela_de_la_borne():
    from app.routers import chat

    app = FastAPI()
    app.include_router(chat.router)
    with patch("app.security._API_SECRET_KEY", None):
        resp = TestClient(app).post(
            "/api/chat/", json={"message": "a" * (CHAT_MESSAGE_MAX_CHARS + 1)}
        )
    assert resp.status_code == 422
