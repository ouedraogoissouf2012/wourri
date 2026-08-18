"""Auth simple provider Baoulé — user + mot de passe (env Dokploy).

Pas un 2e Better Auth : compte atelier local pour /admin/baoule/.
Variables :
  BAOULE_PROVIDER_USER
  BAOULE_PROVIDER_PASSWORD
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

COOKIE_NAME = "wouri_baoule_provider"
SESSION_TTL_S = 12 * 3600


def _creds() -> tuple[str, str]:
    user = (os.getenv("BAOULE_PROVIDER_USER") or "").strip()
    password = (os.getenv("BAOULE_PROVIDER_PASSWORD") or "").strip()
    return user, password


def is_configured() -> bool:
    u, p = _creds()
    return bool(u and p and len(p) >= 8)


def verify_password(username: str, password: str) -> bool:
    u, p = _creds()
    if not u or not p:
        return False
    return hmac.compare_digest(username.strip(), u) and hmac.compare_digest(
        password, p
    )


def _secret() -> bytes:
    # Dérivé du mdp provider + user (pas besoin d'une 3e clé)
    u, p = _creds()
    base = (os.getenv("API_SECRET_KEY") or "") + "|" + u + "|" + p
    return hashlib.sha256(base.encode("utf-8")).digest()


def sign_session(username: str) -> str:
    payload = {
        "u": username.strip(),
        "exp": int(time.time()) + SESSION_TTL_S,
        "role": "baoule_provider",
    }
    body = json.dumps(payload, separators=(",", ":"))
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
    if payload.get("role") != "baoule_provider":
        return None
    return payload
