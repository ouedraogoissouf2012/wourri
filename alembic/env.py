"""Wourri — Alembic environment (Sprint F Phase B — ADR-0008).

Charge la chaîne de connexion Postgres depuis :
1. la variable d'environnement `POSTGRES_URL` (priorité),
2. ou directement depuis l'objet `Settings` (via `.env`).

Aucun `target_metadata` (autogénération désactivée) : les migrations sont
écrites à la main en SQL raw pour conserver le contrôle exact sur le schéma
pgvector (colonne `vector(384)`, index ivfflat) et sur l'ordre de création.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Permet à env.py de retrouver `app.config` quand `alembic` est appelé
# depuis `wouri-api/` (cwd standard documenté dans `docs/dev-setup.md`).
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Charge .env si présent (cohérent avec uvicorn / pytest).
try:
    from dotenv import load_dotenv

    load_dotenv(_HERE / ".env", override=False)
except ImportError:
    pass

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _resolve_url() -> str:
    """Retourne l'URL Postgres en respectant l'ordre de priorité.

    NB — duplication intentionnelle (seuil projet d'extraction = 4 consommateurs,
    cf. règles DRY Sprint D.4). Copies parallèles :
    - `scripts/import_corpus_ivr.py::_resolve_url`   (même contrat : lève RuntimeError)
    - `tests/integration/test_corpus_schema.py::_resolve_url`
       (contrat DIVERGENT : retourne `""` au lieu de lever — utilisé par
        `pytest.mark.skipif` pour skip le module si Postgres indisponible)
    Phase C ajoutera un 4e consommateur (`app/services/corpus_service.py`) :
    déclenchera l'extraction vers `app/db/url_resolver.py`.
    """
    url = os.getenv("POSTGRES_URL", "").strip()
    if url:
        return url

    try:
        from app.config import get_settings

        settings_url = (get_settings().postgres_url or "").strip()
        if settings_url:
            return settings_url
    except Exception:
        pass

    raise RuntimeError(
        "POSTGRES_URL n'est pas définie. Renseignez-la dans wouri-api/.env "
        "(cf. .env.example) ou exportez-la dans l'environnement avant "
        "d'invoquer `alembic`."
    )


def run_migrations_offline() -> None:
    """Mode offline : émet le SQL sans connexion (utile pour génération de scripts)."""
    url = _resolve_url()
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
    section["sqlalchemy.url"] = _resolve_url()

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
