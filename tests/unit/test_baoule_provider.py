"""Provider Baoulé #443 — validation JSON Bronze, pas de corpus."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.lqe_languages import BAOULE_CODE
from app.routers import provider_baoule
from app.security import require_api_key
from app.services import baoule_provider as bp
from app.services import improvement_queue as iq


def test_validate_forces_bronze_and_bci():
    entries, errors = bp.validate_baoule_entries(
        [
            {
                "id": "x1",
                "language": "baoule",
                "text_local": "phrase locale test",
                "text_fr": "phrase française test",
                "status": "production",
            }
        ]
    )
    assert errors == []
    assert len(entries) == 1
    assert entries[0]["status"] == "bronze"
    assert entries[0]["language"] == BAOULE_CODE


def test_reject_missing_fields():
    entries, errors = bp.validate_baoule_entries([{"text_fr": "only fr"}])
    assert entries == []
    assert any("text_local" in e for e in errors)


def test_ingest_writes_bronze_bci(tmp_path):
    path = tmp_path / "t.jsonl"
    out = bp.ingest_baoule_json(
        [
            {
                "text_local": "local A",
                "text_fr": "fr A",
                "intent": "CONSEIL_PRODUCTION",
            }
        ],
        path=path,
    )
    assert out["ok"] is True
    assert out["accepted"] == 1
    assert out["language"] == BAOULE_CODE
    rows = iq.list_tasks(status="bronze", language=BAOULE_CODE, path=path)
    assert len(rows) == 1
    assert rows[0]["text_fr"] == "fr A"
    # dyu file remains empty
    assert iq.list_tasks(status="bronze", language="dyu", path=path) == []


def test_upload_endpoint(tmp_path, monkeypatch):
    path = tmp_path / "t.jsonl"
    monkeypatch.setattr(iq, "DEFAULT_TASKS_PATH", path)
    app = FastAPI()
    app.include_router(provider_baoule.router)
    app.dependency_overrides[require_api_key] = lambda: None
    client = TestClient(app)
    schema = client.get("/api/provider/baoule/schema").json()
    assert schema["language_code"] == "bci"
    payload = [{"text_local": "L", "text_fr": "F"}]
    r = client.post("/api/provider/baoule/upload-json", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 1
    listed = client.get("/api/provider/baoule/tasks").json()
    assert listed["language"] == "bci"
    assert len(listed["tasks"]) == 1
