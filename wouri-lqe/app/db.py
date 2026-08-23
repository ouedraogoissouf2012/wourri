"""Connexion PostgreSQL (psycopg 3) pour l'atelier — schema configurable.

Pas de pool pour l'instant (service interne, faible charge) : une connexion par
unite de travail. Ajouter un pool (psycopg_pool) reste possible derriere ce meme
point d'entree, sans changer les appelants (dette tracee, ADR-0034 P0).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from app.config import get_settings


def valid_schema(schema: str) -> str:
    """Garde-fou : le nom de schema doit etre un identifiant SQL sur (jamais client)."""
    if not schema.isidentifier():
        raise ValueError(f"schema invalide: {schema!r}")
    return schema


@contextmanager
def get_conn(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Ouvre une connexion avec le search_path pointe sur le schema de l'atelier.

    L'appelant gere le commit (sauf autocommit=True). La connexion est fermee
    a la sortie du contexte.
    """
    settings = get_settings()
    schema = valid_schema(settings.lqe_db_schema)
    conn = psycopg.connect(settings.database_url(), autocommit=autocommit)
    try:
        # search_path reste valable meme si le schema n'existe pas encore (le
        # runner de migrations le cree ensuite). Langue/table = donnee, zero if.
        conn.execute(f'SET search_path TO "{schema}", public')
        yield conn
    finally:
        conn.close()
