"""Types d'élément de l'atelier (ADR-0045) : mot-clé et paire question/réponse.

Ils se valident par le locuteur (accepter / rejeter / corriger) mais ne sont jamais
du contenu servi : la garde de parité ne les bloque pas, le corpus et la couverture
les ignorent, la promotion les refuse.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import language_registry as reg
from app.db import get_conn
from app.services import productions_repo as repo
from app.services import workflow
from app.services.ingest import ingest

_LOC = [{"user": "loc", "password": "locpass12", "language": "bci"}]
_MOT = {"kind": "mot_cle", "text_local": "kakao", "text_fr": "cacao",
        "concept_nlu": "CULTURE_CACAO", "id": "CULTURE_CACAO:kakao"}


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import ingest as ingest_router
    from app.routers import session as session_router
    from app.routers import tasks as tasks_router
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(ingest_router.router)
    app.include_router(tasks_router.router)
    c = TestClient(app)
    c.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    return c


def test_mot_cle_echappe_a_la_garde_mais_pas_le_contenu_libre(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")  # non couverte : parité non atteinte
    c = _client(monkeypatch, tmp_path)
    assert c.post("/ingest/json", json=[_MOT]).status_code == 200
    # un lot qui mélange un mot-clé et du contenu libre reste refusé en entier
    lot = [_MOT, {"text_local": "libre", "text_fr": "free"}]
    assert c.post("/ingest/json", json=lot).status_code == 409
    rows = repo.list_by(language="bci")
    assert len(rows) == 1 and rows[0]["kind"] == "mot_cle"
    assert rows[0]["meta"]["concept_nlu"] == "CULTURE_CACAO"


def test_type_inconnu_refuse_par_ligne(seeded):
    r = ingest([{"kind": "autre", "text_local": "x", "text_fr": "y"}, _MOT], language="bci", actor="loc")
    assert r["accepted"] == 1 and any("type inconnu" in e for e in r["errors"])


def test_meme_id_contenu_et_mot_cle_ne_se_confondent_pas(seeded):
    r = ingest([{"text_local": "kakao", "text_fr": "cacao", "id": "x"},
                {**_MOT, "id": "x"}], language="bci", actor="loc")
    assert r["accepted"] == 2


def test_mot_cle_accepte_et_corrige_mais_jamais_promu_ni_dans_le_corpus(seeded):
    ingest([_MOT], language="bci", actor="loc")
    tid = workflow.list_tasks(language="bci", status="bronze")[0]["id"]
    assert workflow.edit_text(tid, language="bci", text_local="kakaw", text_fr="cacao")["ok"]
    assert workflow.decide(tid, "admin_accepted", language="bci")["ok"]
    p = workflow.promote(tid, language="bci", actor="loc")
    assert p == {"ok": False, "reason": "not_promotable", "kind": "mot_cle"}
    # même forcé en 'production' en base, il ne sort ni dans le corpus ni dans la couverture
    with get_conn(autocommit=True) as conn:
        conn.execute("UPDATE productions SET status = 'production', concept_id = 'c1' WHERE id = %s", (int(tid),))
    assert workflow.list_corpus(language="bci") == []
    assert repo.covered_concept_ids(language="bci") == set()


def test_route_validations_par_type(seeded, monkeypatch, tmp_path):
    paire = {"kind": "paire_qr", "text_local": "Blɛ benin yɛ be lua kakao ɔ ?",
             "text_fr": "Quand planter le cacao ?", "reponse_bci": "Be lua i ...",
             "reponse_fr": "On le plante ...", "id": "q1"}
    ingest([_MOT, paire, {"text_local": "a", "text_fr": "b"}], language="bci", actor="loc")
    c = _client(monkeypatch, tmp_path)
    mots = c.get("/tasks/validations", params={"kind": "mot_cle"}).json()
    assert [e["text_local"] for e in mots["entries"]] == ["kakao"]
    paires = c.get("/tasks/validations", params={"kind": "paire_qr"}).json()["entries"]
    assert paires[0]["meta"]["reponse_fr"] == "On le plante ..."
    assert c.get("/tasks/validations", params={"kind": "contenu"}).json()["entries"] == []
