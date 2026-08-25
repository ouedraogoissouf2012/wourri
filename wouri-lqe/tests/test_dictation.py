"""Dictée guidée ASR (ADR-0035) : import (admin) → lecture/enregistrement (locuteur)
→ export dataset (admin, format HF `audiofolder`). Sur Postgres réel (fixture `seeded`).

Vérifie le cœur : transcription garantie (texte imposé = `transcription`), idempotence de
l'import, isolation par langue, et cohérence de l'export (audio ↔ metadata.csv)."""
import csv
import io
import json
import zipfile

from app.services import dictation as svc

_ADMIN = {"user": "adm", "password": "admin-pass-12"}
_LOC_BCI = [{"user": "loc", "password": "locpass12", "language": "bci"}]

_CSV_BCI = (
    "filiere,francais,baoule\r\n"
    "CACAO,Quand planter le cacao ?,Blɛ benin nun yɛ ɔ fata kɛ lua kakao\r\n"
    "RIZ,Comment semer le riz ?,Wafa sɛ amun gua mɔlu\r\n"
    "MAÏS,Comment semer le maïs ?,Wafa sɛ amun gua kaba\r\n"
).encode("utf-8")

_CSV_DYU = (
    "filiere,francais,baoule\r\n"
    "CACAO,Question dioula ?,malo dyu phrase\r\n"
).encode("utf-8")


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC_BCI))
    monkeypatch.setenv("LQE_ADMIN_USER", _ADMIN["user"])
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", _ADMIN["password"])


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers import dictation as dictation_router
    from app.routers import session as session_router

    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(dictation_router.router)
    return TestClient(app)


