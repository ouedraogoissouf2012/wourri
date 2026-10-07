"""Baoulé : CSV/XLSX parse + auth user/mdp."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin_baoule
from app.services import baoule_auth
from app.services import baoule_provider as bp
from app.services import improvement_queue as iq


def test_parse_csv_headers_fr():
    raw = "baoule;francais;intent\nBonjour bci;Bonjour FR;CONSEIL_PRODUCTION\n".encode("utf-8")
    rows = bp.parse_csv_bytes(raw)
    assert len(rows) == 1
    assert rows[0]["text_local"] == "Bonjour bci"
    assert rows[0]["text_fr"] == "Bonjour FR"


def test_parse_csv_cp1252_excel_fr():
    # Excel Windows FR : point-virgule + accents en cp1252
    raw = "baoulé;français\nPhrase été;Phrase FR\n".encode("cp1252")
    rows = bp.parse_csv_bytes(raw)
    assert len(rows) == 1
    assert "été" in rows[0]["text_local"] or "ete" in rows[0]["text_local"].lower()
    assert rows[0]["text_fr"] == "Phrase FR"


def test_parse_csv_two_columns_no_header_names():
    raw = "colA,colB\nlocal x,fr x\n".encode("utf-8")
    rows = bp.parse_csv_bytes(raw)
    assert rows[0]["text_local"] == "local x"
    assert rows[0]["text_fr"] == "fr x"


def test_parse_xlsx_roundtrip():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["text_local", "text_fr", "id"])
    ws.append(["loc x", "fr x", "bci_9"])
    buf = io.BytesIO()
    wb.save(buf)
    rows = bp.parse_xlsx_bytes(buf.getvalue())
    assert rows == [{"text_local": "loc x", "text_fr": "fr x", "id": "bci_9"}]


def test_auth_session(monkeypatch):
    monkeypatch.setenv("BAOULE_PROVIDER_USER", "provider1")
    monkeypatch.setenv("BAOULE_PROVIDER_PASSWORD", "secretpass99")
    monkeypatch.setenv("API_SECRET_KEY", "api-key-for-hmac")
    assert baoule_auth.verify_password("provider1", "secretpass99")
    assert not baoule_auth.verify_password("provider1", "wrong")
    tok = baoule_auth.sign_session("provider1")
    assert baoule_auth.read_session(tok)["u"] == "provider1"


def test_login_and_upload_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("BAOULE_PROVIDER_USER", "provider1")
    monkeypatch.setenv("BAOULE_PROVIDER_PASSWORD", "secretpass99")
    monkeypatch.setenv("API_SECRET_KEY", "api-key-for-hmac")
    path = tmp_path / "t.jsonl"
    monkeypatch.setattr(iq, "DEFAULT_TASKS_PATH", path)

    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app)

    bad = client.post(
        "/admin/baoule/login",
        data={"username": "provider1", "password": "nope"},
    )
    assert bad.status_code == 401

    ok = client.post(
        "/admin/baoule/login",
        data={"username": "provider1", "password": "secretpass99"},
        follow_redirects=False,
    )
    assert ok.status_code == 303

    csv_body = "text_local,text_fr\nA local,A fr\n".encode("utf-8")
    up = client.post(
        "/admin/baoule/api/upload",
        files={"file": ("data.csv", csv_body, "text/csv")},
    )
    assert up.status_code == 200
    assert up.json()["accepted"] == 1
    tasks = client.get("/admin/baoule/api/tasks").json()
    assert tasks["language"] == "bci"
    assert len(tasks["tasks"]) == 1


def _cookie_fabrique(base_du_secret: str) -> str:
    """Cookie signé par quelqu'un qui connaît la base du secret, sans se connecter."""
    body = json.dumps(
        {"u": "intrus", "exp": int(time.time()) + 3600, "role": "baoule_provider"},
        separators=(",", ":"),
    )
    cle = hashlib.sha256(base_du_secret.encode("utf-8")).digest()
    sig = hmac.new(cle, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def test_sans_identifiants_provider_aucune_session_valide(monkeypatch):
    """Sans BAOULE_PROVIDER_* ni clé API, la clé de signature valait sha256("||") :
    un cookie fabriqué donnait accès aux routes /admin/baoule/api/*."""
    monkeypatch.delenv("BAOULE_PROVIDER_USER", raising=False)
    monkeypatch.delenv("BAOULE_PROVIDER_PASSWORD", raising=False)
    monkeypatch.setattr(baoule_auth, "get_settings", lambda: SimpleNamespace(api_secret_key=""))

    assert baoule_auth.read_session(_cookie_fabrique("||")) is None
    with pytest.raises(RuntimeError):
        baoule_auth.sign_session("intrus")

    app = FastAPI()
    app.include_router(admin_baoule.router)
    client = TestClient(app, cookies={baoule_auth.COOKIE_NAME: _cookie_fabrique("||")})
    assert client.get("/admin/baoule/api/tasks").status_code == 401


def test_cle_api_fournie_par_fichier_entre_dans_la_signature(monkeypatch):
    """En prod, la clé API arrive par API_SECRET_KEY_FILE : os.getenv la voyait
    vide, et la signature ne reposait plus que sur les identifiants provider."""
    monkeypatch.setenv("BAOULE_PROVIDER_USER", "provider1")
    monkeypatch.setenv("BAOULE_PROVIDER_PASSWORD", "secretpass99")
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        baoule_auth, "get_settings", lambda: SimpleNamespace(api_secret_key="cle-du-fichier")
    )

    # Signature calculée sans la clé API (ancien comportement) : refusée
    assert baoule_auth.read_session(_cookie_fabrique("|provider1|secretpass99")) is None
    # Session émise après connexion : acceptée
    tok = baoule_auth.sign_session("provider1")
    assert baoule_auth.read_session(tok)["u"] == "provider1"
