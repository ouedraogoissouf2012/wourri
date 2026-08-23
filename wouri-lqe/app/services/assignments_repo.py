"""Acces PostgreSQL a la table lqe.assignments (ADR-0034 P2).

Encapsule le SQL des assignations : l'admin assigne un concept du corpus (pivot fr) a
une langue cible ; le locuteur produit l'equivalent. Calque `productions_repo` :
get_conn(), _row(tuple)->dict, INSERT ON CONFLICT DO NOTHING (idempotence du lot),
UPDATE garde par statut source (open -> done).
"""
from __future__ import annotations

from app.db import get_conn

_COLS = "id, concept_id, target_language, source_fr, status, assigned_by, created_at"
_SELECT = f"SELECT {_COLS} FROM assignments"


def _row(r: tuple) -> dict:
    aid, concept_id, target_language, source_fr, status, assigned_by, created_at = r
    return {
        "id": str(aid),
        "concept_id": concept_id,
        "target_language": target_language,
        "source_fr": source_fr,
        "status": status,
        "assigned_by": assigned_by,
        "created_at": created_at.isoformat() if created_at else None,
    }


def assign_one(*, concept_id: str, target_language: str, source_fr: str, assigned_by: str) -> bool:
    """INSERT idempotent (UNIQUE concept_id+target_language). True si cree, False si deja assigne."""
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO assignments (concept_id, target_language, source_fr, assigned_by)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (concept_id, target_language) DO NOTHING"
            " RETURNING id",
            (concept_id, target_language, source_fr, assigned_by),
        ).fetchone()
        conn.commit()
    return row is not None


def list_by(*, target_language: str, status: str | None = None) -> list[dict]:
    sql = _SELECT + " WHERE target_language = %s"
    params: tuple = (target_language,)
    if status:
        sql += " AND status = %s"
        params = (target_language, status)
    sql += " ORDER BY id"
    with get_conn() as conn:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]


def assigned_concept_ids(*, target_language: str, status: str | None = None) -> set[str]:
    sql = "SELECT concept_id FROM assignments WHERE target_language = %s"
    params: tuple = (target_language,)
    if status:
        sql += " AND status = %s"
        params = (target_language, status)
    with get_conn() as conn:
        return {r[0] for r in conn.execute(sql, params).fetchall()}


def set_done(*, concept_id: str, target_language: str) -> bool:
    """open -> done (garde de transition : ne touche qu'une assignation 'open')."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE assignments SET status = 'done'"
            " WHERE concept_id = %s AND target_language = %s AND status = 'open'",
            (concept_id, target_language),
        )
        conn.commit()
        return cur.rowcount > 0
