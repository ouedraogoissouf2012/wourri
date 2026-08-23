"""Test du script one-shot d'import JSONL -> Postgres lqe.productions (ADR-0034 P4)."""
import json

from app.services import workflow
from scripts.migrate_jsonl_to_pg import migrate_dir


def _write(tmp_path, rows):
    (tmp_path / "tasks.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


def test_import_tasks_jsonl(seeded, tmp_path):
    _write(tmp_path, [
        {"id": "a", "language": "dyu", "text_local": "loc1", "text_fr": "fr1",
         "status": "bronze", "fingerprint": "h:1"},
        {"id": "b", "language": "dyu", "text_local": "loc2", "text_fr": "fr2",
         "status": "production", "fingerprint": "h:2"},
    ])
    res = migrate_dir(tmp_path)
    assert res["imported"] == 2
    assert len(workflow.list_tasks(language="dyu")) == 2
    assert len(workflow.list_corpus(language="dyu")) == 1  # celui en 'production'


def test_import_is_idempotent(seeded, tmp_path):
    _write(tmp_path, [
        {"id": "a", "language": "dyu", "text_local": "l", "text_fr": "f",
         "status": "bronze", "fingerprint": "h:1"},
    ])
    migrate_dir(tmp_path)
    res2 = migrate_dir(tmp_path)  # 2e passage : la contrainte unique bloque les doublons
    assert res2["imported"] == 0
    assert len(workflow.list_tasks(language="dyu")) == 1


def test_import_empty_is_safe(seeded, tmp_path):
    assert migrate_dir(tmp_path) == {"imported": 0, "skipped": 0, "errors": []}


def test_import_unknown_language_goes_backlog(seeded, tmp_path):
    # une langue absente du référentiel est créée en 'backlog', jamais activée d'office
    from app.data import language_registry as reg
    _write(tmp_path, [
        {"id": "z", "language": "zzz", "text_local": "l", "text_fr": "f",
         "status": "bronze", "fingerprint": "h:z"},
    ])
    res = migrate_dir(tmp_path)
    assert res["imported"] == 1
    lg = reg.get_language("zzz")
    assert lg is not None and lg.status == "backlog"
