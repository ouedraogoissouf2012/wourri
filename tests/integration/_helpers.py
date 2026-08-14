"""Helpers partagés pour les tests d'intégration Wourri.

Consommateurs actuels :
- `postgres_reachable` : test_corpus_schema, test_admin_dashboard_metrics.
- `ml_subprocess_env`  : test_corpus_schema, test_ml_subprocess_stability.
"""
from __future__ import annotations

import os


def ml_subprocess_env(**extra: str) -> dict:
    """Env durci pour tout subprocess Python qui recharge un modèle ML (torch,
    SentenceTransformer, transformers…) alors que le process parent a déjà
    initialisé la même pile numérique.

    Garde OpenMP/MKL — pourquoi il reste (issue #189 + ADR-0011) :
    Sur Windows, torch et SentenceTransformer embarquent chacun une copie du
    runtime Intel OpenMP (`libiomp5md.dll`). Quand un subprocess recharge cette
    pile pendant que le parent l'a déjà chargée, le double-load peut :
      - crasher le subprocess avec ACCESS_VIOLATION `0xC0000005`
        (`returncode=3221225477`) — symptôme observé au smoke Phase D (#189) ;
      - déclencher le `mkl_malloc: failed to allocate memory` documenté dans
        ADR-0011 (§bug du 2026-05-07) sous pression mémoire.
    `KMP_DUPLICATE_LIB_OK=TRUE` autorise explicitement le double-load OpenMP ;
    `OMP_NUM_THREADS=1` réduit la pression thread/mémoire qui aggrave le mkl.

    Ce garde est un **heisenbug environnement-dépendant** (versions de torch /
    MKL / OpenMP, machine, CI). Il n'est plus reproductible sur la config dev
    actuelle (torch 2.13 / ST 5.6, cf. test-sentinelle
    `test_ml_subprocess_stability.py`), mais on le CONSERVE : le retirer parce
    qu'« il ne crashe plus ici » risque de faire revenir le crash sur une autre
    machine/CI, pour un coût nul (ces variables ne changent pas le résultat de
    l'inférence, seulement le chargement des libs). Ne pas prendre pour du
    dead-config : c'est une défense volontaire, tracée #189 + ADR-0011.

    Args:
        **extra: variables à injecter dans l'env (ex. POSTGRES_URL=...).

    Returns:
        Une copie de os.environ + `extra`, sur laquelle le garde OpenMP/MKL est
        appliqué EN DERNIER : il prime toujours, même si `extra` (ou l'env hôte)
        tentait de le désactiver — sinon un caller pourrait involontairement
        rouvrir le crash #189 que cette fonction existe pour prévenir.
    """
    env = os.environ.copy()
    env.update(extra)
    # Garde appliqué en dernier : non-surchargeable par extra/l'env hôte.
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["OMP_NUM_THREADS"] = "1"
    return env


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
