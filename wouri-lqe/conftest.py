"""Racine des tests de l'atelier : branche la garde de la base (#638), partagée avec le
moteur (`../tools/pytest/garde_base.py`), avant `tests/conftest.py`.

Même mécanisme que le conftest racine du moteur, par un autre chemin : le câblage peut
casser d'un seul côté, d'où un test de branchement dans chaque suite
(`tests/test_garde_base_atelier.py::test_la_garde_est_branchee_dans_cette_session`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "pytest"))

pytest_plugins = ["garde_base"]
