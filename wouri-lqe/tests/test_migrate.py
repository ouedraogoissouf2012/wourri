"""Tests du runner de migrations (ADR-0034 P0/P4)."""
import psycopg
import pytest

from app.config import get_settings
from app.data import language_registry as reg
from app.db import get_conn, valid_schema
from app.services import migrate


def _exists(conn, name: str) -> bool:
    # search_path = schema atelier -> to_regclass resout dans ce schema
    return conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0] is not None


def test_migrations_create_schema_and_tables(db):
    with get_conn() as conn:
        for table in ("languages", "assignments", "productions", "media", "schema_migrations"):
            assert _exists(conn, table), f"table absente: {table}"


def test_productions_reconcile_columns(db):
    # migration 002 : colonnes de la bascule flux (backend unique)
    with get_conn() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'productions'"
            ).fetchall()
        }
    assert {"fingerprint", "meta", "promoted_by", "promoted_at"} <= cols


def test_migrations_are_idempotent(db):
    # la fixture a deja migre ; un 2e run n'applique rien
    assert migrate.run_migrations() == []


def test_seed_langues_via_migration():
    # sur une base fraiche (schema droppe -> schema_migrations vide), la migration 003
    # seed dyu/bci. N'utilise PAS `db` (qui truncate languages apres migration).
    schema = valid_schema(get_settings().lqe_db_schema)
    try:
        with get_conn(autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL indisponible: {exc}")
    migrate.run_migrations()
    assert reg.is_known("dyu") and reg.is_known("bci")
    assert reg.get_language("dyu").status == "active"
