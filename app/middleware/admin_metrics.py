"""Instrumentation HTTP sans contenu PII pour le dashboard #41."""
from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.admin_metrics import (
    RequestMetric,
    record_request_metric_background,
)

_MONITORED_PREFIXES = (
    "/api/chat",
    "/api/asr",
    "/api/stt",
    "/api/tts",
)
_ALLOWED_CONTEXT_FIELDS = {
    "intent",
    "culture",
    "source",
    "asr_success",
    "nlu_out_of_scope",
}


def set_request_metric_context(request: Request, **fields: Any) -> None:
    """Ajoute uniquement des métadonnées internes autorisées à la requête."""
    current = getattr(request.state, "admin_metric", {})
    if not isinstance(current, dict):
        current = {}
    current.update(
        {
            key: value
            for key, value in fields.items()
            if key in _ALLOWED_CONTEXT_FIELDS
        }
    )
    request.state.admin_metric = current


def _is_monitored(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _MONITORED_PREFIXES)


def _normalised_endpoint(scope: Scope) -> str:
    """Utilise le template de route, jamais la query string ou le nom de fichier."""
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and _is_monitored(route_path):
        return route_path

    path = str(scope.get("path", ""))
    for prefix in _MONITORED_PREFIXES:
        if path.startswith(prefix):
            return prefix
    return "/api/unknown"


class AdminMetricsMiddleware:
    """Middleware ASGI léger : mesure la durée totale et le statut."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_monitored(str(scope.get("path", ""))):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
            state = scope.get("state", {})
            context = state.get("admin_metric", {}) if isinstance(state, dict) else {}
            if not isinstance(context, dict):
                context = {}

            record_request_metric_background(
                RequestMetric(
                    endpoint=_normalised_endpoint(scope),
                    method=str(scope.get("method", "UNKNOWN")),
                    status_code=status_code,
                    duration_ms=duration_ms,
                    intent=context.get("intent"),
                    culture=context.get("culture"),
                    source=context.get("source"),
                    asr_success=context.get("asr_success"),
                    nlu_out_of_scope=context.get("nlu_out_of_scope"),
                )
            )
