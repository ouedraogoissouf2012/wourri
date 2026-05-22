"""Helpers partagés pour les tests d'intégration Wourri (Sprint F Phase D).

Pattern Helpers partagés (cf. règles projet Sprint D.4) : extraction déclenchée
au **4e consommateur** (test_corpus_schema + test_corpus_facade + nouveau
test_corpus_divergence_report → seuil atteint).

Avant Phase D, `_postgres_reachable` était dupliqué dans 2 fichiers avec
cross-références inline. Phase D ajoute un 3e/4e fichier → extraction.
"""
from __future__ import annotations


def postgres_reachable(url: str) -> bool:
    """Vérifie qu'on peut ouvrir une connexion + exécuter `SELECT 1` sur Postgres.

    Utilisé par les fixtures `pytestmark = pytest.mark.skipif(...)` au module
    level. Retourne False sur n'importe quelle erreur (URL vide, container down,
    auth fail, etc.) — l'objectif est uniquement de décider du skip.

    Le `engine.dispose()` est explicite : un test rapide ne doit pas laisser
    de connexion ouverte dans le pool (le module est chargé une fois mais
    la fonction peut être appelée plusieurs fois si réimporté).
    """
    if not url:
        return False
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, future=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return True
    except Exception:
        return False
