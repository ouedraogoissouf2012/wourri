"""Store JSONL : append, lecture tolérante, update ciblé."""
from app.services import store


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "t.jsonl"
    assert store.read_all(p) == []
    assert store.append_row(p, {"id": "a", "status": "bronze"}) is True
    assert store.append_row(p, {"id": "b", "status": "bronze"}) is True
    assert [r["id"] for r in store.read_all(p)] == ["a", "b"]


def test_update_status_touches_only_target(tmp_path):
    p = tmp_path / "t.jsonl"
    store.append_row(p, {"id": "a", "status": "bronze"})
    store.append_row(p, {"id": "b", "status": "bronze"})
    res = store.update_status(p, "a", "admin_accepted")
    assert res == {"ok": True, "id": "a", "status": "admin_accepted"}
    rows = {r["id"]: r["status"] for r in store.read_all(p)}
    assert rows == {"a": "admin_accepted", "b": "bronze"}


def test_update_status_missing_id(tmp_path):
    p = tmp_path / "t.jsonl"
    store.append_row(p, {"id": "a", "status": "bronze"})
    res = store.update_status(p, "zzz", "production")
    assert res["ok"] is False
    assert res["reason"] == "not_found"


def test_update_status_missing_file(tmp_path):
    res = store.update_status(tmp_path / "absent.jsonl", "a", "production")
    assert res["ok"] is False
    assert res["reason"] == "missing"


def test_read_all_skips_corrupt_and_nondict_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"id":"a"}\nnot-json\n[1,2,3]\n{"id":"b"}\n', encoding="utf-8")
    assert [r["id"] for r in store.read_all(p)] == ["a", "b"]
