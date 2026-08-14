"""Tests de chargement du champ config `rate_limit` (issue #310 item 2).

Contrats testés :
- La valeur par défaut de `rate_limit` est bien "120/minute" (ADR-0018) quand
  aucune variable d'environnement RATE_LIMIT n'est présente.
- RATE_LIMIT dans l'environnement surcharge le défaut (chargement Pydantic).

Note d'obsolescence (#310) : l'issue mentionne aussi un champ config
`ffmpeg_path`. Ce champ N'EXISTE PAS dans `Settings` — `FFMPEG_PATH` est lu
directement via `os.getenv` dans `app/services/_ffmpeg.py` (documenté
`app/config.py:207-211`), et cette lecture est déjà testée dans
`test_operational_services.py` (TestFFmpeg). Il n'y a donc rien à tester ici
pour `ffmpeg_path`.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def _restore_config_module(monkeypatch):
    """Recharge app.config avec l'env de session APRÈS le test.

    Chaque test reconstruit `Settings` avec une env dédiée (RATE_LIMIT retiré
    ou surchargé). On restaure l'état par défaut une fois le monkeypatch annulé
    pour ne pas polluer les autres fichiers de tests qui importent app.config
    (le module vit dans sys.modules toute la session pytest)."""
    yield
    monkeypatch.undo()
    import app.config

    app.config.get_settings.cache_clear()
    importlib.reload(app.config)


def _fresh_settings(monkeypatch, **env):
    """Recharge app.config avec une env contrôlée et retourne un Settings neuf.

    `app.config` lit RATE_LIMIT à la construction de `Settings`. Le
    `conftest.py` du projet pose RATE_LIMIT via `setdefault` pour l'hermétisme
    du rate limiting ; pour tester le DÉFAUT du champ il faut donc retirer la
    variable explicitement (`delenv`) avant de reconstruire.
    """
    monkeypatch.delenv("RATE_LIMIT", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import app.config

    app.config.get_settings.cache_clear()
    module = importlib.reload(app.config)
    return module.Settings()


def test_rate_limit_defaut_120_par_minute(monkeypatch):
    """Sans RATE_LIMIT dans l'env, le défaut ADR-0018 s'applique."""
    settings = _fresh_settings(monkeypatch)

    assert settings.rate_limit == "120/minute"


def test_rate_limit_surcharge_par_env(monkeypatch):
    """RATE_LIMIT dans l'env surcharge le défaut au chargement."""
    settings = _fresh_settings(monkeypatch, RATE_LIMIT="42/second")

    assert settings.rate_limit == "42/second"
