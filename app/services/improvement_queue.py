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
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TASKS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "improvement_tasks.jsonl"


def enqueue_improvement_task(
    *,
    intent: str | None,
    source: str | None,
    cultures: list | None,
    excerpt: str | None,
    user_anon: str | None,
    path: str | os.PathLike | None = None,
) -> dict:
    """Ajoute une tâche Bronze. Ne lève jamais (WhatsApp / feedback restent OK)."""
    task = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "bronze",
        "intent": intent or "",
        "source": source or "unknown",
        "cultures": cultures or [],
        "excerpt": (excerpt or "")[:200],
        "user": user_anon or "",
    }
    dumped = json.dumps(task, ensure_ascii=False)
    if "user_id" in dumped or "@s.whatsapp" in dumped:
        logger.error("[LQE] tâche refusée : PII détectée")
        return {"ok": False, "reason": "pii"}
    target = Path(path) if path else DEFAULT_TASKS_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(dumped + "\n")
        logger.info("[LQE] tâche Bronze intent=%s source=%s", task["intent"], task["source"])
        return {"ok": True, "task": task}
    except OSError as exc:
        logger.warning("[LQE] file indisponible (%s) — signal conservé ailleurs", exc)
        return {"ok": False, "reason": "io"}
