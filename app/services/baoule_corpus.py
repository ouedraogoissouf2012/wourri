"""Corpus Baoulé atelier (Production LQE) — séparé du pgvector dioula.

Promotion manuelle ADC uniquement. Pas de WhatsApp tant que le canal bci
n'existe pas. Audio : référence optionnelle (fichier / URL) — pas de TTS baoulé inventé.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.lqe_languages import BAOULE_CODE
from app.services.improvement_queue import DEFAULT_TASKS_PATH, decide_task, list_tasks

logger = logging.getLogger(__name__)

DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "baoule_corpus.jsonl"
)


def _corpus_path(path=None) -> Path:
    return Path(path) if path else DEFAULT_CORPUS_PATH


def list_corpus(*, path=None) -> list[dict]:
    target = _corpus_path(path)
    if not target.is_file():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def promote_task(
    task_id: str,
    *,
    promoted_by: str,
    tasks_path=None,
    corpus_path=None,
) -> dict[str, Any]:
    """admin_accepted (ou bronze déjà validé) → corpus baoulé Production.

    Ne touche PAS corpus_entries pgvector (dioula WhatsApp).
    """
    tpath = Path(tasks_path) if tasks_path else DEFAULT_TASKS_PATH
    candidates = list_tasks(status="admin_accepted", language=BAOULE_CODE, path=tpath)
    # aussi permettre promote depuis bronze si déjà accepté côté UI en une étape
    task = next((t for t in candidates if (t.get("id") or "") == task_id), None)
    if not task:
        # chercher dans toute la file bci
        all_bci = []
        if tpath.is_file():
            for line in tpath.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("language") or "") == BAOULE_CODE and (
                    row.get("id") or ""
                ) == task_id:
                    all_bci.append(row)
        task = all_bci[0] if all_bci else None
    if not task:
        return {"ok": False, "reason": "not_found"}
    if task.get("status") not in {"admin_accepted", "speaker_accepted"}:
        return {"ok": False, "reason": "not_accepted", "status": task.get("status")}

    entry = {
        "id": task.get("id") or uuid.uuid4().hex,
        "language": BAOULE_CODE,
        "status": "production",
        "text_local": task.get("text_local") or task.get("excerpt") or "",
        "text_fr": task.get("text_fr") or "",
        "intent": task.get("intent") or "",
        "cultures": task.get("cultures") or [],
        "region": task.get("region") or "CI",
        "notes": task.get("notes") or "",
        "audio_url": task.get("audio_url") or task.get("audio_ref") or None,
        "source_task_id": task.get("id"),
        "promoted_by": promoted_by,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    if not entry["text_local"]:
        return {"ok": False, "reason": "empty_text_local"}

    # dédup simple par id
    existing = list_corpus(path=corpus_path)
    if any(e.get("id") == entry["id"] for e in existing):
        decide_task(task_id, "admin_accepted", path=tpath)  # no-op status
        return {"ok": True, "duplicate": True, "entry": entry}

    cpath = _corpus_path(corpus_path)
    try:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        with cpath.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("[BAOULE] corpus write failed: %s", exc)
        return {"ok": False, "reason": "io"}

    # marquer la tâche comme promue
    _mark_promoted(task_id, path=tpath)
    logger.info("[BAOULE] promoted id=%s by=%s", entry["id"], promoted_by)
    return {"ok": True, "entry": entry}


def _mark_promoted(task_id: str, *, path: Path) -> None:
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        if (row.get("id") or row.get("ts") or "") == task_id:
            row["status"] = "production"
            row["promoted"] = True
        out.append(json.dumps(row, ensure_ascii=False))
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")


def corpus_stats(*, path=None) -> dict:
    rows = list_corpus(path=path)
    with_audio = sum(1 for r in rows if r.get("audio_url"))
    return {
        "language": BAOULE_CODE,
        "count": len(rows),
        "with_audio": with_audio,
        "without_audio": len(rows) - with_audio,
        "path": str(_corpus_path(path)),
    }
