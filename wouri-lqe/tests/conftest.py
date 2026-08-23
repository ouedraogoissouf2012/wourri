"""Fixtures partagées des tests atelier (ADR-0034 P0).

La fixture `db` : migre le schéma puis nettoie les tables avant chaque test.
Si aucun PostgreSQL n'est joignable (dev local sans base), les tests qui la
demandent sont **skippés** (pas échoués) ; en CI le service Postgres est présent,
donc ils s'exécutent réellement. Un skip ne masque JAMAIS un bug de migration
(on ne skippe que sur erreur de connexion).
"""
from __future__ import annotations

import psycopg
import pytest

from app.db import get_conn
from app.services.migrate import run_migrations

_TABLES = "languages, assignments, productions, media"


@pytest.fixture
def db():
    try:
        with get_conn(autocommit=True) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL indisponible: {exc}")
    run_migrations()  # idempotent ; un échec ici est un vrai bug, pas un skip
    with get_conn(autocommit=True) as conn:
        conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    yield