def _admin(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    c = _client()
    assert c.post("/auth/login", json=_ADMIN).status_code == 200
    return c


def _speaker(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    c = _client()
    assert c.post("/auth/login", json={"user": "loc", "password": "locpass12"}).status_code == 200
    return c


def _import(client, language, payload=_CSV_BCI, name="phrases.csv"):
    return client.post(
        "/dictation/import",
        data={"language": language},
        files={"file": (name, payload, "text/csv")},
    )


# ---------- parsing (fonction pure, sans base) ----------

def test_parse_prompts_maps_named_columns():
    rows = svc.parse_prompts("phrases.csv", _CSV_BCI)
    assert len(rows) == 3
    assert rows[0] == {
        "filiere": "CACAO",
        "text_fr": "Quand planter le cacao ?",
        "text_local": "Blɛ benin nun yɛ ɔ fata kɛ lua kakao",
    }


def test_parse_prompts_json():
    payload = json.dumps(
        {"prompts": [{"filiere": "IGNAME", "text_fr": "X ?", "text_local": "abc"}]}
    ).encode("utf-8")
    assert svc.parse_prompts("x.json", payload) == [
        {"filiere": "IGNAME", "text_fr": "X ?", "text_local": "abc"}
    ]


def test_parse_prompts_ignores_rows_without_local():
    csv_bytes = "filiere,francais,baoule\r\nCACAO,Question ?,\r\n".encode("utf-8")
    assert svc.parse_prompts("p.csv", csv_bytes) == []


# ---------- import (admin) ----------

def test_import_inserts_and_is_idempotent(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    r = _import(a, "bci")
    assert r.status_code == 200
    assert r.json() == {"inserted": 3, "skipped": 0, "language": "bci"}
    # ré-import : les 3 doublons sont ignorés (idempotent par (language, prompt_hash))
    assert _import(a, "bci").json() == {"inserted": 0, "skipped": 3, "language": "bci"}


def test_import_rejects_unknown_language(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    assert _import(a, "xxx").status_code == 400


def test_import_requires_admin(seeded, monkeypatch, tmp_path):
    s = _speaker(monkeypatch, tmp_path)
    assert _import(s, "bci").status_code == 403


def test_import_rejects_empty_batch(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    empty = "filiere,francais,baoule\r\n".encode("utf-8")
    assert _import(a, "bci", payload=empty).status_code == 400


# ---------- supervision (admin) ----------

def test_admin_stats_by_language(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")
    assert a.get("/dictation/stats", params={"language": "bci"}).json() == {
        "language": "bci", "total": 3, "recorded": 0, "todo": 3
    }
    assert a.get("/dictation/stats", params={"language": "xxx"}).status_code == 400


def test_stats_requires_admin(seeded, monkeypatch, tmp_path):
    s = _speaker(monkeypatch, tmp_path)
    assert s.get("/dictation/stats", params={"language": "bci"}).status_code == 403


# ---------- lecture + progression (locuteur) ----------

def test_speaker_lists_prompts_and_progress(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")
    s = _speaker(monkeypatch, tmp_path)
    body = s.get("/dictation/prompts", params={"status": "todo"}).json()
    assert body["count"] == 3
    assert body["prompts"][0]["text_local"].startswith("Blɛ")  # UTF-8 préservé
    assert s.get("/dictation/progress").json() == {
        "language": "bci", "total": 3, "recorded": 0, "todo": 3
    }


# ---------- enregistrement audio + export dataset ----------

def test_record_audio_then_export_dataset(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")
    s = _speaker(monkeypatch, tmp_path)
    prompts = s.get("/dictation/prompts").json()["prompts"]

    clips = {}
    for p in prompts[:2]:
        audio_bytes = f"AUDIO-{p['id']}".encode("utf-8")
        clips[p["id"]] = (audio_bytes, p["text_local"])
        r = s.post(f"/dictation/{p['id']}/audio",
                   files={"audio": ("r.webm", audio_bytes, "audio/webm")})
        assert r.status_code == 200 and r.json()["ok"] is True

    assert s.get("/dictation/progress").json() == {
        "language": "bci", "total": 3, "recorded": 2, "todo": 1
    }

    e = a.get("/dictation/export", params={"language": "bci"})
    assert e.status_code == 200
    assert e.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(e.content))
    names = set(zf.namelist())
    assert "metadata.csv" in names

    meta = list(csv.DictReader(io.StringIO(zf.read("metadata.csv").decode("utf-8"))))
    assert len(meta) == 2
    for row in meta:
        assert row["file_name"] in names          # chaque manifeste pointe un clip présent
        assert row["file_name"].startswith("audio/")
        assert row["language"] == "bci"
    # transcription = texte IMPOSÉ (le cœur : paires audio↔texte garanties)
    assert {row["transcription"] for row in meta} == {t for _, t in clips.values()}
    # contrat COMPLET du manifeste : filière + français corrects (pas que la transcription)
    recorded = {p["id"] for p in prompts[:2]}
    by_transc = {p["text_local"]: p for p in prompts if p["id"] in recorded}
    for row in meta:
        p = by_transc[row["transcription"]]
        assert row["filiere"] == p["filiere"]
        assert row["text_fr"] == p["text_fr"]
    # les octets audio sont préservés à l'identique
    stored = {zf.read(n) for n in names if n.startswith("audio/")}
    assert stored == {b for b, _ in clips.values()}


def test_record_unknown_prompt_404(seeded, monkeypatch, tmp_path):
    s = _speaker(monkeypatch, tmp_path)
    r = s.post("/dictation/999999/audio",
               files={"audio": ("r.webm", b"x", "audio/webm")})
    assert r.status_code == 404


def test_record_rejects_bad_format(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")
    s = _speaker(monkeypatch, tmp_path)
    pid = s.get("/dictation/prompts").json()["prompts"][0]["id"]
    r = s.post(f"/dictation/{pid}/audio",
               files={"audio": ("x.txt", b"not audio", "text/plain")})
    assert r.status_code == 400


def test_export_without_recording_is_404(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")  # importées mais aucune enregistrée
    assert a.get("/dictation/export", params={"language": "bci"}).status_code == 404


# ---------- isolation par langue ----------

def test_language_isolation(seeded, monkeypatch, tmp_path):
    a = _admin(monkeypatch, tmp_path)
    _import(a, "dyu", payload=_CSV_DYU, name="d.csv")
    _import(a, "bci")
    s = _speaker(monkeypatch, tmp_path)  # compte de langue bci
    prompts = s.get("/dictation/prompts").json()["prompts"]
    assert prompts and {p["language"] for p in prompts} == {"bci"}  # jamais dyu


def test_record_foreign_language_prompt_is_404(seeded, monkeypatch, tmp_path):
    """Isolation d'ÉCRITURE : un locuteur bci ne peut pas enregistrer un prompt d'une autre
    langue même en connaissant son id (anti-IDOR). repo.get filtre par langue → 404, et le
    prompt dyu reste intact."""
    from app.services import dictation_repo

    a = _admin(monkeypatch, tmp_path)
    _import(a, "dyu", payload=_CSV_DYU, name="d.csv")
    dyu_id = dictation_repo.list_prompts(language="dyu")[0]["id"]
    s = _speaker(monkeypatch, tmp_path)  # compte de langue bci
    r = s.post(f"/dictation/{dyu_id}/audio",
               files={"audio": ("r.webm", b"x", "audio/webm")})
    assert r.status_code == 404
    assert dictation_repo.list_prompts(language="dyu")[0]["status"] == "todo"  # aucune écriture


def test_re_record_overwrites_audio(seeded, monkeypatch, tmp_path):
    """Ré-enregistrer une phrase déjà 'recorded' remplace l'audio sans doubler le compteur ;
    l'export porte le DERNIER enregistrement."""
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")
    s = _speaker(monkeypatch, tmp_path)
    pid = s.get("/dictation/prompts").json()["prompts"][0]["id"]
    s.post(f"/dictation/{pid}/audio", files={"audio": ("a.webm", b"FIRST", "audio/webm")})
    s.post(f"/dictation/{pid}/audio", files={"audio": ("b.webm", b"SECOND", "audio/webm")})
    assert s.get("/dictation/progress").json()["recorded"] == 1  # pas de double comptage

    e = a.get("/dictation/export", params={"language": "bci"})
    zf = zipfile.ZipFile(io.BytesIO(e.content))
    stored = {zf.read(n) for n in zf.namelist() if n.startswith("audio/")}
    assert stored == {b"SECOND"}


def test_export_skips_missing_audio_file(seeded, monkeypatch, tmp_path):
    """Un audio référencé mais absent du disque est ignoré à l'export (pas de crash, pas
    d'entrée fantôme dans metadata.csv)."""
    a = _admin(monkeypatch, tmp_path)
    _import(a, "bci")
    s = _speaker(monkeypatch, tmp_path)
    prompts = s.get("/dictation/prompts").json()["prompts"]
    refs = []
    for p in prompts[:2]:
        r = s.post(f"/dictation/{p['id']}/audio",
                   files={"audio": ("r.webm", f"A{p['id']}".encode("utf-8"), "audio/webm")})
        refs.append(r.json()["audio_url"])
    (tmp_path / "audio" / refs[0].split("/")[-1]).unlink()  # supprime un des deux fichiers

    e = a.get("/dictation/export", params={"language": "bci"})
    assert e.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(e.content))
    meta = list(csv.DictReader(io.StringIO(zf.read("metadata.csv").decode("utf-8"))))
    assert len(meta) == 1  # l'orphelin est ignoré
    assert len([n for n in zf.namelist() if n.startswith("audio/")]) == 1
