"""Garde-fous de démarrage (lifespan) : migrations, secret public/prod, cookie Secure.

L'app est rechargée à chaque cas pour relire l'environnement (get_settings n'est pas
mis en cache). Le lifespan ne se déclenche qu'avec `with TestClient(app)`.
"""
import importlib

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_conn, valid_schema

STRONG = "a-very-strong-prod-secret-32chars"


def _fresh_app():
    import app.main as m
    importlib.reload(m)
    return m.app


def test_lifespan_applies_migrations(monkeypatch):
    # DROP schéma puis démarrage SANS fixture db : SEUL le lifespan doit recréer les tables.
    monkeypatch.setenv("LQE_ENV", "dev")
    monkeypatch.setenv("LQE_SECRET", STRONG)
    schema = valid_schema(get_settings().lqe_db_schema)
    try:
        with get_conn(autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL indisponible: {exc}")
    with TestClient(_fresh_app()) as client:
        assert client.get("/health").status_code == 200
    with get_conn() as conn:
        exists = conn.execute("SELECT to_regclass('productions')").fetchone()[0]
    assert exists is not None  # les tables existent => le lifespan a bien migré


def test_secret_guard_refuses_default_even_in_dev(monkeypatch):
    # le secret par défaut est un placeholder PUBLIC du repo -> refusé même en dev
    # (pas besoin de Postgres : le raise précède run_migrations)
    monkeypatch.setenv("LQE_ENV", "dev")
    monkeypatch.setenv("LQE_SECRET", "dev-only-not-for-prod")
    with pytest.raises(RuntimeError):
        with TestClient(_fresh_app()):
            pass


def test_secret_guard_refuses_short_secret_in_prod(monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", "tooshort")
    with pytest.raises(RuntimeError):
        with TestClient(_fresh_app()):
            pass


def test_secret_guard_accepts_strong_secret_in_prod(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", STRONG)
    with TestClient(_fresh_app()) as client:
        assert client.get("/health").status_code == 200


def test_cookie_secure_in_prod(db, monkeypatch):
    monkeypatch.setenv("LQE_ENV", "prod")
    monkeypatch.setenv("LQE_SECRET", STRONG)
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
