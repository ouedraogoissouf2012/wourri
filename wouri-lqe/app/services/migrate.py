"""Runner de migrations SQL versionnees pour le schema de l'atelier (ADR-0034 P0).

Applique dans l'ordre les fichiers db/migrations/NNN_*.sql non encore appliques.
Suivi dans <schema>.schema_migrations. Idempotent, un commit par migration.

Limite assumee (DDL controle) : le decoupage se fait sur ';' — donc pas de ';'
dans un litteral de migration.
"""
from __future__ import annotations

from pathlib import Path

import psycopg

from app.config import get_settings
from app.db import get_conn, valid_schema

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


def _statements(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


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
        _bootstrap(conn, schema)
        conn.commit()
        done = _applied(conn)
        for path in sorted(directory.glob("*.sql")):
            version = path.stem
            if version in done:
                continue
            for stmt in _statements(path.read_text(encoding="utf-8")):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            conn.commit()
            applied_now.append(version)
    return applied_now
