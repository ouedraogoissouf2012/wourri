"""Migration one-shot des donnees JSONL de l'atelier vers Postgres lqe.productions (ADR-0034 P4).

Lit LQE_DATA_DIR/tasks.jsonl (source de verite du flux : tous les items avec leur statut
courant) et applique le statut. Idempotent : la contrainte unique (language, fingerprint)
empeche les doublons a la re-execution. Sur : ne fait rien si les fichiers sont absents/vides.

Dette tracee : promoted_by/promoted_at des items deja 'production' ne sont pas restaures
(champ cosmetique d'audit ; corpus.jsonl etait une projection derivee).

Usage (depuis wouri-lqe/, memes variables POSTGRES_*/LQE_DB_SCHEMA que l'app) :
    python -m scripts.migrate_jsonl_to_pg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.data import language_registry as reg
from app.paths import data_dir
from app.services import productions_repo as repo
from app.services.fingerprint import fingerprint
from app.services.migrate import run_migrations

_STATUS = {"bronze", "admin_accepted", "admin_rejected", "production"}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
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
    return out


def migrate_dir(directory: Path) -> dict:
    tasks = _read_jsonl(directory / "tasks.jsonl")
    imported = 0
    skipped = 0
    errors: list[str] = []
    for t in tasks:
        language = (t.get("language") or "").strip().lower()
        local = str(t.get("text_local") or "").strip()
        fr = str(t.get("text_fr") or "").strip()
        if not language or not local or not fr:
            skipped += 1
            continue
        if not reg.is_known(language):
            reg.upsert_language(language, language, status="active")
        ext = t.get("external_id") or t.get("id")
        fp = t.get("fingerprint") or fingerprint(
            language=language, text_local=local, text_fr=fr,
            external_id=str(ext) if ext else None,
        )
        status = t.get("status") if t.get("status") in _STATUS else "bronze"
        meta = {
            "region": t.get("region"),
            "notes": t.get("notes"),
            "source": t.get("source") or "jsonl_import",
            "external_id": str(ext) if ext else None,
            "actor": t.get("actor"),
        }
        res = repo.insert_bronze(
            language=language,
            text_local=local[:2000],
            text_fr=fr[:2000],
            intent=str(t.get("intent") or ""),
            cultures=t.get("cultures") if isinstance(t.get("cultures"), list) else [],
            audio_url=t.get("audio_url"),
            fingerprint=fp,
            concept_id=str(t.get("concept_id")).strip() if t.get("concept_id") else None,
            created_by=t.get("actor"),
            meta=meta,
        )
        if not res["inserted"]:
            skipped += 1
            continue
        if status != "bronze":  # insert_bronze cree en 'bronze' -> restaure l'etat reel
            repo.set_status(item_id=res["id"], language=language, status=status)
        imported += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def main() -> int:
    run_migrations()
    result = migrate_dir(data_dir())
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
