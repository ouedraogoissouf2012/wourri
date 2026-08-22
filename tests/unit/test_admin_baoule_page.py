"""Écran Baoulé retiré du moteur (ADR-0033) : /admin/baoule/ redirige vers le service LQE."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin_baoule


def test_baoule_home_redirects_to_lqe(monkeypatch):
    monkeypatch.setenv("WOURI_LQE_URL", "https://lqe.example.test")
    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app, follow_redirects=False)
    r = client.get("/admin/baoule/")
    assert r.status_code == 302
    assert r.headers["location"] == "https://lqe.example.test"


def test_baoule_home_redirect_default(monkeypatch):
    monkeypatch.delenv("WOURI_LQE_URL", raising=False)
    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app, follow_redirects=False)
    r = client.get("/admin/baoule/")
    assert r.status_code == 302
    assert r.headers["location"] == "https://lqe.africandigitconsulting.com"


def test_lqe_uses_template():
    from app.routers import lqe

    app = FastAPI()
    app.include_router(lqe.router)
    client = TestClient(app)
    r = client.get("/admin/lqe/")
    assert r.status_code == 200
    assert "dioula" in r.text.lower()
    assert 'href="/static/admin/lqe.css"' in r.text
