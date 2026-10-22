"""Reprendre une validation (ADR-0045, #475) : le locuteur annule sa decision et sa
correction, la fiche redevient « a valider » avec son texte d'origine.

Couvre l'action unitaire (ecran « Mes decisions ») et la remise a zero en lot
(scripts/reprendre_validations.py) : jamais une fiche publiee, jamais une autre langue.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_conn
from app.services import productions_repo as repo
from app.services import workflow
from app.services.ingest import ingest
from scripts import reprendre_validations as reprise

_MOT = {"kind": "mot_cle", "text_local": "kakao", "text_fr": "cacao",
        "concept_nlu": "CULTURE_CACAO", "id": "CULTURE_CACAO:kakao"}
_PAIRE = {"kind": "paire_qr", "text_local": "Blɛ benin ?", "text_fr": "Quand ?",
          "reponse_bci": "Be lua i", "reponse_fr": "On plante", "id": "paire:3:210"}


def _id(text_local, language="bci"):
    return next(r["id"] for r in repo.list_by(language=language) if r["text_local"] == text_local)


def test_correction_garde_l_origine_et_reprendre_la_restaure(seeded):
    ingest([_MOT], language="bci", actor="loc")
    tid = _id("kakao")
    workflow.edit_text(tid, language="bci", text_local="kakaw", text_fr="cacao!")
    workflow.edit_text(tid, language="bci", text_local="kakoo", text_fr="cacao?")
    assert workflow.decide(tid, "admin_rejected", language="bci")["ok"]
    row = repo.get(item_id=tid, language="bci")
    assert row["meta"]["texte_origine"] == {"text_local": "kakao", "text_fr": "cacao"}  # la 1re, pas la 2e
    assert [r["id"] for r in workflow.list_decided(language="bci")] == [tid]

    assert workflow.reprendre(tid, language="bci") == {"ok": True, "id": tid, "status": "bronze"}
    row = repo.get(item_id=tid, language="bci")
    assert (row["status"], row["text_local"], row["text_fr"]) == ("bronze", "kakao", "cacao")
    assert "texte_origine" not in row["meta"] and row["meta"]["concept_nlu"] == "CULTURE_CACAO"
    assert workflow.list_decided(language="bci") == []


def test_reprendre_ne_touche_jamais_une_production_ni_une_autre_langue(seeded):
    ingest([{"text_local": "contenu", "text_fr": "contenu fr"}], language="bci", actor="loc")
    tid = _id("contenu")
    workflow.decide(tid, "admin_accepted", language="bci")
    assert workflow.promote(tid, language="bci", actor="adm")["ok"]
    assert workflow.reprendre(tid, language="bci")["reason"] == "locked"
    assert repo.get(item_id=tid, language="bci")["status"] == "production"
    assert workflow.reprendre(tid, language="dyu")["reason"] == "not_found"


def test_routes_mes_decisions_et_reprendre(seeded, monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps([{"user": "loc", "password": "locpass12", "language": "bci"}]))
    from app.routers import session as session_router
    from app.routers import tasks as tasks_router
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(tasks_router.router)
    c = TestClient(app)
    c.post("/auth/login", json={"user": "loc", "password": "locpass12"})

    ingest([_MOT, _PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    assert c.post("/tasks/decision", json={"id": pid, "decision": "admin_accepted"}).status_code == 200
    taches = c.get("/tasks").json()
    assert [r["id"] for r in taches["decided"]] == [pid]
    assert c.post("/tasks/reprendre", json={"id": pid}).status_code == 200
    taches = c.get("/tasks").json()
    assert taches["decided"] == [] and len(taches["bronze"]) == 2
    assert c.post("/tasks/reprendre", json={"id": "999"}).status_code == 404


def test_remise_a_zero_en_lot_essai_a_blanc_puis_appliquee(seeded, tmp_path, capsys):
    ingest([_MOT, _PAIRE, {"text_local": "contenu", "text_fr": "contenu fr"}], language="bci", actor="loc")
    ingest([{**_MOT, "text_local": "kakao dyu"}], language="dyu", actor="loc")
    mot, paire, contenu = _id("kakao"), _id("Blɛ benin ?"), _id("contenu")
    workflow.decide(mot, "admin_accepted", language="bci")
    workflow.decide(paire, "admin_rejected", language="bci")
    workflow.decide(contenu, "admin_rejected", language="bci")
    workflow.decide(_id("kakao dyu", "dyu"), "admin_accepted", language="dyu")
    # correction faite AVANT que l'atelier garde l'origine : seul le fichier d'import la connait
    with get_conn(autocommit=True) as conn:
        conn.execute("UPDATE productions SET text_local = 'kakaw' WHERE id = %s", (int(mot),))
    original = tmp_path / "import.json"
    original.write_text(json.dumps([_MOT, _PAIRE], ensure_ascii=False), encoding="utf-8")

    assert reprise.main(["--langue", "bci", "--original", str(original)]) == 0
    assert "Fiches remises « a valider » : 2" in capsys.readouterr().out
    assert repo.get(item_id=mot, language="bci")["status"] == "admin_accepted"  # rien d'ecrit

    sauvegarde = tmp_path / "sauvegarde.json"
    assert reprise.main(["--langue", "bci", "--original", str(original), "--appliquer",
                         "--sauvegarde", str(sauvegarde)]) == 0
    row = repo.get(item_id=mot, language="bci")
    assert (row["status"], row["text_local"]) == ("bronze", "kakao")
    assert repo.get(item_id=paire, language="bci")["status"] == "bronze"
    assert repo.get(item_id=contenu, language="bci")["status"] == "admin_rejected"  # type non demande
    assert repo.get(item_id=_id("kakao dyu", "dyu"), language="dyu")["status"] == "admin_accepted"
    avant = json.loads(sauvegarde.read_text(encoding="utf-8"))
    assert {r["id"]: r["text_local"] for r in avant} == {mot: "kakaw", paire: "Blɛ benin ?"}


def test_planifier_saute_ce_qui_est_deja_a_valider_et_intact():
    rows = [{"id": "1", "kind": "mot_cle", "status": "bronze", "text_local": "a", "text_fr": "b",
             "meta": {"external_id": "mot_cle:x"}},
            {"id": "2", "kind": "mot_cle", "status": "bronze", "text_local": "z", "text_fr": "b",
             "meta": {"external_id": "mot_cle:y"}},
            {"id": "3", "kind": "paire_qr", "status": "production", "text_local": "q", "text_fr": "r", "meta": {}}]
    origine = reprise.originaux([{"kind": "mot_cle", "id": "x", "text_local": "a", "text_fr": "b"},
                                 {"kind": "mot_cle", "id": "y", "text_local": "y0", "text_fr": "b"}])
    plan = reprise.planifier(rows, origine, ("mot_cle", "paire_qr"))
    assert [(p["id"], p["apres"]["text_local"]) for p in plan] == [("2", "y0")]
