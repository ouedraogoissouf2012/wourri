"""Acces PostgreSQL a la table lqe.dictation — dataset ASR par dictee (ADR-0035).

Table ISOLEE du flux de parite (productions) : la dictee IMPOSE le texte au locuteur
(transcription garantie) ; un audio de dictee ne couvre AUCUN concept. Cycle de vie
propre porte par `status` : todo -> recorded. La cle publique exposee a l'API est
`dictation.id` (bigint identity) serialisee en str.
"""
from __future__ import annotations

import hashlib

from app.db import get_conn

_COLS = (
    "id, language, filiere, text_local, text_fr, audio_url,"
    " status, recorded_by, recorded_at, created_at"
)
_SELECT = f"SELECT {_COLS} FROM dictation"


def _row(r: tuple) -> dict:
    (
        did, language, filiere, text_local, text_fr, audio_url,
        status, recorded_by, recorded_at, created_at,
    ) = r
    return {
        "id": str(did),
        "language": language,
        "filiere": filiere or "",
        "text_local": text_local or "",
        "text_fr": text_fr or "",
        "audio_url": audio_url,
        "status": status,
        "recorded_by": recorded_by,
        "recorded_at": recorded_at.isoformat() if recorded_at else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


def _as_int(item_id) -> int | None:
    try:
        return int(str(item_id).strip())
    except (TypeError, ValueError):
        return None


def prompt_hash(*, language: str, text_local: str) -> str:
    """Identite stable d'un prompt = langue + phrase normalisee (espaces reduits, casse).
    Base de l'idempotence de l'import (index unique `(language, prompt_hash)`)."""
    norm = " ".join((text_local or "").split()).lower()
    raw = f"{(language or '').strip().lower()}|{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def import_prompts(*, language: str, prompts: list[dict]) -> dict:
    """INSERT en masse des phrases a lire (status 'todo', sans audio). Idempotent par
    `(language, prompt_hash)` via l'index unique + ON CONFLICT DO NOTHING (re-import sur).
    Retourne {inserted, skipped, language}. Une phrase vide est ignoree (skipped)."""
    inserted = 0
    skipped = 0
    with get_conn() as conn:
        for p in prompts:
            local = str(p.get("text_local") or "").strip()
            if not local:
                skipped += 1
                continue
            fr = str(p.get("text_fr") or "").strip()
            filiere = str(p.get("filiere") or "").strip()
            ph = prompt_hash(language=language, text_local=local)
            row = conn.execute(
                "INSERT INTO dictation"
                " (language, filiere, text_local, text_fr, prompt_hash, status)"
                " VALUES (%s, %s, %s, %s, %s, 'todo')"
                " ON CONFLICT (language, prompt_hash) DO NOTHING"
                " RETURNING id",
                (language, filiere, local[:2000], fr[:2000], ph),
            ).fetchone()
            if row is not None:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    return {"inserted": inserted, "skipped": skipped, "language": language}


def list_prompts(*, language: str, status: str | None = None) -> list[dict]:
    """Les prompts de `language`, filtres par statut optionnel, tries par id (ordre stable)."""
    sql = _SELECT + " WHERE language = %s"
    params: tuple = (language,)
    if status:
        sql += " AND status = %s"
        params = (language, status)
    sql += " ORDER BY id"
    with get_conn() as conn:
        return [_row(r) for r in conn.execute(sql, params).fetchall()]


def get(*, item_id, language: str) -> dict | None:
    """Un prompt par id, TOUJOURS filtre par langue (isolation inter-locuteurs)."""
    did = _as_int(item_id)
    if did is None:
        return None
    with get_conn() as conn:
        row = conn.execute(
            _SELECT + " WHERE id = %s AND language = %s", (did, language)
        ).fetchone()
    return _row(row) if row else None


def counts(*, language: str) -> dict:
    """Progression de la dictee pour `language` : {total, recorded, todo}."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE status = 'recorded')"
            " FROM dictation WHERE language = %s",
            (language,),
        ).fetchone()
    total = int(row[0] or 0)
    recorded = int(row[1] or 0)
    return {"language": language, "total": total, "recorded": recorded, "todo": total - recorded}


def set_recorded(*, item_id, language: str, audio_url: str, actor: str) -> bool:
    """Attache l'audio a un prompt et le passe 'recorded'. Filtre TOUJOURS par langue
    (isolation). Re-enregistrement autorise (remplace l'audio precedent)."""
    did = _as_int(item_id)
    if did is None:
        return False
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE dictation SET audio_url = %s, status = 'recorded',"
            " recorded_by = %s, recorded_at = now()"
            " WHERE id = %s AND language = %s",
            (audio_url, actor, did, language),
        )
        conn.commit()
        return cur.rowcount > 0


def export_rows(*, language: str) -> list[dict]:
    """Les prompts ENREGISTRES (audio present) de `language`, pour l'export dataset."""
    with get_conn() as conn:
        rows = conn.execute(
            _SELECT + " WHERE language = %s AND status = 'recorded'"
            " AND audio_url IS NOT NULL ORDER BY id",
            (language,),
        ).fetchall()
    return [_row(r) for r in rows]
