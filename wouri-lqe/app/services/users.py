"""Utilisateurs persistants dans LQE_DATA_DIR/users.json."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from app.data.languages import is_known
from app.data.roles import ALL_ROLES, normalize_roles
from app.paths import data_dir
from app.services.passwords import hash_password

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def users_path():
    return data_dir() / "users.json"


def load_users() -> list[dict]:
    p = users_path()
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("users read: %s", exc)
        return []
    return raw if isinstance(raw, list) else []


def save_users(rows: list[dict]) -> None:
    p = users_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def find_user(username: str) -> dict | None:
    key = username.strip().lower()
    for row in load_users():
        if str(row.get("user") or "").strip().lower() == key:
            return row
    return None


def create_user(*, user: str, password: str, language: str, roles: list[str]) -> dict:
    user = user.strip()
    language = language.strip().lower()
    roles = normalize_roles(roles)
    if not user or len(password) < 8:
        return {"ok": False, "reason": "bad_credentials"}
    if "admin" not in roles and not is_known(language):
        return {"ok": False, "reason": "unknown_language"}
    if "admin" in roles and language != "*":
        language = language if is_known(language) else "*"
    with _lock:
        rows = load_users()
        if any(str(r.get("user") or "").lower() == user.lower() for r in rows):
            return {"ok": False, "reason": "exists"}
        rec = {
            "user": user,
            "password_hash": hash_password(password),
            "language": language if "admin" in roles else language,
            "roles": roles or ["review"],
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if "admin" in rec["roles"]:
            rec["language"] = "*"
        rows.append(rec)
        save_users(rows)
    return {"ok": True, "user": public_user(rec)}


def update_user(username: str, *, roles=None, language=None, active=None, password=None) -> dict:
    with _lock:
        rows = load_users()
        rec = None
        for r in rows:
            if str(r.get("user") or "").lower() == username.strip().lower():
                rec = r
                break
        if not rec:
            return {"ok": False, "reason": "not_found"}
        if roles is not None:
            rec["roles"] = normalize_roles(roles)
        if language is not None:
            lang = language.strip().lower()
            if "admin" in rec["roles"]:
                rec["language"] = "*"
            elif is_known(lang):
                rec["language"] = lang
            else:
                return {"ok": False, "reason": "unknown_language"}
        if active is not None:
            rec["active"] = bool(active)
        if password:
            if len(password) < 8:
                return {"ok": False, "reason": "bad_password"}
            rec["password_hash"] = hash_password(password)
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_users(rows)
    return {"ok": True, "user": public_user(rec)}


def public_user(rec: dict) -> dict:
    return {
        "user": rec.get("user"),
        "language": rec.get("language"),
        "roles": rec.get("roles") or [],
        "active": rec.get("active", True),
    }


def list_public() -> list[dict]:
    return [public_user(r) for r in load_users()]
