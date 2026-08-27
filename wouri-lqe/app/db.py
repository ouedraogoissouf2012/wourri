"""Connexion PostgreSQL (psycopg 3) pour l'atelier — schema configurable, pool derriere.

Tous les appelants passent par le meme context manager `get_conn()` : le pool
(psycopg_pool.ConnectionPool) est branche DERRIERE ce point d'entree, sans changer une
ligne chez eux (issue #494, dette tracee ADR-0034 P0).

Semantique identique a la connexion par unite de travail qu'il remplace :
- `search_path` pointe sur le schema de l'atelier (applique une fois par connexion
  physique, pas a chaque emprunt) ;
- l'appelant gere le commit (sauf autocommit=True) : rien n'est valide implicitement
  en sortie de contexte, ce qui reste ouvert est annule ;
- une base injoignable leve toujours psycopg.OperationalError (PoolTimeout en herite).

Reglages (env) : LQE_DB_POOL_ENABLED, LQE_DB_POOL_MIN_SIZE, LQE_DB_POOL_MAX_SIZE,
LQE_DB_POOL_TIMEOUT. LQE_DB_POOL_ENABLED=false retablit une connexion par unite de
travail — soupape pour isoler un probleme de pool sans redeployer du code.

Attention : une connexion rendue au pool n'est PAS fermee. Tout etat de session
(verrou advisory, table temporaire) doit donc etre libere explicitement par son
appelant — voir services/migrate.py.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from app.config import Settings, get_settings

# Pool unique du processus, cree a la premiere demande. Recree si la configuration
# (DSN, schema, taille, timeout) change : la prod n'en cree qu'un, les tests basculent.
_pool: ConnectionPool | None = None
_pool_key: tuple | None = None
_pool_lock = threading.Lock()


def valid_schema(schema: str) -> str:
    """Garde-fou : le nom de schema doit etre un identifiant SQL sur (jamais client)."""
    if not schema.isidentifier():
        raise ValueError(f"schema invalide: {schema!r}")
    return schema


@contextmanager
def get_conn(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Ouvre une connexion avec le search_path pointe sur le schema de l'atelier.

    L'appelant gere le commit (sauf autocommit=True). La connexion est rendue au pool
    (ou fermee si le pool est desactive) a la sortie du contexte.
    """
    settings = get_settings()
    schema = valid_schema(settings.lqe_db_schema)
    acquire = _pooled if settings.lqe_db_pool_enabled else _dedicated
    with acquire(settings, schema, autocommit) as conn:
        yield conn


@contextmanager
def _dedicated(
    settings: Settings, schema: str, autocommit: bool
) -> Iterator[psycopg.Connection]:
    """Une connexion par unite de travail, fermee en sortie (pool desactive)."""
    conn = psycopg.connect(settings.database_url(), autocommit=autocommit)
    try:
        conn.execute(f'SET search_path TO "{schema}", public')
        yield conn
    finally:
        conn.close()


@contextmanager
def _pooled(
    settings: Settings, schema: str, autocommit: bool
) -> Iterator[psycopg.Connection]:
    """Une connexion empruntee au pool, rendue — jamais fermee — en sortie."""
    pool = _get_pool(settings, schema)
    conn = pool.getconn()
    try:
        conn.autocommit = autocommit
        yield conn
    finally:
        _return_to_pool(pool, conn)


def _return_to_pool(pool: ConnectionPool, conn: psycopg.Connection) -> None:
    """Rend la connexion sans rien valider : meme effet qu'une fermeture."""
    try:
        if conn.autocommit:
            conn.autocommit = False  # etat par defaut du pool (aucune transaction ici)
        else:
            conn.rollback()  # ce que l'appelant n'a pas commite est perdu, comme avant
    except psycopg.Error:
        pass  # connexion cassee : putconn la remplace par une neuve
    pool.putconn(conn)


def _get_pool(settings: Settings, schema: str) -> ConnectionPool:
    """Pool du processus, recree si la configuration a change depuis sa creation."""
    global _pool, _pool_key
    key = (
        settings.database_url(),
        schema,
        settings.lqe_db_pool_min_size,
        settings.lqe_db_pool_max_size,
        settings.lqe_db_pool_timeout,
    )
    with _pool_lock:
        if _pool is not None and _pool_key == key and not _pool.closed:
            return _pool
        _close_pool_locked()
        pool = ConnectionPool(
            key[0],
            name="lqe",
            min_size=settings.lqe_db_pool_min_size,
            max_size=settings.lqe_db_pool_max_size,
            timeout=settings.lqe_db_pool_timeout,
            configure=lambda conn: _configure(conn, schema),
            # Une connexion morte (redemarrage Postgres) est remplacee a l'emprunt au
            # lieu de faire echouer la requete de l'appelant.
            check=ConnectionPool.check_connection,
            open=False,
        )
        pool.open()
        _pool, _pool_key = pool, key
        return pool


def _configure(conn: psycopg.Connection, schema: str) -> None:
    """search_path applique une fois par connexion physique, a sa creation.

    Le commit est indispensable : un SET est transactionnel, donc annule par le
    rollback de recyclage du pool s'il n'est pas valide.

    search_path reste valable meme si le schema n'existe pas encore (le runner de
    migrations le cree ensuite). Langue/table = donnee, zero if.
    """
    conn.execute(f'SET search_path TO "{schema}", public')
    conn.commit()


def close_pool() -> None:
    """Ferme le pool : arret de l'application, ou bascule de configuration en test."""
    with _pool_lock:
        _close_pool_locked()


def _close_pool_locked() -> None:
    global _pool, _pool_key
    if _pool is not None:
        _pool.close()
        _pool, _pool_key = None, None
