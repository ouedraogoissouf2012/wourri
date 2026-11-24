"""La garde de la base (#638), côté atelier : la fixture `db` VAUT déclaration, et même
déclarée elle n'atteint qu'une base jetable — refusée AVANT `run_migrations` et AVANT le
TRUNCATE, sans un octet sur le réseau.

Chaque cas tourne dans une vraie session pytest en sous-processus, avec la vraie fixture
`db` de `tests/conftest.py` et un faux serveur qui compte les connexions reçues. La
garde elle-même est prouvée dans `wouri-api/tests/unit/test_garde_base.py`.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ATELIER = Path(__file__).resolve().parents[1]
GARDE = ATELIER.parent / "tools" / "pytest"

CONFTEST = '''
import json, os
import tests.conftest as atelier
from tests.conftest import db, pytest_collection_modifyitems  # la vraie fixture, la vraie déclaration

appels = {"run_migrations": 0}
_vraie = atelier.run_migrations

def _espion(*a, **k):
    appels["run_migrations"] += 1
    return _vraie(*a, **k)

atelier.run_migrations = _espion

def pytest_sessionfinish(session):
    with open(os.environ["ESPION"], "w", encoding="utf-8") as f:
        json.dump(appels, f)
'''

TESTS = '''
from app.db import get_conn

def test_demande_db(db):
    pass

def test_drop_schema_sans_declaration():
    with get_conn(autocommit=True) as conn:  # la forme exacte de test_migrate / test_startup
        conn.execute('DROP SCHEMA IF EXISTS "lqe" CASCADE')
'''


class _Ecoute:
    def __init__(self):
        self._s = socket.create_server(("127.0.0.1", 0))
        self._s.settimeout(0.1)
        self.port = self._s.getsockname()[1]
        self.acceptees = 0
        self._fin = threading.Event()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def _boucle(self):
        while not self._fin.is_set():
            try:
                conn, _ = self._s.accept()
            except OSError:
                continue
            self.acceptees += 1
            conn.close()

    def fermer(self):
        self._fin.set()
        self._fil.join()
        self._s.close()


def _session(tmp_path: Path, base: str, test: str):
    """UN test de la suite miniature, contre `base` -> (issues, appels espionnés, connexions
    reçues, sortie). Un seul par session : le pool de l'atelier est neuf, sa première
    tentative tombe pendant CE test (un pool en attente de reconnexion la décalerait)."""
    (tmp_path / "conftest.py").write_text(textwrap.dedent(CONFTEST), encoding="utf-8")
    (tmp_path / "test_mini.py").write_text(textwrap.dedent(TESTS), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        f"[pytest]\naddopts = -p garde_base -p no:cacheprovider\npythonpath = {ATELIER.as_posix()}\n",
        encoding="utf-8",
    )
    ecoute = _Ecoute()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("POSTGRES", "PG", "LQE_"))}
    # PYTHONPATH pour la garde : `pythonpath` du pytest.ini s'applique après les greffons `-p`.
    env.update(PYTHONPATH=str(GARDE), POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=str(ecoute.port), POSTGRES_USER="u",
               POSTGRES_PASSWORD="p", POSTGRES_DB=base, LQE_DB_SCHEMA="lqe",
               LQE_DB_POOL_TIMEOUT="1", ESPION=str(tmp_path / "espion.json"))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml=rapport.xml", f"test_mini.py::{test}"],
                           cwd=tmp_path, env=env, capture_output=True, text=True, timeout=180)
    finally:
        ecoute.fermer()
    issues = {}
    for cas in ET.parse(tmp_path / "rapport.xml").getroot().iter("testcase"):
        el = next((cas.find(b) for b in ("failure", "error", "skipped") if cas.find(b) is not None), None)
        texte = "" if el is None else (el.get("message") or "") + "\n" + (el.text or "")
        issues[cas.get("name")] = ("passed" if el is None else el.tag, texte)
    appels = json.loads((tmp_path / "espion.json").read_text(encoding="utf-8"))
    return issues, appels, ecoute.acceptees, r.stdout + r.stderr


def test_db_sur_une_base_non_jetable_est_refusee_avant_toute_ecriture(tmp_path):
    issues, appels, acceptees, sortie = _session(tmp_path, "wourri_dev", "test_demande_db")
    issue, texte = issues["test_demande_db"]
    assert issue in ("failure", "error"), sortie
    # « non jetable » et non « sans le déclarer » : demander `db` a bien valu déclaration.
    assert "base non jetable : wourri_dev (attendu : un nom finissant par `_test`)" in texte, texte
    assert appels["run_migrations"] == 0, "la migration a tourné AVANT le refus"
    assert acceptees == 0, "le refus est arrivé APRÈS le réseau"


def test_db_sur_une_base_jetable_est_autorisee(tmp_path):
    issues, appels, acceptees, sortie = _session(tmp_path, "atelier_garde_test", "test_demande_db")
    # Le faux serveur raccroche : la fixture saute (« PostgreSQL indisponible »), comme
    # sans base — mais la connexion l'a ATTEINT, ce qui prouve que la garde l'a laissée passer.
    assert issues["test_demande_db"][0] == "skipped", sortie
    assert acceptees >= 1, sortie


def test_drop_schema_hors_fixture_sans_declaration_est_refuse(tmp_path):
    issues, _, _, sortie = _session(tmp_path, "atelier_garde_test", "test_drop_schema_sans_declaration")
    issue, texte = issues["test_drop_schema_sans_declaration"]
    assert issue in ("failure", "error") and "sans le déclarer" in texte, f"{issue}\n{texte}\n{sortie}"



def test_la_garde_est_branchee_dans_cette_session(request):
    """Les tests ci-dessus prouvent que la garde fonctionne ; celui-ci, qu'elle est
    branchée ICI (`../tools/pytest`, un autre chemin que celui du moteur)."""
    import psycopg

    assert request.config.pluginmanager.has_plugin("garde_base"), (
        "garde_base absente de la session : voir addopts et pythonpath dans wouri-lqe/pytest.ini"
    )
    assert hasattr(psycopg.Cursor.execute, "__garde__"), "garde chargée mais psycopg non surveillé"
