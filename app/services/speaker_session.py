"""Session locuteur LQE (#433).

Identité vérifiée via Better Auth (Convex HTTP). Aucun mot de passe stocké
ici. Cookie signé HMAC pour la page FR /speaker/.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "wouri_speaker"
SESSION_TTL_S = 12 * 3600


def _secret() -> bytes:
    s = get_settings()
    raw = (s.api_secret_key or "dev-speaker-only").encode("utf-8")
    return raw


def sign_session(email: str) -> str:
    payload = {
        "email": email.strip().lower(),
        "exp": int(time.time()) + SESSION_TTL_S,
        "lang": "dyu",
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    sig = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_session(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, _, sig = token.rpartition(".")
    expect = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    if not payload.get("email"):
        return None
    return payload


async def verify_better_auth(email: str, password: str) -> bool:
    """POST sign-in Better Auth sur CONVEX_SITE_URL / CONVEX_BASE_URL."""
    settings = get_settings()
    base = (
        getattr(settings, "convex_site_url", "")
        or __import__("os").environ.get("CONVEX_SITE_URL", "")
        or __import__("os").environ.get("CONVEX_BASE_URL", "")
    ).strip().rstrip("/")
    if not base or not email or not password:
        return False
    url = urljoin(base + "/", "api/auth/sign-in/email")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                url,
                json={"email": email.strip(), "password": password},
                headers={"Content-Type": "application/json"},
            )
        if r.status_code < 400:
            return True
        logger.info("[SPEAKER] Better Auth refuse (%s)", r.status_code)
        return False
    except Exception as exc:
        logger.warning("[SPEAKER] Better Auth injoignable (%s)", exc)
        return False
