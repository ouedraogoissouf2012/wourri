"""Machine à états atelier : bronze → admin_accepted → production (jamais pgvector)."""
from app.services import workflow
from app.services.ingest import ingest


def _seed_bronze(tmp_path, monkeypatch, language="bci"):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_LANGUAGE_CODES", "bci,dyu")
    res = ingest(
        [{"text_local": "Akwaba", "text_fr": "Bienvenue", "id": "k1"}],
        language=language,
        actor="prov",
    )
    assert res["accepted"] == 1
    return workflow.list_tasks(language=language)[0]["id"]


def test_promote_requires_accepted_status(tmp_path, monkeypatch):
    tid = _seed_bronze(tmp_path, monkeypatch)
    r = workflow.promote(tid, language="bci", actor="admin")
    assert r["ok"] is False
    assert r["reason"] == "not_accepted"
    assert r["status"] == "bronze"


def test_promote_flow_bronze_to_production(tmp_path, monkeypatch):
    tid = _seed_bronze(tmp_path, monkeypatch)
    assert workflow.decide(tid, "admin_accepted", language="bci")["ok"] is True

    r = workflow.promote(tid, language="bci", actor="admin")
    assert r["ok"] is True
    assert r["entry"]["status"] == "production"
    assert r["entry"]["language"] == "bci"
    assert r["entry"]["promoted_by"] == "admin"

    assert [e["id"] for e in workflow.list_corpus(language="bci")] == [tid]

    # la tâche est passée en production → un 2e promote est refusé, pas redoublé
    r2 = workflow.promote(tid, language="bci", actor="admin")
    assert r2["ok"] is False
    assert r2["status"] == "production"


def test_promote_isolates_language(tmp_path, monkeypatch):
    tid = _seed_bronze(tmp_path, monkeypatch)  # tâche en langue bci
    workflow.decide(tid, "admin_accepted", language="bci")

    # une autre langue ne voit jamais la tâche d'un autre compte
    r = workflow.promote(tid, language="dyu", actor="admin")
    assert r["ok"] is False
    assert r["reason"] == "not_found"
    assert workflow.list_corpus(language="dyu") == []
