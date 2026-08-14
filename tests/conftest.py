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
