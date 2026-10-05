"""
Fixtures partagées pour tous les tests Wourri.
"""
import os
import sys

# S'assurer que le répertoire racine du projet est dans le PYTHONPATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Issue #215 / ADR-0025 : les tests d'intégration exécutent le lifespan réel
# via TestClient(app) — sans ce garde-fou, la purge de rétention s'exécuterait
# sur le dossier logs/ RÉEL du repo (suppression de fichiers hors tmp_path).
# setdefault : exécuté avant tout import de app.config par les modules de test.
os.environ.setdefault("LOG_RETENTION_ENABLED", "false")

# Issue #307 / ADR-0018 : hermétisme du rate limiting — app/security.py lit le
# .env RÉEL au premier import et le limiter garde ses compteurs en mémoire
# toute la session pytest (IP unique "testclient"). Un RATE_LIMIT bas laissé
# dans le .env d'un poste dev ferait pleuvoir des 429 inexpliqués sur les
# tests d'intégration (échec local non reproductible en CI). Les tests dédiés
# (test_rate_limiting.py) posent leur propre RATE_LIMIT explicitement.
os.environ.setdefault("RATE_LIMIT", "100000/minute")


# ADR-0039 / #550 : le garde LLM escalade désormais les questions non couvertes
# (remontée préventive). Sans ce garde-fou, les tests de handlers qui traversent
# le chemin LLM écriraient de VRAIES tâches dans data/improvement_tasks.jsonl du
# repo. `improvement_queue` expose `DEFAULT_TASKS_PATH` précisément pour cela.
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isoler_file_amelioration(tmp_path_factory, monkeypatch):
    """Redirige la file d'amélioration vers un fichier jetable, pour toute la suite."""
    from app.services import improvement_queue

    cible = tmp_path_factory.mktemp("lqe") / "improvement_tasks.jsonl"
    monkeypatch.setattr(improvement_queue, "DEFAULT_TASKS_PATH", str(cible), raising=False)
    yield
