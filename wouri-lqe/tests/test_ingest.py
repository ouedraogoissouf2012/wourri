from pathlib import Path
from app.services.ingest import ingest, parse_upload


def test_ingest_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_LANGUAGE_CODES", "bci,dyu")
    rows = [{"text_local": "A", "text_fr": "B", "id": "x1"}]
    first = ingest(rows, language="bci", actor="t")
    second = ingest(rows, language="bci", actor="t")
    assert first["accepted"] == 1
    assert second["duplicates_skipped"] == 1


def test_parse_csv():
    raw = "text_local,text_fr\nloc,fr\n".encode("utf-8")
    rows = parse_upload("a.csv", raw)
    assert rows[0]["text_local"] == "loc"
