"""Provider Baoulé (#443) — validation JSON → Bronze uniquement.

N'écrit jamais pgvector. Pas de contenu baoulé inventé ici : on stocke
uniquement ce que le provider envoie après validation de forme.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.data.lqe_languages import BAOULE_CODE
from app.services.improvement_queue import enqueue_improvement_task

logger = logging.getLogger(__name__)

REQUIRED = ("text_local", "text_fr")


def _as_entries(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("entries"), list):
            return [x for x in payload["entries"] if isinstance(x, dict)]
        return [payload]
    return []


def validate_baoule_entries(payload: Any) -> tuple[list[dict], list[str]]:
    """Retourne (entrées normalisées Bronze, erreurs)."""
    raw = _as_entries(payload)
    if not raw:
        return [], ["payload vide ou JSON invalide (attendu: liste d'objets)"]

    ok: list[dict] = []
    errors: list[str] = []
    for i, row in enumerate(raw):
        prefix = f"[{i}]"
        local = str(row.get("text_local") or "").strip()
        fr = str(row.get("text_fr") or "").strip()
        if not local:
            errors.append(f"{prefix} text_local requis")
            continue
        if not fr:
            errors.append(f"{prefix} text_fr requis")
            continue
        lang = str(row.get("language") or BAOULE_CODE).strip().lower()
        if lang not in {BAOULE_CODE, "baoule", "baoulé"}:
            errors.append(f"{prefix} language doit être {BAOULE_CODE} (reçu: {lang})")
            continue
        # status client ignoré — toujours bronze
        cultures = row.get("cultures")
        if cultures is not None and not isinstance(cultures, list):
            errors.append(f"{prefix} cultures doit être une liste")
            continue
        ok.append(
            {
                "external_id": str(row.get("id") or "").strip() or None,
                "language": BAOULE_CODE,
                "text_local": local[:2000],
                "text_fr": fr[:2000],
                "intent": str(row.get("intent") or "").strip() or None,
                "cultures": [str(c) for c in (cultures or [])][:20],
                "region": str(row.get("region") or "CI").strip()[:32],
                "notes": str(row.get("notes") or "").strip()[:500] or None,
                "source": "provider_upload",
                "status": "bronze",
            }
        )
    return ok, errors


def ingest_baoule_json(
    payload: Any,
    *,
    provider_id: str = "provider_baoule",
    path=None,
) -> dict:
    """Valide + écrit Bronze. Jamais de corpus prod."""
    entries, errors = validate_baoule_entries(payload)
    if not entries and errors:
        return {"ok": False, "accepted": 0, "rejected": 0, "errors": errors, "tasks": []}

    tasks = []
    for ent in entries:
        excerpt = ent["text_local"]
        # enqueue dyu-oriented helper : on passe language via champs étendus
        result = enqueue_improvement_task(
            intent=ent.get("intent"),
            source="provider_upload",
            cultures=ent.get("cultures") or [],
            excerpt=excerpt,
            user_anon=provider_id,
            path=path,
            language=BAOULE_CODE,
            extra={
                "text_fr": ent["text_fr"],
                "text_local": ent["text_local"],
                "external_id": ent.get("external_id"),
                "region": ent.get("region"),
                "notes": ent.get("notes"),
            },
        )
        if result.get("ok"):
            tasks.append(result.get("task"))
        else:
            errors.append(f"écriture refusée: {result.get('reason')}")

    return {
        "ok": len(tasks) > 0,
        "accepted": len(tasks),
        "rejected": len(errors),
        "errors": errors,
        "language": BAOULE_CODE,
        "tasks": tasks,
    }


def parse_json_bytes(data: bytes) -> Any:
    text = data.decode("utf-8-sig")
    return json.loads(text)


_HEADER_ALIASES = {
    "text_local": {
        "text_local",
        "local",
        "baoule",
        "baoulé",
        "bci",
        "phrase_baoule",
        "phrase_locale",
    },
    "text_fr": {
        "text_fr",
        "fr",
        "francais",
        "français",
        "french",
        "phrase_fr",
        "traduction",
    },
    "id": {"id", "identifiant", "ref"},
    "intent": {"intent", "intention"},
    "cultures": {"cultures", "culture"},
    "region": {"region", "région"},
    "notes": {"notes", "note", "commentaire"},
    "language": {"language", "langue", "lang"},
}


def _norm_header(h: str) -> str | None:
    key = str(h or "").strip().lower()
    for canon, aliases in _HEADER_ALIASES.items():
        if key in aliases:
            return canon
    return None


def _rows_from_table(headers: list[str], rows: list[list[Any]]) -> list[dict]:
    mapped = [_norm_header(h) for h in headers]
    out: list[dict] = []
    for row in rows:
        item: dict[str, Any] = {}
        for i, canon in enumerate(mapped):
            if not canon or i >= len(row):
                continue
            val = row[i]
            if val is None:
                continue
            s = str(val).strip()
            if not s:
                continue
            if canon == "cultures":
                item[canon] = [c.strip() for c in s.replace(";", ",").split(",") if c.strip()]
            else:
                item[canon] = s
        if item:
            out.append(item)
    return out


def parse_csv_bytes(data: bytes) -> list[dict]:
    import csv
    import io

    text = data.decode("utf-8-sig")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        return []
    headers, body = rows[0], rows[1:]
    return _rows_from_table(headers, body)


def parse_xlsx_bytes(data: bytes) -> list[dict]:
    import io

    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl non installé — ajoute openpyxl au requirements"
        ) from exc
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = [str(c) if c is not None else "" for c in next(rows_iter)]
    except StopIteration:
        return []
    body = [list(r) for r in rows_iter]
    return _rows_from_table(headers, body)


def parse_upload(filename: str, data: bytes) -> Any:
    """JSON / CSV / XLSX → liste d'objets pour validate_baoule_entries."""
    name = (filename or "").lower()
    if name.endswith(".json"):
        return parse_json_bytes(data)
    if name.endswith(".csv"):
        return parse_csv_bytes(data)
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return parse_xlsx_bytes(data)
    # tentative contenu
    head = data[:1]
    if head == b"[" or head == b"{":
        return parse_json_bytes(data)
    raise ValueError("Format non supporté — utilise .json, .csv ou .xlsx")
