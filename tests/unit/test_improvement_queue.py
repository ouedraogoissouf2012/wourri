"""Tests — file Bronze #431 (aucun corpus, aucune PII)."""
from __future__ import annotations

import json

from app.services.improvement_queue import (
    decide_task,
    enqueue_improvement_task,
    list_tasks,
)


def test_enqueue_writes_bronze_without_phone(tmp_path):
    path = tmp_path / "tasks.jsonl"
    out = enqueue_improvement_task(
        intent="CONSEIL_PRODUCTION",
        source="deepseek_open",
        cultures=["CULTURE_MAIS"],
        excerpt="Aw ye foro labɛn",
        user_anon="usr_abcd",
        path=path,
    )
    assert out["ok"] is True
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["status"] == "bronze"
    assert line["intent"] == "CONSEIL_PRODUCTION"
    # On scanne ce que l'APPELANT fournit, en excluant les champs GÉNÉRÉS :
    # `id` (uuid4 hexadécimal) et `ts` (horodatage ISO, microsecondes incluses)
    # peuvent contenir « 225 » par hasard — ce qui faisait échouer ce test au
    # hasard (CI de APIPy rouge depuis le 2026-09-23, #555) sans qu'aucune PII
    # ne fuite réellement. L'intention du test est intacte : aucune donnée
    # personnelle ne doit être stockée.
    contenu = json.dumps({k: v for k, v in line.items() if k not in ("id", "ts")})
    assert "225" not in contenu
    assert "@s.whatsapp" not in contenu


def test_list_and_decide_keeps_out_of_corpus(tmp_path):
    path = tmp_path / "tasks.jsonl"
    first = enqueue_improvement_task(
        intent="A", source="s", cultures=[], excerpt="malo", user_anon="usr_1", path=path,
    )
    enqueue_improvement_task(
        intent="B", source="s", cultures=[], excerpt="tiga", user_anon="usr_2", path=path,
    )
    bronze = list_tasks(path=path)
    assert len(bronze) == 2
    assert all(t["language"] == "dyu" for t in bronze)
    tid = first["task"]["id"]
    assert decide_task(tid, "speaker_accepted", path=path)["ok"] is True
    assert len(list_tasks(status="bronze", path=path)) == 1
    assert len(list_tasks(status="speaker_accepted", path=path)) == 1
    assert decide_task(tid, "nope", path=path)["ok"] is False


def test_enqueue_io_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    path = blocker / "tasks.jsonl"
    out = enqueue_improvement_task(
        intent="x", source="y", cultures=[], excerpt="", user_anon="usr_x", path=path,
    )
    assert out["ok"] is False
