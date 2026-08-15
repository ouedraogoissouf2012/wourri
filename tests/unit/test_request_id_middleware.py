"""Tests — middleware de correlation X-Request-ID (L5a, issue #412).

Verifie : generation si absent, echo si en-tete client sur, rejet + regeneration
si en-tete non conforme (anti-injection), presence dans l'en-tete de reponse et
sur request.state. Petite app FastAPI dediee (pas app.main -> pas de lifespan ML).
"""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.request_id import RequestIdMiddleware, generate_request_id


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    def ping(request: Request):  # noqa: ANN001
        return {"rid": getattr(request.state, "request_id", None)}

    return TestClient(app)


def test_generates_request_id_when_absent():
    resp = _client().get("/ping")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid and len(rid) >= 8
    # Le meme id est expose au handler via request.state.
    assert resp.json()["rid"] == rid


def test_echoes_valid_client_request_id():
    valid = "queue-ABC_123.4:5"
    resp = _client().get("/ping", headers={"X-Request-ID": valid})
    assert resp.headers["x-request-id"] == valid
    assert resp.json()["rid"] == valid


def test_rejects_unsafe_request_id_and_generates_new():
    resp = _client().get("/ping", headers={"X-Request-ID": "bad id <script>"})
    rid = resp.headers["x-request-id"]
    assert rid != "bad id <script>"
    assert " " not in rid and "<" not in rid


def test_rejects_overlong_request_id():
    overlong = "a" * 500
    resp = _client().get("/ping", headers={"X-Request-ID": overlong})
    assert resp.headers["x-request-id"] != overlong


def test_generate_request_id_is_nonempty_and_unique():
    a = generate_request_id()
    b = generate_request_id()
    assert a and b and a != b
