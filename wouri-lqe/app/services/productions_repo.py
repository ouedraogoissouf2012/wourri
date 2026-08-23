"""Acces PostgreSQL a la table lqe.productions — backend UNIQUE de l'atelier (ADR-0034 P4).

Encapsule TOUT le SQL du flux : ingest (bronze), transitions de statut, promotion et
couverture. Remplace le store JSONL (tasks.jsonl / corpus.jsonl). Une seule table porte
les deux etages via `status` : bronze -> admin_accepted -> production.

La cle publique exposee a l'API est `productions.id` (bigint identity) serialisee en str.
"""
from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db import get_conn

_COLS = (
    "id, concept_id, language, text_local, text_fr, intent, cultures,"
    " audio_url, status, fingerprint, created_by, promoted_by, promoted_at, meta"
)
_SELECT = f"SELECT {_COLS} FROM productions"


def _row(r: tuple) -> dict:
    (
        pid, concept_id, language, text_local, text_fr, intent, cultures,
        audio_url, status, fingerprint, created_by, promoted_by, promoted_at, meta,
    ) = r
    return {
        "id": str(pid),
        "concept_id": concept_id,
        "language": language,
        "text_local": text_local or "",
        "text_fr": text_fr or "",
        "intent": intent or "",
        "cultures": list(cultures or []),
        "audio_url": audio_url,
        "status": status,
        "fingerprint": fingerprint,
        "created_by": created_by,
        "promoted_by": promoted_by,
        "promoted_at": promoted_at.isoformat() if promoted_at else None,
        "meta": meta or {},
    }


def _as_int(item_id) -> int | None:
    try:
        return int(str(item_id).strip())
    except (TypeError, ValueError):
        return None


def insert_bronze(
    *, language, text_local, text_fr, intent="", cultures=None, audio_url=None,
    fingerprint=None, concept_id=None, created_by=None, meta=None,
) -> dict:
    """INSERT une ligne 'bronze'. Dedup atomique par (language, fingerprint) via l'index
    unique partiel + ON CONFLICT DO NOTHING (protege contre les ingests concurrents).
    Retourne {inserted: bool, id: str|None} — inserted=False => doublon ignore."""
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO productions"
            " (concept_id, language, text_local, text_fr, intent, cultures,"
            "  audio_url, status, fingerprint, created_by, meta)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 'bronze', %s, %s, %s)"
            " ON CONFLICT (language, fingerprint) WHERE fingerprint IS NOT NULL"
            " DO NOTHING"
            " RETURNING id",
            (
                concept_id, language, text_local, text_fr, intent, list(cultures or []),
                audio_url, fingerprint, created_by, Jsonb(meta or {}),
            ),
        ).fetchone()
        conn.commit()
    return {"inserted": row is not None, "id": str(row[0]) if row else None}


def list_by(*, language: str, status: str | None = None) -> list[dict]:
    sql = _SELECT + " WHERE language = %s"
    params: tuple = (language,)
    if status:
        sql += " AND status = %s"
        params = (language, status)
    sql += " ORDER BY id"
    with get_conn() as conn:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]


def get(*, item_id, language: str) -> dict | None:
    pid = _as_int(item_id)
    if pid is None:
        return None
    with get_conn() as conn:
        row = conn.execute(
            _SELECT + " WHERE id = %s AND language = %s", (pid, language)
        ).fetchone()
    return _row(row) if row else None


def set_status(*, item_id, language: str, status: str, allowed_from=None) -> bool:
    """UPDATE cible, TOUJOURS filtre par langue (isolation inter-locuteurs). Si
    `allowed_from` est fourni, la transition n'a lieu QUE depuis ces statuts source
    (garde atomique : empeche p.ex. de retrograder une 'production' publiee)."""
    pid = _as_int(item_id)
    if pid is None:
        return False
    sql = (
        "UPDATE productions SET status = %s, updated_at = now()"
        " WHERE id = %s AND language = %s"
    )
    params: list = [status, pid, language]
    if allowed_from is not None:
        sql += " AND status = ANY(%s)"
        params.append(list(allowed_from))
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount > 0


def promote(*, item_id, language: str, actor: str, allowed_from) -> dict:
    """Transition atomique -> 'production' (verrou FOR UPDATE). Ne cree JAMAIS de nouvelle
    ligne : flippe le statut de LA meme ligne. Refuse si statut hors `allowed_from`."""
    pid = _as_int(item_id)
    if pid is None:
        return {"ok": False, "reason": "not_found"}
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM productions WHERE id = %s AND language = %s FOR UPDATE",
            (pid, language),
        ).fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "reason": "not_found"}
        status = row[0]
        if status not in allowed_from:
            conn.rollback()
            return {"ok": False, "reason": "not_accepted", "status": status}
        updated = conn.execute(
            "UPDATE productions SET status = 'production', promoted_by = %s,"
            " promoted_at = now(), updated_at = now()"
            f" WHERE id = %s AND language = %s RETURNING {_COLS}",
            (actor, pid, language),
        ).fetchone()
        conn.commit()
    return {"ok": True, "entry": _row(updated)}


def covered_concept_ids(*, language: str) -> set[str]:
    """concept_id distincts couverts par une production PROMUE dans `language`."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT concept_id FROM productions"
            " WHERE language = %s AND status = 'production' AND concept_id IS NOT NULL",
            (language,),
        ).fetchall()
    return {r[0] for r in rows}
