"""Store JSONL générique (tâches + corpus)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_all(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    except OSError as exc:
        logger.warning("read failed %s: %s", path, exc)
    return out


def append_row(path: Path, row: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError as exc:
        logger.warning("append failed %s: %s", path, exc)
        return False


def update_status(path: Path, item_id: str, status: str) -> dict:
    if not path.is_file():
        return {"ok": False, "reason": "missing"}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
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
        rid = str(row.get("id") or "")
        if rid == item_id:
            row["status"] = status
            found = True
        rewritten.append(json.dumps(row, ensure_ascii=False))
    if not found:
        return {"ok": False, "reason": "not_found"}
    try:
        path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    except OSError:
        return {"ok": False, "reason": "io"}
    return {"ok": True, "id": item_id, "status": status}
