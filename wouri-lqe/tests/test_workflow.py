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


def test_edit_text_corrige_une_fiche_bronze(seeded):
    tid = _seed_bronze()
    r = workflow.edit_text(tid, language="bci", text_local="Akwaba o!", text_fr="Bienvenue a toi")
    assert r["ok"] is True
    row = workflow.list_tasks(language="bci", status="bronze")[0]
    assert row["id"] == tid
    assert row["text_local"] == "Akwaba o!"
    assert row["text_fr"] == "Bienvenue a toi"


def test_edit_text_refuse_texte_vide(seeded):
    tid = _seed_bronze()
    r = workflow.edit_text(tid, language="bci", text_local="   ", text_fr="x")
    assert r["ok"] is False
    assert r["reason"] == "empty"
    # texte d'origine intact
    assert workflow.list_tasks(language="bci", status="bronze")[0]["text_local"] == "Akwaba"


def test_edit_text_isole_la_langue(seeded):
    # une autre langue ne peut JAMAIS editer la fiche d'un autre compte (WHERE language)
    tid = _seed_bronze()  # langue bci
    r = workflow.edit_text(tid, language="dyu", text_local="pirate", text_fr="pirate")
    assert r["ok"] is False
    assert r["reason"] == "not_found"
    assert workflow.list_tasks(language="bci", status="bronze")[0]["text_local"] == "Akwaba"


def test_edit_text_autorise_avant_promotion(seeded):
    tid = _seed_bronze()
    workflow.decide(tid, "admin_accepted", language="bci")
    r = workflow.edit_text(tid, language="bci", text_local="Akwaba fixe", text_fr="Bienvenue")
    assert r["ok"] is True
    assert workflow.list_tasks(language="bci", status="admin_accepted")[0]["text_local"] == "Akwaba fixe"


def test_edit_text_refuse_sur_production(seeded):
    # une fiche publiee (production) n'est plus editable par le role review
    tid = _seed_bronze()
    workflow.decide(tid, "admin_accepted", language="bci")
    workflow.promote(tid, language="bci", actor="admin")
    r = workflow.edit_text(tid, language="bci", text_local="modif", text_fr="modif")
    assert r["ok"] is False
    assert r["reason"] == "locked"
    assert r["status"] == "production"
    assert workflow.list_corpus(language="bci")[0]["text_local"] == "Akwaba"
