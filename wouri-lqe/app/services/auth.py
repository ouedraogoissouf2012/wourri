"""Auth cookie — langue portée par le compte, pas par le code."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from app.config import get_settings

SESSION_TTL = 12 * 3600


def _secret() -> bytes:
    return hashlib.sha256(get_settings().lqe_secret.encode("utf-8")).digest()


def verify(username: str, password: str) -> dict | None:
    for acc in get_settings().accounts():
        if hmac.compare_digest(username.strip(), acc["user"]) and hmac.compare_digest(
            password, acc["password"]
        ):
            return acc
    return None


def sign_session(user: str, language: str) -> str:
    payload = {"u": user, "lang": language, "exp": int(time.time()) + SESSION_TTL}
    body = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_session(token: str | None) -> dict | None:
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
    if not payload.get("u") or not payload.get("lang"):
        return None
    return payload
