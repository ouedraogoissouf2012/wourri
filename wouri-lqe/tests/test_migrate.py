"""Tests du runner de migrations (ADR-0034 P0)."""
from app.db import get_conn
from app.services import migrate


def _exists(conn, name: str) -> bool:
    # search_path = schema atelier -> to_regclass resout dans ce schema
    return conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0] is not None


def test_migrations_create_schema_and_tables(db):
    with get_conn() as conn:
        for table in ("languages", "assignments", "productions", "media", "schema_migrations"):
            assert _exists(conn, table), f"table absente: {table}"


def test_migrations_are_idempotent(db):
    # la fixture a deja migre ; un 2e run n'applique rien
    assert migrate.run_migrations() == []
