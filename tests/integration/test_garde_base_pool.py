"""#638 — la mesure qui justifie la garde, reproduite sur une vraie base.

Sur les 4 tests unitaires fautifs, UN SEUL ouvrait une connexion ; les 3 autres
réutilisaient celle laissée dans le pool. Ici, un test déclaré ouvre une vraie connexion
et la laisse derrière lui ; le test suivant, non déclaré, s'en sert sans rien ouvrir. La
garde doit le refuser quand même.

Le cas sans base (méthodes de curseur appelées directement) est dans
`tests/unit/test_garde_base.py` ; celui-ci prouve que c'est bien le chemin réel.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.db.url_resolver import resolve_postgres_url

pytestmark = pytest.mark.base_de_donnees

GARDE = Path(__file__).resolve().parents[2] / "tools" / "pytest"

SCENARIO = '''
import os, psycopg, pytest

laissee = []

@pytest.mark.base_de_donnees
def test_1_declare_ouvre_et_laisse_la_connexion():
    url = os.environ["URL_TEST"].replace("postgresql+psycopg://", "postgresql://")
    laissee.append(psycopg.connect(url, autocommit=True))
    assert laissee[0].execute("SELECT 1").fetchone() == (1,)

def test_2_non_declare_reutilise_sans_rien_ouvrir():
    try:
        laissee[0].execute("SELECT 1")
    except Exception:
        pass  # avalé, comme le repli de baoule_ivr
'''


def test_reutiliser_une_connexion_ouverte_par_un_autre_test_est_refuse(tmp_path):
    url = resolve_postgres_url(raise_on_missing=False)
    if not url:
        pytest.skip("POSTGRES_URL absent : la CI, elle, l'a")
    (tmp_path / "test_pool.py").write_text(textwrap.dedent(SCENARIO), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        f"[pytest]\naddopts = -p garde_base -p no:cacheprovider\npythonpath = {GARDE.as_posix()}\n",
        encoding="utf-8",
    )
    env = {**os.environ, "URL_TEST": url}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    sortie = r.stdout + r.stderr
    assert "PASSED test_pool.py::test_1_declare_ouvre_et_laisse_la_connexion" in sortie, sortie
    assert "FAILED test_pool.py::test_2_non_declare_reutilise_sans_rien_ouvrir" in sortie, sortie
    assert "sans le déclarer" in sortie, sortie
