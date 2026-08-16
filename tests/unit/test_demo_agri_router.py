"""Démo agri : badge corpus vs fallback (sans appeler ML réel)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import demo
from app.security import require_api_key


def _client(monkeypatch, *, source: str):
    async def _process(**kwargs):
        return SimpleNamespace(
            response="Prépare bien ton champ de maïs.",
            response_dioula="I ka foro labɛn ka ɲɛ.",
            audio_url="/static/audio/demo.ogg",
            city="Bouaké",
            language="both",
            audio_language="dioula",
            meta={"source": source, "intent": "CONSEIL_PRODUCTION", "cultures": ["CULTURE_MAIS"]},
        )

    monkeypatch.setattr(
        demo,
        "get_chat_service",
        lambda: SimpleNamespace(process=AsyncMock(side_effect=_process)),
    )
    app = FastAPI()
    app.include_router(demo.router)
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


def test_demo_agri_corpus_badge(monkeypatch):
    client = _client(monkeypatch, source="ivr_exact")
    r = client.post("/api/demo/agri", json={"message": "comment planter le maïs"})
    assert r.status_code == 200
    body = r.json()
    assert body["badge"] == "CORPUS_VALIDE"
    assert body["source"] == "ivr_exact"
    assert body["text_dioula"]
    assert "maïs" in body["text_fr"].lower() or "champ" in body["text_fr"].lower()


def test_demo_agri_deepseek_badge(monkeypatch):
    client = _client(monkeypatch, source="deepseek_open")
    r = client.post("/api/demo/agri", json={"message": "bonjour"})
    assert r.status_code == 200
    assert r.json()["badge"] == "FALLBACK_OUVERT"
