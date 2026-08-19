"""Empreinte stable — dédup sans hardcoder une langue."""
from __future__ import annotations

import hashlib


def fingerprint(*, language: str, text_local: str, text_fr: str = "", external_id: str | None = None) -> str:
    if external_id:
        return f"ext:{(language or '').lower()}:{external_id.strip().lower()}"
    raw = "|".join(
        [
            (language or "").strip().lower(),
            " ".join((text_local or "").strip().lower().split()),
            " ".join((text_fr or "").strip().lower().split()),
        ]
    )
    return "h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
