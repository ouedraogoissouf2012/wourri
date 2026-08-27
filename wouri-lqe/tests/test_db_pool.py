"""Tests du pool de connexions branche derriere get_conn (issue #494).

Le contrat verifie ici est celui des appelants : aucun d'eux n'a change, donc la
semantique de get_conn ne doit pas changer non plus. Seul le cout d'obtention d'une
connexion change.
"""
from __future__ import annotations

import threading

import psycopg
import pytest

from app import db as db_module
from app.config import get_settings
from app.db import close_pool, get_conn


@pytest.fixture(autouse=True)
def _pool_actif(monkeypatch):
    """Ces tests decrivent le pool : ils ne doivent pas dependre de l'environnement
    ambiant, ou LQE_DB_POOL_ENABLED peut avoir ete mis a false (soupape)."""
    monkeypatch.setenv("LQE_DB_POOL_ENABLED", "true")


def _backend_pid() -> int:
    """PID du backend Postgres servant une unite de travail (= identite de connexion)."""
    with get_conn() as conn:
        return conn.execute("SELECT pg_backend_pid()").fetchone()[0]


def test_le_pool_reutilise_la_connexion(db, monkeypatch):
    # Pool borne a 1 : les cinq unites de travail passent par la MEME connexion
    # physique. Le pool par defaut en garde plusieurs et tourne de l'une a l'autre.
    monkeypatch.setenv("LQE_DB_POOL_MIN_SIZE", "1")
    monkeypatch.setenv("LQE_DB_POOL_MAX_SIZE", "1")
    assert len({_backend_pid() for _ in range(5)}) == 1


def test_le_pool_borne_le_nombre_de_connexions(db, monkeypatch):
    monkeypatch.setenv("LQE_DB_POOL_MAX_SIZE", "2")
    assert len({_backend_pid() for _ in range(8)}) <= 2


def test_sans_pool_chaque_unite_de_travail_ouvre_sa_connexion(db, monkeypatch):
    monkeypatch.setenv("LQE_DB_POOL_ENABLED", "false")
    assert len({_backend_pid() for _ in range(5)}) == 5


def test_search_path_identique_avec_et_sans_pool(db, monkeypatch):
    with get_conn() as conn:
        avec_pool = conn.execute("SHOW search_path").fetchone()[0]
    monkeypatch.setenv("LQE_DB_POOL_ENABLED", "false")
    with get_conn() as conn:
        sans_pool = conn.execute("SHOW search_path").fetchone()[0]
    assert avec_pool == sans_pool
    assert get_settings().lqe_db_schema in avec_pool


def test_autocommit_est_respecte(db):
    with get_conn(autocommit=True) as conn:
        assert conn.autocommit is True
    with get_conn() as conn:
        assert conn.autocommit is False


def test_aucun_commit_implicite_en_sortie_de_contexte(db, seeded):
    # L'appelant gere le commit : sans commit, l'ecriture est perdue — exactement ce
    # que faisait la fermeture de connexion avant le pool.
    with get_conn() as conn:
        conn.execute("INSERT INTO productions (language, text_local) VALUES ('dyu', 'sans commit')")
    with get_conn() as conn:
        restant = conn.execute(
            "SELECT count(*) FROM productions WHERE text_local = 'sans commit'"
        ).fetchone()[0]
    assert restant == 0


def test_commit_explicite_est_conserve(db, seeded):
    with get_conn() as conn:
        conn.execute("INSERT INTO productions (language, text_local) VALUES ('dyu', 'avec commit')")
        conn.commit()
    with get_conn() as conn:
        restant = conn.execute(
            "SELECT count(*) FROM productions WHERE text_local = 'avec commit'"
        ).fetchone()[0]
    assert restant == 1


def test_transaction_en_erreur_ne_contamine_pas_l_emprunt_suivant(db):
    with pytest.raises(psycopg.errors.UndefinedTable):
        with get_conn() as conn:
            conn.execute("SELECT 1 FROM table_qui_nexiste_pas")
    with get_conn() as conn:  # connexion rendue assainie, la suivante est utilisable
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_deux_unites_de_travail_simultanees_ont_deux_connexions(db):
    depart = threading.Barrier(2, timeout=15)
    verrou = threading.Lock()
    pids: list[int] = []

    def travail() -> None:
        with get_conn() as conn:
            pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
            with verrou:
                pids.append(pid)
            depart.wait()  # les deux connexions restent prises en meme temps

    fils = [threading.Thread(target=travail) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=20)
    assert len(pids) == 2
    assert pids[0] != pids[1]


def test_taille_du_pool_configurable_via_env(db, monkeypatch):
    monkeypatch.setenv("LQE_DB_POOL_MIN_SIZE", "2")
    monkeypatch.setenv("LQE_DB_POOL_MAX_SIZE", "3")
    with get_conn() as conn:
        conn.execute("SELECT 1")
    assert (db_module._pool.min_size, db_module._pool.max_size) == (2, 3)


def test_pool_rouvert_apres_fermeture(db):
    close_pool()
    assert db_module._pool is None
    with get_conn() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    assert db_module._pool is not None
