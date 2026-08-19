"""Registre des langues — étendu via LQE_LANGUAGE_CODES, pas de if baoule."""
from __future__ import annotations

from app.config import get_settings


def known_languages() -> list[str]:
    return get_settings().language_codes()


def is_known(code: str) -> bool:
    return (code or "").strip().lower() in known_languages()
