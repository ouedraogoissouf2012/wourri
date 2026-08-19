"""Promotion corpus Baoulé — pas de pgvector dioula."""
from __future__ import annotations

from app.services import baoule_corpus as bc
from app.services import baoule_provider as bp
from app.services import improvement_queue as iq


def test_promote_accepted_to_corpus(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    bp.ingest_baoule_json(
        [{"text_local": "Bci phrase", "text_fr": "FR phrase", "id": "bci_p1"}],
        path=tasks,
    )
    tid = iq.list_tasks(language="bci", path=tasks)[0]["id"]
    iq.decide_task(tid, "admin_accepted", path=tasks)
    out = bc.promote_task(
        tid, promoted_by="adc", tasks_path=tasks, corpus_path=corpus
    )
    assert out["ok"] is True
    rows = bc.list_corpus(path=corpus)
    assert len(rows) == 1
    assert rows[0]["status"] == "production"
    assert rows[0]["text_local"] == "Bci phrase"
    assert rows[0]["language"] == "bci"
    stats = bc.corpus_stats(path=corpus)
    assert stats["count"] == 1
    assert stats["without_audio"] == 1


def test_promote_rejects_bronze(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    bp.ingest_baoule_json(
        [{"text_local": "L", "text_fr": "F"}],
        path=tasks,
    )
    tid = iq.list_tasks(language="bci", path=tasks)[0]["id"]
    out = bc.promote_task(
        tid, promoted_by="adc", tasks_path=tasks, corpus_path=corpus
    )
    assert out["ok"] is False
    assert out["reason"] == "not_accepted"


def test_ingest_skips_duplicates(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    row = {"text_local": "Meme phrase", "text_fr": "Same FR", "id": "bci_dup"}
    a = bp.ingest_baoule_json([row], path=tasks)
    b = bp.ingest_baoule_json([row], path=tasks)
    assert a["accepted"] == 1
    assert b["duplicates_skipped"] == 1
    assert b["accepted"] == 0
    assert len(iq.list_tasks(language="bci", path=tasks)) == 1
