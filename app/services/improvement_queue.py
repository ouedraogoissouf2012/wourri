"""File d'amélioration native (ADR-0031 / #431).

Un 👎 (ou signal équivalent) crée une tâche **Bronze**. Rien n'entre dans
pgvector. Convex n'a pas encore d'endpoint tâches : file JSONL équivalente,
lisible par l'écran locuteur (#433) plus tard.

Aucun numéro : uniquement `user` déjà anonymisé par l'appelant.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from app.services.lqe_paths import improvement_tasks_path

# Compat tests : chemin par défaut = volume logs en prod, ./data en local
def _default_tasks() -> Path:
    return improvement_tasks_path()


# Alias mutable pour monkeypatch tests
DEFAULT_TASKS_PATH = None  # résolu à l'appel


def _tasks_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    if DEFAULT_TASKS_PATH is not None:
        return Path(DEFAULT_TASKS_PATH)
    return _default_tasks()


def enqueue_improvement_task(
    *,
    intent: str | None,
    source: str | None,
    cultures: list | None,
    excerpt: str | None,
    user_anon: str | None,
    path: str | os.PathLike | None = None,
    language: str = "dyu",
    extra: dict | None = None,
) -> dict:
    """Ajoute une tâche Bronze. Ne lève jamais (WhatsApp / feedback restent OK)."""
    task = {
        "id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "bronze",
        "language": (language or "dyu").strip().lower(),
        "intent": intent or "",
        "source": source or "unknown",
        "cultures": cultures or [],
        "excerpt": (excerpt or "")[:200],
        "user": user_anon or "",
    }
    if extra:
        for k, v in extra.items():
            if v is not None and k not in task:
                task[k] = v
    dumped = json.dumps(task, ensure_ascii=False)
    if "user_id" in dumped or "@s.whatsapp" in dumped:
        logger.error("[LQE] tâche refusée : PII détectée")
        return {"ok": False, "reason": "pii"}
    target = _tasks_path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(dumped + "\n")
        logger.info(
            "[LQE] Bronze lang=%s intent=%s path=%s",
            task["language"],
            task["intent"],
            target,
        )
        return {"ok": True, "task": task}
    except OSError as exc:
        logger.warning("[LQE] file indisponible (%s) — signal conservé ailleurs", exc)
        return {"ok": False, "reason": "io"}


def list_tasks(*, status: str | None = "bronze", language: str = "dyu", path=None) -> list[dict]:
    """Lit la file. Défaut : Bronze dyu (pilote ADR-0031)."""
    target = _tasks_path(path)
    if not target.is_file():
        return []
    out = []
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if status and row.get("status") != status:
                continue
            lang = row.get("language") or "dyu"
            if language and lang != language:
                continue
            if not row.get("id"):
                row["id"] = row.get("ts") or ""
            out.append(row)
    except OSError as exc:
        logger.warning("[LQE] lecture file échouée (%s)", exc)
    return out


def decide_task(task_id: str, decision: str, *, path=None) -> dict:
    """speaker_* ou admin_*. N'écrit jamais dans pgvector."""
    allowed = {
        "admin_accepted",
        "admin_rejected",
        "speaker_accepted",
        "speaker_rejected",
        "production",
    }
    if decision not in allowed:
        return {"ok": False, "reason": "bad_decision"}
    target = _tasks_path(path)
    if not target.is_file():
        logger.warning("[LQE] decide missing file id=%s path=%s", task_id, target)
        return {"ok": False, "reason": "missing", "path": str(target)}
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("[LQE] lecture file échouée (%s)", exc)
        return {"ok": False, "reason": "io"}
    found = False
    rewritten = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            rewritten.append(line)
            continue
        rid = row.get("id") or row.get("ts") or ""
        if rid == task_id:
            row["status"] = decision
            found = True
        rewritten.append(json.dumps(row, ensure_ascii=False))
    if not found:
        return {"ok": False, "reason": "not_found"}
    try:
        target.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("[LQE] écriture file échouée (%s)", exc)
        return {"ok": False, "reason": "io"}
    return {"ok": True, "id": task_id, "status": decision}
