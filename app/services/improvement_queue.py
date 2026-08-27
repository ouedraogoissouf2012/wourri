"""File d'amélioration native (ADR-0031 / #431).

Aucun numéro : uniquement `user` déjà anonymisé par l'appelant.
Persistance : voir lqe_paths (volume dédié /app/data/lqe en prod, issue #488).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.lqe_paths import improvement_tasks_path

logger = logging.getLogger(__name__)

# Monkeypatch tests : si non None, prioritaire
DEFAULT_TASKS_PATH = None


def _tasks_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    if DEFAULT_TASKS_PATH is not None:
        return Path(DEFAULT_TASKS_PATH)
    return improvement_tasks_path()


def content_fingerprint(
    *,
    language: str,
    text_local: str,
    text_fr: str = "",
    external_id: str | None = None,
) -> str:
    """Empreinte stable pour dédoublonnage (id externe ou hash textes)."""
    if external_id:
        return f"ext:{(language or '').lower()}:{external_id.strip().lower()}"
    raw = "|".join(
        [
            (language or "").strip().lower(),
            " ".join((text_local or "").strip().lower().split()),
            " ".join((text_fr or "").strip().lower().split()),
        ]
    )
    return "h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def list_all_tasks(*, language: str | None = None, path=None) -> list[dict]:
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
            lang = row.get("language") or "dyu"
            if language and lang != language:
                continue
            if not row.get("id"):
                row["id"] = row.get("ts") or ""
            out.append(row)
    except OSError as exc:
        logger.warning("[LQE] lecture file échouée (%s)", exc)
    return out


def existing_fingerprints(*, language: str, path=None) -> set[str]:
    fps: set[str] = set()
    for row in list_all_tasks(language=language, path=path):
        fp = row.get("fingerprint")
        if fp:
            fps.add(fp)
            continue
        fps.add(
            content_fingerprint(
                language=language,
                text_local=str(row.get("text_local") or row.get("excerpt") or ""),
                text_fr=str(row.get("text_fr") or ""),
                external_id=row.get("external_id"),
            )
        )
    return fps


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
    skip_if_duplicate: bool = False,
) -> dict:
    """Ajoute une tâche Bronze. Ne lève jamais."""
    lang = (language or "dyu").strip().lower()
    extra = dict(extra or {})
    text_local = str(extra.get("text_local") or excerpt or "")
    text_fr = str(extra.get("text_fr") or "")
    external_id = extra.get("external_id")
    fp = content_fingerprint(
        language=lang,
        text_local=text_local,
        text_fr=text_fr,
        external_id=external_id if isinstance(external_id, str) else None,
    )

    if skip_if_duplicate:
        if fp in existing_fingerprints(language=lang, path=path):
            return {"ok": True, "duplicate": True, "fingerprint": fp}

    task = {
        "id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "bronze",
        "language": lang,
        "intent": intent or "",
        "source": source or "unknown",
        "cultures": cultures or [],
        "excerpt": (excerpt or "")[:200],
        "user": user_anon or "",
        "fingerprint": fp,
    }
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
        return {"ok": True, "task": task, "duplicate": False}
    except OSError as exc:
        logger.warning("[LQE] file indisponible (%s)", exc)
        return {"ok": False, "reason": "io"}


def list_tasks(*, status: str | None = "bronze", language: str = "dyu", path=None) -> list[dict]:
    out = []
    for row in list_all_tasks(language=language, path=path):
        if status and row.get("status") != status:
            continue
        out.append(row)
    return out


def decide_task(task_id: str, decision: str, *, path=None) -> dict:
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
        return {"ok": False, "reason": "not_found", "path": str(target)}
    try:
        target.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("[LQE] écriture file échouée (%s)", exc)
        return {"ok": False, "reason": "io"}
    return {"ok": True, "id": task_id, "status": decision}
