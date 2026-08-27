"""Runner de migrations SQL versionnees pour le schema de l'atelier (ADR-0034 P0).

Applique dans l'ordre les fichiers db/migrations/NNN_*.sql non encore appliques.
Suivi dans <schema>.schema_migrations. Idempotent, un commit par migration.

Garde-fou (issue #493) : le decoupage se fait sur ';', mais un ';' cache dans un
litteral SQL est REFUSE par une erreur qui nomme le fichier et la ligne. Tout le lot
en attente est analyse AVANT la premiere execution : une migration indecoupable n'en
laisse donc aucune a moitie appliquee. Voir app/services/sql_script.py.
"""
from __future__ import annotations

from pathlib import Path

import psycopg

from app.config import get_settings
from app.db import get_conn, valid_schema
from app.services.sql_script import split_statements

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"

# Cle advisory fixe ("LQE") : serialise les runners de migration concurrents.
_LOCK_KEY = 0x4C5145


def _bootstrap(conn: psycopg.Connection, schema: str) -> None:
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version text PRIMARY KEY,"
        " applied_at timestamptz NOT NULL DEFAULT now())"
    )


def _applied(conn: psycopg.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}


def run_migrations(*, migrations_dir: Path | None = None) -> list[str]:
    """Applique les migrations manquantes. Retourne la liste des versions appliquees."""
    schema = valid_schema(get_settings().lqe_db_schema)
    directory = migrations_dir or MIGRATIONS_DIR
    applied_now: list[str] = []
    with get_conn(autocommit=False) as conn:
        # Verrou de session : serialise les runners concurrents (workers uvicorn au boot).
        # Libere automatiquement a la fermeture de la connexion (fin du contexte get_conn).
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        _bootstrap(conn, schema)
        conn.commit()
        done = _applied(conn)
        # Garde-fou #493 : tout le lot en attente est analyse d'abord. Une migration
        # indecoupable (';' dans un litteral) leve SqlScriptError en nommant fichier
        # et ligne, avant que la moindre migration du lot ne soit appliquee.
        pending = [p for p in sorted(directory.glob("*.sql")) if p.stem not in done]
        parsed = [
            (path, split_statements(path.read_text(encoding="utf-8"), origin=path.name))
            for path in pending
        ]
        for path, statements in parsed:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,)
            )
            conn.commit()
            applied_now.append(path.stem)
    return applied_now

