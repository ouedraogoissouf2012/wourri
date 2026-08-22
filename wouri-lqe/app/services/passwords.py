"""Hash mot de passe PBKDF2 — pas de clair sur disque."""
from __future__ import annotations

import hashlib
import hmac
import os


def hash_password(plain: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(plain: str, stored: str) -> bool:
    if not stored or ":" not in stored:
        return False
    salt_h, dk_h = stored.split(":", 1)
    try:
        salt = bytes.fromhex(salt_h)
        expect = bytes.fromhex(dk_h)
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(got, expect)
