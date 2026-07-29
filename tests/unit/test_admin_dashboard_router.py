"""Tests HTTP du dashboard administrateur #41."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import admin
from app.security import require_api_key


def _dashboard_payload():
    observed_at = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    recent = {
        "observed_at": observed_at,
        "endpoint": "/api/chat/",
        "method": "POST",
        "status_code": 200,
        "duration_ms": 120,
        "intent": "CONSEIL_PRODUCTION",
        "culture": "CULTURE_RIZ",
        "source": "ivr_exact",
        "asr_success": None,
        "nlu_out_of_scope": False,
    }
    return {
        "generated_at": observed_at,
        "days": 7,
        "summary": {
            "total_requests": 4,
            "success_rate": 0.75,
            "average_duration_ms": 125.5,
            "p95_duration_ms": 180.0,
            "asr_success_rate": 0.5,
            "nlu_in_scope_rate": 0.75,
        },
        "daily": [{"day": date(2026, 7, 29), "requests": 4, "errors": 1}],
        "top_intents": [{"label": "CONSEIL_PRODUCTION", "count": 3}],
        "top_cultures": [{"label": "CULTURE_RIZ", "count": 2}],
        "endpoint_counts": [{"label": "/api/chat/", "count": 4}],
        "recent_requests": [recent],
        "recent_errors": [
            {
                **recent,
                "status_code": 503,
                "error_kind": "server_error",
            }
        ],
    }


def _client(monkeypatch, *, payload=None, enabled=True):
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            app_name="WOURRI",
            admin_metrics_enabled=enabled,
        ),
    )
    if payload is not None:
        monkeypatch.setattr(admin, "get_dashboard_data", lambda **kwargs: payload)

    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


def test_dashboard_shell_returns_200_with_security_headers(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/dashboard")

    assert response.status_code == 200
    assert "Observabilité agricole" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_dashboard_data_returns_typed_aggregates(monkeypatch):
    client = _client(monkeypatch, payload=_dashboard_payload())

    response = client.get("/admin/dashboard/data?days=7&recent_limit=12")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_requests"] == 4
    assert body["top_intents"][0]["label"] == "CONSEIL_PRODUCTION"
    assert body["recent_requests"][0]["culture"] == "CULTURE_RIZ"
    assert "message" not in body["recent_requests"][0]
    assert "transcription" not in body["recent_requests"][0]
    assert "user_id" not in body["recent_requests"][0]


def test_dashboard_data_requires_auth_dependency(monkeypatch):
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(app_name="WOURRI", admin_metrics_enabled=True),
    )
    app = FastAPI()
    app.include_router(admin.router)

    def reject():
        raise HTTPException(status_code=403, detail="forbidden")

    app.dependency_overrides[require_api_key] = reject
    response = TestClient(app).get("/admin/dashboard/data")

    assert response.status_code == 403


def test_dashboard_data_returns_503_when_disabled(monkeypatch):
    client = _client(monkeypatch, enabled=False)

    response = client.get("/admin/dashboard/data")

    assert response.status_code == 503


def test_dashboard_data_hides_database_exception(monkeypatch):
    client = _client(monkeypatch, payload=_dashboard_payload())
    monkeypatch.setattr(
        admin,
        "get_dashboard_data",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("secret DSN")),
    )

    response = client.get("/admin/dashboard/data")

    assert response.status_code == 503
    assert response.json()["detail"] == "Métriques temporairement indisponibles."
    assert "secret DSN" not in response.text
