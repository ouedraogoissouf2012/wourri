"""Écran admin LQE — français, file dyu, pas de corpus."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import lqe
from app.security import require_api_key
from app.services import improvement_queue as iq


def _client(tmp_path, monkeypatch):
    path = tmp_path / "tasks.jsonl"
    monkeypatch.setattr(iq, "DEFAULT_TASKS_PATH", path)
    app = FastAPI()
    app.include_router(lqe.router)
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app), path


def test_page_is_french(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    r = client.get("/admin/lqe/")
    assert r.status_code == 200
    assert "File admin — dioula de Côte d’Ivoire" in r.text
    assert "lang=\"fr\"" in r.text


def test_tasks_and_decision_no_corpus_write(tmp_path, monkeypatch):
    client, path = _client(tmp_path, monkeypatch)
    iq.enqueue_improvement_task(
        intent="CONSEIL_PRODUCTION",
        source="deepseek_open",
        cultures=[],
        excerpt="Aw ye foro labɛn",
        user_anon="usr_x",
        path=path,
    )
    listed = client.get("/admin/lqe/tasks").json()
    assert listed["language"] == "dyu"
    assert len(listed["tasks"]) == 1
    tid = listed["tasks"][0]["id"]
    dec = client.post("/admin/lqe/decision", json={"id": tid, "decision": "admin_rejected"})
    assert dec.status_code == 200
    assert client.get("/admin/lqe/tasks").json()["tasks"] == []
