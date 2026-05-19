"""Wourri — Alembic environment (Sprint F Phase B — ADR-0008).

Charge la chaîne de connexion Postgres via `app.db.url_resolver.resolve_postgres_url`
(source unique partagée avec `scripts/import_corpus_ivr.py`,
`app/services/corpus_service.py` et `tests/integration/`).

Aucun `target_metadata` (autogénération désactivée) : les migrations sont
écrites à la main en SQL raw pour conserver le contrôle exact sur le schéma
pgvector (colonne `vector(384)`, index ivfflat) et sur l'ordre de création.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Permet à env.py de retrouver `app.config` et `app.db.url_resolver` quand
# `alembic` est appelé depuis `wouri-api/` (cwd documenté dans docs/dev-setup.md).
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Charge .env si présent (cohérent avec uvicorn / pytest).
try:
    from dotenv import load_dotenv

    load_dotenv(_HERE / ".env", override=False)
except ImportError:
    pass

# Import APRÈS l'insertion dans sys.path (sinon `app.db` introuvable).
from app.db.url_resolver import resolve_postgres_url  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Mode offline : émet le SQL sans connexion (utile pour génération de scripts)."""
    url = resolve_postgres_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Mode online : applique les migrations via une connexion live."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = resolve_postgres_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
