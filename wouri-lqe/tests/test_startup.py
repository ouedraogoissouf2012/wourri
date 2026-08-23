"""Garde-fous de démarrage (lifespan) : migrations, secret prod, cookie Secure.

L'app est rechargée à chaque cas pour relire l'environnement (get_settings n'est pas
mis en cache). Le lifespan ne se déclenche qu'avec `with TestClient(app)`.
"""
import importlib

import pytest
from fastapi.testclient import TestClient


def _fresh_app():
    import app.main as m
    importlib.reload(m)
    return m.app


def test_lifespan_applies_migrations(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "dev")
    with TestClient(_fresh_app()) as client:
        assert client.get("/health").status_code == 200


def test_secret_guard_refuses_default_in_prod(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", "dev-only-not-for-prod")
    with pytest.raises(RuntimeError):
        with TestClient(_fresh_app()):
            pass


def test_secret_guard_refuses_short_secret_in_prod(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", "tooshort")
    with pytest.raises(RuntimeError):
        with TestClient(_fresh_app()):
            pass


def test_secret_guard_accepts_strong_secret_in_prod(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", "a-very-strong-prod-secret-32chars")
    with TestClient(_fresh_app()) as client:
        assert client.get("/health").status_code == 200


def test_cookie_secure_in_prod(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", "a-very-strong-prod-secret-32chars")
    monkeypatch.setenv("LQE_ADMIN_USER", "admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    with TestClient(_fresh_app()) as client:
        r = client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
        assert r.status_code == 200
        assert "secure" in r.headers.get("set-cookie", "").lower()


def test_cookie_not_secure_in_dev(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "dev")
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    with TestClient(_fresh_app()) as client:
        r = client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
        assert r.status_code == 200
        assert "secure" not in r.headers.get("set-cookie", "").lower()
