"""
Tests pour app/config.py::_read_file_secret + get_settings() override
(issue #213 Docker secrets pattern *_FILE).

Couvre :
    - Fichier présent → contenu retourné, strip appliqué
    - Env var FILE absente → "" (backward-compat)
    - Fichier référencé mais introuvable → "" (no-op, log absent volontairement)
    - get_settings() : API_SECRET_KEY_FILE override la valeur du .env
    - get_settings() : API_SECRET_KEY_PREVIOUS_FILE override
"""
from __future__ import annotations

import importlib

import pytest


def _reload_config(monkeypatch, env: dict[str, str]):
    """Force le rechargement de app.config avec env contrôlée."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from app.config import get_settings

    get_settings.cache_clear()
    import app.config

    importlib.reload(app.config)
    return app.config


# ─────────────────────────────────────────────
# _read_file_secret
# ─────────────────────────────────────────────


def test_read_file_secret_fichier_present(monkeypatch, tmp_path):
    """Fichier existe → contenu retourné avec strip."""
    secret_file = tmp_path / "api_secret_key"
    secret_file.write_text("  my_secret_value  \n", encoding="utf-8")
    monkeypatch.setenv("API_SECRET_KEY_FILE", str(secret_file))

    from app.config import _read_file_secret

    assert _read_file_secret("API_SECRET_KEY") == "my_secret_value"


def test_read_file_secret_env_var_absente_retourne_vide(monkeypatch):
    """Si {NAME}_FILE n'est pas défini → "" (backward-compat)."""
    monkeypatch.delenv("API_SECRET_KEY_FILE", raising=False)

    from app.config import _read_file_secret

    assert _read_file_secret("API_SECRET_KEY") == ""


def test_read_file_secret_fichier_introuvable_retourne_vide(monkeypatch, tmp_path):
    """Si le fichier référencé n'existe pas → "" (no-op silencieux)."""
    nonexistent = tmp_path / "definitely_not_here"
    monkeypatch.setenv("API_SECRET_KEY_FILE", str(nonexistent))

    from app.config import _read_file_secret

    assert _read_file_secret("API_SECRET_KEY") == ""


def test_read_file_secret_path_vide_retourne_vide(monkeypatch):
    """API_SECRET_KEY_FILE="" (chaîne vide) → "" (pas de KeyError)."""
    monkeypatch.setenv("API_SECRET_KEY_FILE", "")

    from app.config import _read_file_secret

    assert _read_file_secret("API_SECRET_KEY") == ""


# ─────────────────────────────────────────────
# get_settings() override
# ─────────────────────────────────────────────


def test_get_settings_override_api_secret_key_depuis_fichier(monkeypatch, tmp_path):
    """API_SECRET_KEY_FILE override la valeur de .env / env var directe."""
    secret_file = tmp_path / "api_secret_key"
    secret_file.write_text("file_based_secret", encoding="utf-8")

    cfg = _reload_config(
        monkeypatch,
        {
            "API_SECRET_KEY": "env_based_secret",         # ← devrait etre IGNORE
            "API_SECRET_KEY_FILE": str(secret_file),
        },
    )

    s = cfg.get_settings()
    # Le fichier override l'env var
    assert s.api_secret_key == "file_based_secret"


# NOTE : test API_SECRET_KEY_PREVIOUS_FILE differe a une PR de suivi apres
# le merge de PR #245 (issue #222 dual-key, qui introduit le champ
# api_secret_key_previous dans Settings).


def test_get_settings_pas_de_file_env_garde_valeur_env(monkeypatch):
    """Pas de *_FILE env vars → valeurs lues depuis .env normales
    (backward-compat preserved)."""
    monkeypatch.delenv("API_SECRET_KEY_FILE", raising=False)
    monkeypatch.delenv("API_SECRET_KEY_PREVIOUS_FILE", raising=False)
    cfg = _reload_config(
        monkeypatch,
        {
            "API_SECRET_KEY": "from_env_only",
        },
    )
    s = cfg.get_settings()
    assert s.api_secret_key == "from_env_only"
