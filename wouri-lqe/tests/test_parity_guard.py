"""Garde parité-avant-extension sur /ingest (ADR-0034 P2).

Une langue < 100% couverte ne peut pas recevoir de saisie libre (extension) ; elle peut
toujours recevoir des réponses aux assignations (entrées avec un concept_id RÉEL du corpus).
Un concept_id arbitraire ne contourne pas la garde. Une fois la langue à 100%, la saisie
libre redevient permise.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import language_registry as reg
from app.db import get_conn

_LOC = [{"user": "loc", "password": "locpass12", "language": "bci"}]


def _speaker(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import ingest as ingest_router
    from app.routers import session as session_router
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(ingest_router.router)
    c = TestClient(app)
    c.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    return c


def _cover(concept_id, language):
    with get_conn(autocommit=True) as conn:
        conn.execute(
            "INSERT INTO productions (concept_id, language, status)"
            " VALUES (%s, %s, 'production')",
            (concept_id, language),
        )


def test_free_ingest_blocked_when_not_up_to_date(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    c = _speaker(monkeypatch, tmp_path)
    r = c.post("/ingest/json", json=[{"text_local": "libre", "text_fr": "free"}])
    assert r.status_code == 409  # extension bloquée (parité avant extension)


def test_bogus_concept_id_does_not_bypass_guard(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    c = _speaker(monkeypatch, tmp_path)
    # un concept_id absent du corpus ne doit PAS contourner la garde
    r = c.post("/ingest/json", json=[{"text_local": "libre", "text_fr": "free", "concept_id": "zzz"}])
    assert r.status_code == 409


def test_assignment_response_allowed_even_when_not_up_to_date(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    c = _speaker(monkeypatch, tmp_path)
    # entrée avec un concept_id RÉEL du corpus (réponse d'assignation) -> toujours permise
    r = c.post("/ingest/json", json=[
        {"text_local": "reponse", "text_fr": "Plante ton mais", "concept_id": "mais_conseil_001"},
    ])
    assert r.status_code == 200 and r.json()["accepted"] == 1


def test_mixed_batch_rejected(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    c = _speaker(monkeypatch, tmp_path)
    # lot mixte (réponse + libre) : refusé en bloc tant que la langue n'est pas à jour
    r = c.post("/ingest/json", json=[
        {"text_local": "a", "text_fr": "Plante ton mais", "concept_id": "mais_conseil_001"},
        {"text_local": "libre", "text_fr": "free"},
    ])
    assert r.status_code == 409


def test_free_ingest_allowed_when_up_to_date(corpus, monkeypatch, tmp_path):
    reg.upsert_language("bci", "Baoule", status="active")
    _cover("mais_conseil_001", "bci")
    _cover("riz_conseil_001", "bci")  # les 2 concepts du corpus couverts -> bci à jour
    c = _speaker(monkeypatch, tmp_path)
    r = c.post("/ingest/json", json=[{"text_local": "nouvelle", "text_fr": "libre ok"}])
    assert r.status_code == 200 and r.json()["accepted"] == 1  # extension redevient permise
