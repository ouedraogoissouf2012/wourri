"""Routes /assignments (ADR-0034 P2)."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import language_registry as reg

_LOC = [{"user": "loc", "password": "locpass12", "language": "bci"}]


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import assignments as assignments_router
    from app.routers import session as session_router
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(assignments_router.router)
    return TestClient(app)


def test_assignments_requires_auth(corpus, monkeypatch, tmp_path):
    client = _app(monkeypatch, tmp_path)
    assert client.get("/assignments").status_code == 401


def test_post_assign_admin_only(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    r = client.post("/assignments", json={"target_language": "bci", "concept_ids": ["mais_conseil_001"]})
    assert r.status_code == 403  # un locuteur ne peut pas assigner


def test_post_assign_then_speaker_sees_it(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    admin = _app(monkeypatch, tmp_path)
    admin.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    r = admin.post("/assignments", json={"target_language": "bci", "concept_ids": ["mais_conseil_001"]})
    assert r.status_code == 200 and r.json()["assigned"] == 1

    loc = _app(monkeypatch, tmp_path)
    loc.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    d = loc.get("/assignments").json()
    assert d["count"] == 1 and d["assignments"][0]["concept_id"] == "mais_conseil_001"


def test_missing_lists_unassigned(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    d = client.get("/assignments/missing?language=bci").json()
    assert {c["concept_id"] for c in d["concepts"]} == {"mais_conseil_001", "riz_conseil_001"}


def test_post_assign_unknown_language_400(corpus, monkeypatch, tmp_path):
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    r = client.post("/assignments", json={"target_language": "zzz", "concept_ids": ["mais_conseil_001"]})
    assert r.status_code == 400


def test_promote_closes_assignment(corpus, monkeypatch, tmp_path):
    """Boucle complète : assigner -> produire (réponse) -> accepter -> promouvoir ferme
    l'assignation (open -> done). Couvre le câblage /corpus/promote -> mark_done."""
    reg.upsert_language("bci", "Baoule", status="active")
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import assignments as a_router
    from app.routers import corpus as corpus_router
    from app.routers import ingest as ingest_router
    from app.routers import session as session_router
    from app.routers import tasks as tasks_router
    app = FastAPI()
    for r in (session_router.router, a_router.router, ingest_router.router,
              tasks_router.router, corpus_router.router):
        app.include_router(r)

    admin = TestClient(app)
    admin.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    admin.post("/assignments", json={"target_language": "bci", "concept_ids": ["mais_conseil_001"]})

    loc = TestClient(app)
    loc.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    assert loc.post("/ingest/json", json=[
        {"text_local": "kaba", "text_fr": "Plante ton mais", "concept_id": "mais_conseil_001"},
    ]).status_code == 200
    tid = loc.get("/tasks").json()["bronze"][0]["id"]
    loc.post("/tasks/decision", json={"id": tid, "decision": "admin_accepted"})
    loc.post("/corpus/promote", json={"id": tid})

    assert loc.get("/assignments").json()["count"] == 0  # assignation fermée (done)
