"""Promotion atelier — jamais pgvector moteur."""
from __future__ import annotations

from datetime import datetime, timezone

from app.paths import corpus_path, tasks_path
from app.services.store import append_row, read_all, update_status

ALLOWED_FROM = {"admin_accepted", "speaker_accepted"}


def list_tasks(*, language: str, status: str | None = None) -> list[dict]:
    rows = [r for r in read_all(tasks_path()) if (r.get("language") or "") == language]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows


def decide(item_id: str, status: str, *, language: str) -> dict:
    allowed = {"admin_accepted", "admin_rejected", "production"}
    if status not in allowed:
        return {"ok": False, "reason": "bad_decision"}
    row = next((r for r in list_tasks(language=language) if r.get("id") == item_id), None)
    if not row:
        return {"ok": False, "reason": "not_found"}
    return update_status(tasks_path(), item_id, status)


def promote(item_id: str, *, language: str, actor: str) -> dict:
    row = next((r for r in list_tasks(language=language) if r.get("id") == item_id), None)
    if not row:
        return {"ok": False, "reason": "not_found"}
    if row.get("status") not in ALLOWED_FROM:
        return {"ok": False, "reason": "not_accepted", "status": row.get("status")}
    existing = read_all(corpus_path())
    if any(e.get("id") == item_id and e.get("language") == language for e in existing):
        return {"ok": True, "duplicate": True}
    entry = {
        "id": item_id,
        "language": language,
        "status": "production",
        "text_local": row.get("text_local") or "",
        "text_fr": row.get("text_fr") or "",
        "intent": row.get("intent") or "",
        "cultures": row.get("cultures") or [],
        "audio_url": row.get("audio_url"),
        "promoted_by": actor,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    if not append_row(corpus_path(), entry):
        return {"ok": False, "reason": "io"}
    update_status(tasks_path(), item_id, "production")
    return {"ok": True, "entry": entry}


def list_corpus(*, language: str) -> list[dict]:
    return [r for r in read_all(corpus_path()) if (r.get("language") or "") == language]
