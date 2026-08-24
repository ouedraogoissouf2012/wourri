"""Production audio (ADR-0034 P3) : upload -> production bronze avec audio_url -> lecture média."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import workflow

_LOC = [{"user": "loc", "password": "locpass12", "language": "bci"}]


def _speaker(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import ingest as ingest_router
    from app.routers import media as media_router
    from app.routers import session as session_router
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(ingest_router.router)
    app.include_router(media_router.router)
    c = TestClient(app)
    c.post("/auth/login", json={"user": "loc", "password": "locpass12"})
    return c


def test_audio_response_creates_production_and_is_playable(seeded, monkeypatch, tmp_path):
    c = _speaker(monkeypatch, tmp_path)
    audio_bytes = b"RIFF....WAVEfake-audio-content"
    r = c.post(
        "/ingest/audio",
        data={"concept_id": "mais_semis_001", "text_fr": "Comment semer le mais",
              "text_local": "kaba (bci)"},
        files={"audio": ("reponse.webm", audio_bytes, "audio/webm")},
    )
    assert r.status_code == 200 and r.json()["ok"] is True

    row = workflow.list_tasks(language="bci")[0]
    assert row["concept_id"] == "mais_semis_001"
    assert row["audio_url"] and row["audio_url"].startswith("audio/")
    assert row["text_local"] == "kaba (bci)"

    # l'audio est relisible via /media (mêmes octets)
    name = row["audio_url"].split("/")[-1]
    m = c.get("/media/" + name)
    assert m.status_code == 200
    assert m.content == audio_bytes
    assert m.headers["content-type"] == "audio/webm"


def test_audio_text_is_optional(seeded, monkeypatch, tmp_path):
    c = _speaker(monkeypatch, tmp_path)
    r = c.post(
        "/ingest/audio",
        data={"concept_id": "riz_semis_001", "text_fr": "Comment semer le riz"},
        files={"audio": ("r.webm", b"audio-bytes-here", "audio/webm")},
    )
    assert r.status_code == 200
    row = next(t for t in workflow.list_tasks(language="bci") if t["concept_id"] == "riz_semis_001")
    assert row["audio_url"]
    assert row["text_local"] == ""  # texte omis, accepté


def test_audio_requires_file(seeded, monkeypatch, tmp_path):
    c = _speaker(monkeypatch, tmp_path)
    r = c.post("/ingest/audio", data={"concept_id": "x", "text_fr": "y"})
    assert r.status_code == 422  # champ audio (File) manquant -> validation FastAPI


def test_audio_rejects_bad_format(seeded, monkeypatch, tmp_path):
    c = _speaker(monkeypatch, tmp_path)
    r = c.post(
        "/ingest/audio",
        data={"concept_id": "c1", "text_fr": "fr"},
        files={"audio": ("x.txt", b"not audio", "text/plain")},
    )
    assert r.status_code == 400
