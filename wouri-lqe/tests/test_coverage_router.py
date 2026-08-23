"""Test de la route /coverage (admin) — ADR-0034 P1."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import language_registry as reg


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_ADMIN_USER", "admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    from app.routers import coverage as coverage_router
    from app.routers import session as session_router
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(coverage_router.router)
    return TestClient(app)


def test_coverage_requires_admin(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    client = _client(monkeypatch, tmp_path)
    assert client.get("/coverage").status_code in (401, 403)


def test_coverage_matrix_via_route(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    client = _client(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    r = client.get("/coverage")
    assert r.status_code == 200
    langs = r.json()["languages"]
    assert langs[0]["code"] == "bci"
    assert langs[0]["total"] == 2       # 2 concepts seedes par la fixture corpus
    assert langs[0]["covered"] == 0
