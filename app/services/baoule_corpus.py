"""Corpus Baoulé atelier (Production LQE) — séparé du pgvector dioula."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.lqe_languages import BAOULE_CODE
from app.services.improvement_queue import _tasks_path, decide_task, list_tasks
from app.services.lqe_paths import baoule_corpus_path

logger = logging.getLogger(__name__)

DEFAULT_CORPUS_PATH = None  # monkeypatch tests


def _corpus_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    if DEFAULT_CORPUS_PATH is not None:
        return Path(DEFAULT_CORPUS_PATH)
    return baoule_corpus_path()


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
    tpath = _tasks_path(tasks_path)
    candidates = list_tasks(status="admin_accepted", language=BAOULE_CODE, path=tpath)
    task = next((t for t in candidates if (t.get("id") or "") == task_id), None)
    if not task:
        from app.services.improvement_queue import list_all_tasks

        task = next(
            (
                t
                for t in list_all_tasks(language=BAOULE_CODE, path=tpath)
                if (t.get("id") or "") == task_id
            ),
            None,
        )
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

    existing = list_corpus(path=corpus_path)
    if any(e.get("id") == entry["id"] for e in existing):
        return {"ok": True, "duplicate": True, "entry": entry}

    cpath = _corpus_path(corpus_path)
    try:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        with cpath.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("[BAOULE] corpus write failed: %s", exc)
        return {"ok": False, "reason": "io"}

    decide_task(task_id, "production", path=tpath)
    logger.info("[BAOULE] promoted id=%s by=%s path=%s", entry["id"], promoted_by, cpath)
    return {"ok": True, "entry": entry}


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
