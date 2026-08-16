"""ADR-0032 : /docs et /openapi absents dès que la surface publique est active."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app(*, is_production: bool, origins: list[str]) -> FastAPI:
    public = is_production or bool(origins)
    return FastAPI(
        docs_url=None if public else "/docs",
        redoc_url=None if public else "/redoc",
        openapi_url=None if public else "/openapi.json",
    )


def test_docs_on_in_dev():
    client = TestClient(_app(is_production=False, origins=[]))
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_off_in_production():
    client = TestClient(_app(is_production=True, origins=[]))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_off_when_allowed_origins_set():
    client = TestClient(
        _app(is_production=False, origins=["https://console.vercel.app"])
    )
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
