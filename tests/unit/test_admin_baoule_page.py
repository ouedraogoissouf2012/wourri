"""Page admin Baoulé — HTML FR + décision sans corpus."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin_baoule
from app.security import require_api_key
from app.services import improvement_queue as iq


def test_page_is_french_and_bci():
    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app)
    r = client.get("/admin/baoule/")
    assert r.status_code == 200
    assert "Baoulé" in r.text
    assert "bci" in r.text
    assert "ne publie pas" in r.text


def test_decision_endpoint(tmp_path, monkeypatch):
    path = tmp_path / "t.jsonl"
    monkeypatch.setattr(iq, "DEFAULT_TASKS_PATH", path)
    from app.services.baoule_provider import ingest_baoule_json

    ingest_baoule_json(
        [{"text_local": "L", "text_fr": "F"}],
        path=path,
    )
    tid = iq.list_tasks(language="bci", path=path)[0]["id"]
    app = FastAPI()
    app.include_router(admin_baoule.router)
    app.dependency_overrides[require_api_key] = lambda: None
    client = TestClient(app)
    r = client.post(
        "/admin/baoule/decision",
        json={"id": tid, "decision": "admin_rejected"},
    )
    assert r.status_code == 200
    assert iq.list_tasks(status="bronze", language="bci", path=path) == []
