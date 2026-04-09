"""
Fixtures partagées pour tous les tests Wourri.
"""
import os
import sys

# S'assurer que le répertoire racine du projet est dans le PYTHONPATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
