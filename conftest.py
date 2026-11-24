"""Racine des tests du moteur : branche la garde de la base (#638) avant tout le reste.

Un conftest à la racine est le seul point que pytest charge toujours, avant
`tests/conftest.py`, quel que soit le chemin passé en argument. (`addopts = -p
garde_base` ne marche pas : `pythonpath` du pytest.ini n'est appliqué qu'APRÈS l'import des
greffons `-p`.) La garde vit hors de `tests/` parce que l'atelier la partage.
Sa présence est vérifiée par `tests/unit/test_garde_base_branchee.py`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools" / "pytest"))

pytest_plugins = ["garde_base"]
