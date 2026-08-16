"""Tests — file Bronze #431 (aucun corpus, aucune PII)."""
from __future__ import annotations

import json

from app.services.improvement_queue import enqueue_improvement_task


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
    assert "225" not in json.dumps(line)
    assert "@s.whatsapp" not in json.dumps(line)


def test_enqueue_io_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    path = blocker / "tasks.jsonl"
    out = enqueue_improvement_task(
        intent="x", source="y", cultures=[], excerpt="", user_anon="usr_x", path=path,
    )
    assert out["ok"] is False
