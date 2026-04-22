# -*- coding: utf-8 -*-
"""
WOURI — Sécurité API

- X-API-Key : authentification simple sur toutes les routes /api/*
- Rate limiting : 10 req/min par IP via slowapi
- La clé est lue depuis .env (API_SECRET_KEY)
  Si non configurée → mode dev permissif (warn uniquement)
"""
import logging
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Rate limiter (partagé, instancié une seule fois) ──────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])

# ── API Key header ─────────────────────────────────────────────────────────────
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
# Lecture via Pydantic Settings (qui charge .env correctement) plutôt que
# os.getenv() qui n'a pas connaissance du .env
_API_SECRET_KEY: str | None = get_settings().api_secret_key or None

if not _API_SECRET_KEY:
    logger.warning(
        "[SECURITY] API_SECRET_KEY non configurée dans .env — "
        "authentification désactivée (mode dev)"
    )


async def require_api_key(api_key: str | None = Depends(_API_KEY_HEADER)) -> None:
    """Dependency FastAPI : vérifie le header X-API-Key.

    Si API_SECRET_KEY n'est pas configurée → pass (mode dev).
    En production, toute requête sans clé valide reçoit un 403.
    """
    if not _API_SECRET_KEY:
        return  # mode dev

    if api_key != _API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clé API invalide ou manquante (header X-API-Key requis)",
        )
