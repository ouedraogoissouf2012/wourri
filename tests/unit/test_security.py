"""
Tests pour app/security.py (issue #222 : dual-key zero-downtime rotation).

Couvre :
    - Clé courante acceptée
    - Clé précédente acceptée quand définie (fenêtre rotation)
    - Clé invalide rejetée (403)
    - Mode dev (clé non configurée) : aucune vérification
"""
from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException


def _reload_security_module(monkeypatch, *, current: str = "", previous: str = ""):
    """Force le rechargement de app.security avec des valeurs env donnees.

    Pourquoi : `app/security.py` lit les cles au moment du `import` (`_settings`
    + `_API_SECRET_KEY` au top-level). Pour tester avec differentes valeurs, on
    doit `reload()` le module apres avoir surcharge les env vars.
    """
    monkeypatch.setenv("API_SECRET_KEY", current)
    monkeypatch.setenv("API_SECRET_KEY_PREVIOUS", previous)

    # Forcer un nouveau Settings() (sinon lru_cache renvoie l'ancien)
    from app.config import get_settings
    get_settings.cache_clear()

    # Recharger app.security pour repreendre les nouvelles env
    import app.security
    importlib.reload(app.security)
    return app.security


@pytest.mark.asyncio
async def test_cle_courante_acceptee(monkeypatch):
    """Clé courante valide → pas d'exception."""
    sec = _reload_security_module(monkeypatch, current="CURRENT_KEY_42")
    # Ne doit pas lever
    await sec.require_api_key(api_key="CURRENT_KEY_42")


@pytest.mark.asyncio
async def test_cle_invalide_rejetee_403(monkeypatch):
    """Clé invalide → HTTPException 403."""
    sec = _reload_security_module(monkeypatch, current="GOOD_KEY")
    with pytest.raises(HTTPException) as exc_info:
        await sec.require_api_key(api_key="WRONG_KEY")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cle_absente_rejetee_403(monkeypatch):
    """Header X-API-Key absent → HTTPException 403."""
    sec = _reload_security_module(monkeypatch, current="GOOD_KEY")
    with pytest.raises(HTTPException) as exc_info:
        await sec.require_api_key(api_key=None)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cle_previous_acceptee_pendant_rotation(monkeypatch):
    """Clé previous définie → acceptée AUSSI (fenêtre rotation zero-downtime)."""
    sec = _reload_security_module(
        monkeypatch,
        current="NEW_KEY_AFTER_ROTATION",
        previous="OLD_KEY_BEFORE_ROTATION",
    )
    # La nouvelle clé est acceptée
    await sec.require_api_key(api_key="NEW_KEY_AFTER_ROTATION")
    # L'ancienne clé est acceptée (fenêtre rotation)
    await sec.require_api_key(api_key="OLD_KEY_BEFORE_ROTATION")
    # Une 3e clé arbitraire est toujours rejetée
    with pytest.raises(HTTPException) as exc_info:
        await sec.require_api_key(api_key="RANDOM_KEY")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cle_previous_vide_seule_courante_acceptee(monkeypatch):
    """Quand previous est vide, seule la clé courante est acceptée
    (= comportement avant issue #222, backward-compatible)."""
    sec = _reload_security_module(monkeypatch, current="ONLY_CURRENT", previous="")
    # Courante OK
    await sec.require_api_key(api_key="ONLY_CURRENT")
    # Une autre clé (qui aurait été acceptée en mode rotation) est rejetée
    with pytest.raises(HTTPException) as exc_info:
        await sec.require_api_key(api_key="WOULD_BE_OLD_KEY")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_mode_dev_aucune_cle_configuree(monkeypatch):
    """Si API_SECRET_KEY vide → mode dev permissif (pas de vérif)."""
    sec = _reload_security_module(monkeypatch, current="", previous="")
    # N'importe quelle clé (ou absence) passe
    await sec.require_api_key(api_key=None)
    await sec.require_api_key(api_key="anything")
