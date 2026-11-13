"""Route GET /corpus — lecture d'une autre langue, réservée aux admins (ADR-0049).

`adc.admin` a la langue `*` : sans paramètre il ne verrait rien, sa session n'étant
liée à aucune langue. Il lui faut donc `?language=bci` pour construire les messages
système. Ce que ces tests retiennent, c'est que ce paramètre **ne perce pas**
l'isolation inter-locuteurs d'ADR-0034.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import workflow
from app.services.ingest import ingest

_LOC = [{"user": "loc", "password": "locpass12", "language": "bci"}]


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import corpus as corpus_router
    from app.routers import session as session_router

    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(corpus_router.router)
    return TestClient(app)


def _promouvoir(texte: str, langue: str) -> str:
    """Un contenu promu dans `langue`, tel que le corpus le sert."""
    assert ingest([{"text_local": texte, "text_fr": "fr", "id": texte}],
                  language=langue, actor="prov")["accepted"] == 1
    tid = workflow.list_tasks(language=langue)[0]["id"]
    assert workflow.decide(tid, "admin_accepted", language=langue)["ok"] is True
    assert workflow.promote(tid, language=langue, actor="admin")["ok"] is True
    return tid


def test_sans_parametre_le_comportement_ne_change_pas(seeded, monkeypatch, tmp_path):
    """L'appel existant du front n'est pas touché : la langue de session."""
    _promouvoir("Akwaba", "bci")
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    r = client.get("/corpus")
    assert r.status_code == 200
    assert r.json()["language"] == "bci" and r.json()["count"] == 1


def test_un_locuteur_ne_peut_pas_lire_une_autre_langue(seeded, monkeypatch, tmp_path):
    """Le cœur de la garde : le paramètre ne perce pas l'isolation (ADR-0034)."""
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    assert client.get("/corpus?language=dyu").status_code == 403
    # Même sa PROPRE langue est refusée : seul un admin passe le paramètre.
    assert client.get("/corpus?language=bci").status_code == 403


def test_un_admin_lit_la_langue_demandee(seeded, monkeypatch, tmp_path):
    _promouvoir("Akwaba", "bci")
    _promouvoir("Aw ni ce", "dyu")
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})

    bci = client.get("/corpus?language=bci").json()
    assert bci["language"] == "bci" and bci["count"] == 1
    assert bci["entries"][0]["text_local"] == "Akwaba"

    dyu = client.get("/corpus?language=dyu").json()
    assert dyu["language"] == "dyu" and dyu["count"] == 1
    assert dyu["entries"][0]["text_local"] == "Aw ni ce"


def test_admin_sans_parametre_ne_voit_rien(seeded, monkeypatch, tmp_path):
    """C'est la raison d'être du paramètre : la langue `*` ne sert aucun corpus."""
    _promouvoir("Akwaba", "bci")
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    assert client.get("/corpus").json()["count"] == 0


def test_langue_inconnue_refusee(seeded, monkeypatch, tmp_path):
    client = _app(monkeypatch, tmp_path)
    client.post("/auth/login", json={"user": "admin", "password": "adminpass1"})
    assert client.get("/corpus?language=zzz").status_code == 400


def test_sans_session_rien(seeded, monkeypatch, tmp_path):
    assert _app(monkeypatch, tmp_path).get("/corpus?language=bci").status_code == 401
