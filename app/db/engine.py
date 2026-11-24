"""Engine SQLAlchemy partagé des données linguistiques (ADR-0050).

SQLAlchemy synchrone + psycopg 3, même modèle que `corpus_service._get_engine` : créé
au premier appel, jamais à l'import (aucun I/O au chargement du module).

DETTE TRACÉE (#623 → #624) : en phase 1 le dioula garde son propre engine dans
`corpus_service.py`, qui n'est pas touché ; deux pools coexistent. La phase 2 fait
converger `corpus_service` vers ce module, ce qui le raccourcit.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def get_engine():
    from sqlalchemy import create_engine

    from app.db.url_resolver import resolve_postgres_url

    return create_engine(resolve_postgres_url(raise_on_missing=True), future=True, pool_pre_ping=True)


def message_sur(exc: Exception) -> str:
    """L'exception, lisible dans un journal sans y laisser d'identifiants de connexion.

    `psycopg.OperationalError` peut citer l'URL complète, mot de passe compris. Même règle
    que `corpus_service._safe_error` (dupliquée, même dette que l'engine).
    """
    msg = str(exc)
    if any(motif in msg for motif in ("postgresql+psycopg://", "postgresql://", "password=")):
        return f"{type(exc).__name__} (message masqué — il contient un secret potentiel)"
    return f"{type(exc).__name__}: {msg[:200]}"
