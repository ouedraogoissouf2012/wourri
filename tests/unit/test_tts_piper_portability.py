"""
Tests pour la portabilité des modules TTS Piper (fix hardcoding).

Couvre :
    - `_piper_cwd` : dérivation correcte du cwd selon le chemin du binaire
      (None si binaire dans PATH, parent dir si chemin absolu existant)
    - Settings Piper : lecture depuis Pydantic Settings (pas de chemin Windows
      hardcoded dans le code)
    - `synthesize_french` / `synthesize_english` : graceful degradation quand
      le modèle correspondant n'est pas configuré (`PIPER_MODEL_FR` ou
      `PIPER_MODEL_EN` vide)

Ref : règle [[feedback_no_hardcoding]] — JAMAIS de chemin/URL/port en dur.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.tts_french import _piper_cwd, synthesize_french
from app.services.tts_english import synthesize_english


# ─────────────────────────────────────────────
# _piper_cwd : dérivation portable du cwd subprocess
# ─────────────────────────────────────────────


class TestPiperCwdDerivation:
    """Vérifie qu'aucun chemin Windows n'est hardcoded — tout est dérivé."""

    def test_returns_none_for_bare_binary_in_path(self):
        """`piper` seul (binaire dans PATH système) → cwd = None (POSIX standard)."""
        assert _piper_cwd("piper") is None

    def test_returns_none_for_nonexistent_absolute_path(self):
        """Chemin absolu vers un parent qui n'existe pas → None (pas de
        cwd invalide passé au subprocess)."""
        fake_path = "/this/path/does/not/exist/piper"
        assert _piper_cwd(fake_path) is None

    def test_returns_parent_dir_for_real_absolute_path(self, tmp_path: Path):
        """Chemin absolu vers binaire dans dossier existant → cwd = parent dir."""
        fake_binary = tmp_path / "piper"
        fake_binary.write_text("#!/bin/sh\necho fake\n")
        result = _piper_cwd(str(fake_binary))
        assert result == str(tmp_path)

    def test_no_windows_path_hardcoded(self):
        """Vérifie qu'aucun chemin Windows ne sort de cette fonction même si
        l'env var contient un chemin POSIX (anti-régression hardcoding)."""
        # Sur un système POSIX-like, on ne doit jamais voir `C:\` apparaître
        result = _piper_cwd("/usr/local/bin/piper")
        assert result is None or "C:\\" not in (result or "")


# ─────────────────────────────────────────────
# Settings Piper : lecture via Pydantic Settings
# ─────────────────────────────────────────────


class TestPiperSettings:
    """Vérifie que les chemins sont lus depuis config, pas hardcoded."""

    def _isolated_settings(self, monkeypatch):
        """Construit Settings en ignorant le .env du dev local.

        Sans cette isolation, les tests lisent le .env de Ruben (qui contient
        `PIPER_MODEL_FR=C:\\piper-tts\\...`) et les assertions sur les defaults
        Pydantic echouent. Solution : clear les env vars + `_env_file=None`
        pour court-circuiter le chargement .env.
        """
        for var in ("PIPER_PATH", "PIPER_MODEL_FR", "PIPER_MODEL_EN", "PIPER_MODEL"):
            monkeypatch.delenv(var, raising=False)
        from app.config import Settings
        return Settings(_env_file=None)

    def test_default_piper_path_is_portable(self, monkeypatch):
        """Defaut `piper` = binaire dans PATH (universellement portable)."""
        s = self._isolated_settings(monkeypatch)
        # Le defaut doit etre portable (pas un chemin Windows hardcoded)
        assert s.piper_path == "piper" or s.piper_path == ""
        assert "C:\\" not in s.piper_path
        assert ":\\" not in s.piper_path

    def test_default_piper_model_fr_is_empty(self, monkeypatch):
        """Modele FR vide par defaut = graceful degradation (pas crash).

        Isole le .env local pour tester le VRAI defaut Pydantic.
        """
        s = self._isolated_settings(monkeypatch)
        assert s.piper_model_fr == "", \
            f"Defaut piper_model_fr doit etre vide, got {s.piper_model_fr!r}"

    def test_default_piper_model_en_is_empty(self, monkeypatch):
        """Modele EN vide par defaut = graceful degradation."""
        s = self._isolated_settings(monkeypatch)
        assert s.piper_model_en == "", \
            f"Defaut piper_model_en doit etre vide, got {s.piper_model_en!r}"


# ─────────────────────────────────────────────
# Graceful degradation : modèle absent
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesize_french_returns_none_when_model_not_configured():
    """Si `PIPER_MODEL_FR` est vide, synthesize_french retourne None
    sans crasher (graceful degradation pour environnements sans Piper)."""
    with patch("app.services.tts_french.get_settings") as mock_settings:
        mock_settings.return_value.piper_path = "piper"
        mock_settings.return_value.piper_model_fr = ""
        result = await synthesize_french("Bonjour")
    assert result is None


@pytest.mark.asyncio
async def test_synthesize_english_returns_none_when_model_not_configured():
    """Si `PIPER_MODEL_EN` est vide, synthesize_english retourne None
    sans crasher (utile pour les environnements de test/CI sans modèle EN)."""
    with patch("app.services.tts_english.get_settings") as mock_settings:
        mock_settings.return_value.piper_path = "piper"
        mock_settings.return_value.piper_model_en = ""
        result = await synthesize_english("Hello")
    assert result is None


@pytest.mark.asyncio
async def test_synthesize_french_returns_none_for_empty_text():
    """Texte vide → None (court-circuit avant tout appel Piper)."""
    result = await synthesize_french("")
    assert result is None


@pytest.mark.asyncio
async def test_synthesize_english_returns_none_for_empty_text():
    """Texte vide → None (court-circuit avant tout appel Piper)."""
    result = await synthesize_english("")
    assert result is None


# ─────────────────────────────────────────────
# Anti-régression : aucun chemin Windows dans le code des modules TTS
# ─────────────────────────────────────────────


class TestNoHardcodedWindowsPaths:
    """Vérification au niveau code source : grep `C:\\` dans les modules TTS.

    C'est la **règle [[feedback_no_hardcoding]]** appliquée comme test.
    Si une future modification réintroduit un chemin Windows hardcoded, ce
    test échoue automatiquement.
    """

    @pytest.mark.parametrize("module_path", [
        "app/services/tts_french.py",
        "app/services/tts_english.py",
    ])
    def test_no_raw_windows_path(self, module_path):
        """Aucune occurrence de `r"C:\\` dans les modules TTS production."""
        from pathlib import Path as P
        base = P(__file__).resolve().parent.parent.parent
        src = (base / module_path).read_text(encoding="utf-8")
        # Cherche `r"C:\` ou `"C:\\` (raw string ou string normale)
        assert 'r"C:' not in src, f"Chemin Windows hardcoded trouve dans {module_path}"
        assert "'C:\\\\" not in src, f"Chemin Windows hardcoded trouve dans {module_path}"
