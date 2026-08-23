"""Machine à états atelier sur Postgres : bronze → admin_accepted → production."""
from app.services import workflow
from app.services.ingest import ingest


def _seed_bronze(language="bci"):
    res = ingest(
        [{"text_local": "Akwaba", "text_fr": "Bienvenue", "id": "k1"}],
        language=language,
        actor="prov",
    )
    assert res["accepted"] == 1
    return workflow.list_tasks(language=language)[0]["id"]


def test_promote_requires_accepted_status(seeded):
    tid = _seed_bronze()
    r = workflow.promote(tid, language="bci", actor="admin")
    assert r["ok"] is False
    assert r["reason"] == "not_accepted"
    assert r["status"] == "bronze"


def test_promote_flow_bronze_to_production(seeded):
    tid = _seed_bronze()
    assert workflow.decide(tid, "admin_accepted", language="bci")["ok"] is True

    r = workflow.promote(tid, language="bci", actor="admin")
    assert r["ok"] is True
    assert r["entry"]["status"] == "production"
    assert r["entry"]["language"] == "bci"
    assert r["entry"]["promoted_by"] == "admin"

    assert [e["id"] for e in workflow.list_corpus(language="bci")] == [tid]

    # la ligne est en production → un 2e promote est refusé, jamais redoublé
    r2 = workflow.promote(tid, language="bci", actor="admin")
    assert r2["ok"] is False
    assert r2["status"] == "production"


def test_promote_isolates_language(seeded):
    tid = _seed_bronze()  # tâche en langue bci
    workflow.decide(tid, "admin_accepted", language="bci")

    # une autre langue ne voit jamais la tâche d'un autre compte (WHERE language)
    r = workflow.promote(tid, language="dyu", actor="admin")
    assert r["ok"] is False
    assert r["reason"] == "not_found"
    assert workflow.list_corpus(language="dyu") == []


def test_decide_rejects_production(seeded):
    tid = _seed_bronze()
    # 'production' n'est PAS une décision : la promotion passe par /corpus/promote (role promote)
    r = workflow.decide(tid, "production", language="bci")
    assert r["ok"] is False
    assert r["reason"] == "bad_decision"
    # la ligne reste bronze, jamais promue en douce
    assert workflow.list_tasks(language="bci", status="bronze")[0]["id"] == tid


def test_decide_admin_rejected(seeded):
    tid = _seed_bronze()
    assert workflow.decide(tid, "admin_rejected", language="bci")["ok"] is True
    assert workflow.list_tasks(language="bci", status="admin_rejected")[0]["id"] == tid


def test_decide_cannot_downgrade_production(seeded):
    # le role review (decide) ne doit JAMAIS pouvoir defaire une promotion (role promote)
    tid = _seed_bronze()
    workflow.decide(tid, "admin_accepted", language="bci")
    workflow.promote(tid, language="bci", actor="admin")

    r = workflow.decide(tid, "admin_rejected", language="bci")
    assert r["ok"] is False
    assert r["reason"] == "locked"
    assert r["status"] == "production"
    # la production reste publiee dans le corpus
    assert [e["id"] for e in workflow.list_corpus(language="bci")] == [tid]
