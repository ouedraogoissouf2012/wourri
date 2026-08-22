"""Auth cookie — langue + rôles portés par le compte."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from app.config import get_settings
from app.data.roles import SPEAKER_ROLES, has_role
from app.services.passwords import verify_password
from app.services.users import find_user

SESSION_TTL = 12 * 3600


def _secret() -> bytes:
    return hashlib.sha256(get_settings().lqe_secret.encode("utf-8")).digest()


def verify(username: str, password: str) -> dict | None:
    name = username.strip()
    rec = find_user(name)
    if rec:
        if not rec.get("active", True):
            return None
        if verify_password(password, rec.get("password_hash") or ""):
            return {
                "user": rec["user"],
                "language": rec.get("language") or "*",
                "roles": rec.get("roles") or [],
            }
        return None
    s = get_settings()
    admin_u = (getattr(s, "lqe_admin_user", "") or "").strip()
    admin_p = getattr(s, "lqe_admin_password", "") or ""
    if admin_u and hmac.compare_digest(name, admin_u) and hmac.compare_digest(password, admin_p):
        return {"user": admin_u, "language": "*", "roles": ["admin", *SPEAKER_ROLES]}
    for acc in s.accounts():
        if hmac.compare_digest(name, acc["user"]) and hmac.compare_digest(password, acc["password"]):
            return {
                "user": acc["user"],
                "language": acc["language"],
                "roles": list(SPEAKER_ROLES),
            }
    return None


def sign_session(user: str, language: str, roles: list) -> str:
    payload = {
        "u": user,
        "lang": language,
        "roles": list(roles or []),
        "exp": int(time.time()) + SESSION_TTL,
    }
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
    if not payload.get("u"):
        return None
    payload.setdefault("roles", [])
    payload.setdefault("lang", "*")
    return payload


def session_has(sess: dict, role: str) -> bool:
    return has_role(sess.get("roles"), role)
