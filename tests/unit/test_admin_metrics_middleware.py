"""Contrat du middleware d'observabilité sans PII."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.middleware import admin_metrics as middleware_module
from app.middleware.admin_metrics import (
    AdminMetricsMiddleware,
    set_request_metric_context,
)


def _client(monkeypatch):
    captured = []
    monkeypatch.setattr(
        middleware_module,
        "record_request_metric_background",
        captured.append,
    )

    app = FastAPI()
    app.add_middleware(AdminMetricsMiddleware)

    @app.post("/api/chat/{item}")
    async def monitored(request: Request, item: str):
        set_request_metric_context(
            request,
            intent="CONSEIL_PRODUCTION",
            culture="CULTURE_RIZ",
            source="ivr_exact",
            nlu_out_of_scope=False,
            forbidden_message="contenu à ne jamais stocker",
        )
        return {"ok": True, "item": item}

    @app.get("/api/asr/fail")
    async def failed_asr(request: Request):
        set_request_metric_context(request, asr_success=False)
        raise HTTPException(status_code=503, detail="ASR unavailable")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return TestClient(app), captured


def test_monitored_route_uses_template_and_context_without_query(monkeypatch):
    client, captured = _client(monkeypatch)

    response = client.post("/api/chat/private-value?phone=%2B22501020304")

    assert response.status_code == 200
    assert len(captured) == 1
    metric = captured[0]
    assert metric.endpoint == "/api/chat/{item}"
    assert metric.method == "POST"
    assert metric.status_code == 200
    assert metric.intent == "CONSEIL_PRODUCTION"
    assert metric.culture == "CULTURE_RIZ"
    assert metric.source == "ivr_exact"
    assert metric.nlu_out_of_scope is False
    assert "private-value" not in metric.endpoint
    assert "phone" not in metric.endpoint
    assert not hasattr(metric, "forbidden_message")


def test_http_error_is_recorded_without_exception_detail(monkeypatch):
    client, captured = _client(monkeypatch)

    response = client.get("/api/asr/fail")

    assert response.status_code == 503
    assert len(captured) == 1
    metric = captured[0]
    assert metric.endpoint == "/api/asr/fail"
    assert metric.status_code == 503
    assert metric.asr_success is False
    assert not hasattr(metric, "detail")


def test_unmonitored_route_is_ignored(monkeypatch):
    client, captured = _client(monkeypatch)

    assert client.get("/health").status_code == 200
    assert captured == []
