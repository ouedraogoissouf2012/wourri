"""Referentiel des langues (table `languages`) — source de verite unique.

Remplace le CSV `LQE_LANGUAGE_CODES` : **activer une langue = un INSERT**, zero
code, zero `if`-langue. La bascule des appelants metier (ingest/users) vers ce
referentiel se fera dans une phase ulterieure ; P0 ne fait que poser la table
et son acces.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db import get_conn

_COLS = "code, name, family, script, asr_available, tts_available, status"


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    family: str | None
    script: str
    asr_available: bool
    tts_available: bool
    status: str  # active | backlog


def _to_language(row: tuple) -> Language:
    return Language(*row)


def list_languages(*, status: str | None = None) -> list[Language]:
    sql = f"SELECT {_COLS} FROM languages"
    params: tuple = ()
    if status:
        sql += " WHERE status = %s"
        params = (status,)
    sql += " ORDER BY code"
    with get_conn() as conn:
        return [_to_language(r) for r in conn.execute(sql, params).fetchall()]


def get_language(code: str) -> Language | None:
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM languages WHERE code = %s", (code.strip().lower(),)
        ).fetchone()
    return _to_language(row) if row else None


def is_known(code: str) -> bool:
    """Une langue est 'connue' si presente au referentiel (quel que soit son statut)."""
    return get_language(code) is not None


def upsert_language(
    code: str,
    name: str,
    *,
    family: str | None = None,
    script: str = "Latn",
    asr_available: bool = False,
    tts_available: bool = False,
    status: str = "backlog",
) -> Language:
    code = code.strip().lower()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO languages (code, name, family, script, asr_available, tts_available, status)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET"
            "   name = EXCLUDED.name, family = EXCLUDED.family, script = EXCLUDED.script,"
            "   asr_available = EXCLUDED.asr_available, tts_available = EXCLUDED.tts_available,"
            "   status = EXCLUDED.status",
            (code, name, family, script, asr_available, tts_available, status),
        )
        conn.commit()
    return get_language(code)  # type: ignore[return-value]


def set_status(code: str, status: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE languages SET status = %s WHERE code = %s", (status, code.strip().lower())
        )
        conn.commit()
        return cur.rowcount > 0
