"""Page admin Baoulé — login + HTML FR."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin_baoule


def test_page_requires_config(monkeypatch):
    monkeypatch.delenv("BAOULE_PROVIDER_USER", raising=False)
    monkeypatch.delenv("BAOULE_PROVIDER_PASSWORD", raising=False)
    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app)
    r = client.get("/admin/baoule/")
    assert r.status_code == 503
    assert "BAOULE_PROVIDER_USER" in r.text


def test_page_login_form_when_configured(monkeypatch):
    monkeypatch.setenv("BAOULE_PROVIDER_USER", "u1")
    monkeypatch.setenv("BAOULE_PROVIDER_PASSWORD", "password12")
    monkeypatch.setenv("API_SECRET_KEY", "k")
    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app)
    r = client.get("/admin/baoule/")
    assert r.status_code == 200
    assert "Provider Baoulé" in r.text
    assert "Mot de passe" in r.text
