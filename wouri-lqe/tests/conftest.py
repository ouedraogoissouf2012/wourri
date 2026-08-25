"""Fixtures partagées des tests atelier (ADR-0034).

`db` : migre le schéma puis nettoie les tables avant chaque test. Si aucun
PostgreSQL n'est joignable (dev local sans base), les tests qui la demandent
sont **skippés** (pas échoués) ; en CI le service Postgres est présent, donc ils
s'exécutent réellement. Un skip ne masque jamais un bug (on ne skippe que sur
erreur de connexion).

`corpus` : table `public.corpus_entries` de test (simule le corpus IVR du moteur)
pour exercer le pont lecture seule (P1).
"""
from __future__ import annotations

import psycopg
import pytest

from app.db import get_conn
from app.services.migrate import run_migrations

_TABLES = "languages, assignments, productions, media, dictation"


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


@pytest.fixture
def seeded(db):
    """Langues pilotes actives (dyu, bci) — requises par le flux (FK productions.language
    + is_known). Re-seed apres le TRUNCATE de `db` (qui laisse `languages` vide, ce que
    `test_language_registry` exige)."""
    from app.data import language_registry as reg

    reg.upsert_language("dyu", "Dioula", status="active")
    reg.upsert_language("bci", "Baoule", status="active")
    yield


@pytest.fixture
def corpus(db):
    """Corpus IVR de reference simule (`public.corpus_entries`) : 2 concepts."""
    with get_conn(autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.corpus_entries ("
            " id text PRIMARY KEY, intent text,"
            " cultures text[] NOT NULL DEFAULT '{}',"
            " conditions text[] NOT NULL DEFAULT '{}',"
            " reponse_bambara text, reponse_fr text)"
        )
        conn.execute("TRUNCATE public.corpus_entries")
        conn.execute(
            "INSERT INTO public.corpus_entries"
            " (id, intent, cultures, reponse_bambara, reponse_fr) VALUES"
            " ('mais_conseil_001', 'CONSEIL_PRODUCTION', ARRAY['CULTURE_MAIS'], 'Aw ye kaba sene', 'Plante ton mais'),"
            " ('riz_conseil_001', 'CONSEIL_PRODUCTION', ARRAY['CULTURE_RIZ'], 'Aw ye malo sene', 'Plante ton riz')"
        )
    yield
