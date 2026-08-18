"""Baoulé : CSV/XLSX parse + auth user/mdp."""
from __future__ import annotations

import io

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
