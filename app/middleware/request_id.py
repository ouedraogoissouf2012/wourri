"""Middleware de correlation X-Request-ID (L5a, issue #412).

Lit l'en-tete `X-Request-ID` entrant s'il est present ET conforme a un charset
sur (le serveur WhatsApp envoie le queueId Baileys) ; sinon en genere un
(uuid4). Le pose sur `request.state.request_id`, le renvoie dans l'en-tete de
reponse, et le journalise une fois par requete (hors sondes haute frequence).

Securite : la valeur cliente est reemise dans un en-tete de reponse ET
journalisee -> on rejette tout ce qui n'est pas `[A-Za-z0-9._:-]{1,200}`
(anti-injection CRLF dans les headers de reponse et anti log-forging).
"""
from __future__ import annotations

import logging
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_HEADER_BYTES = b"x-request-id"
_SAFE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
# Sondes haute frequence : id pose + renvoye mais NON journalise (anti-bruit).
_LOG_SKIP_PATHS = frozenset({"/health", "/ready", "/api/health/memory"})


def generate_request_id() -> str:
    """Genere un identifiant de requete opaque (uuid4 hex)."""
    return uuid.uuid4().hex


def _client_request_id(scope: Scope) -> str | None:
    """Retourne l'X-Request-ID client s'il est present et conforme, sinon None."""
    for name, value in scope.get("headers", []):
        if name == _HEADER_BYTES:
            try:
                candidate = value.decode("latin-1").strip()
            except Exception:
                return None
            return candidate if _SAFE_RE.match(candidate) else None
    return None


class RequestIdMiddleware:
    """Middleware ASGI de correlation X-Request-ID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _client_request_id(scope) or generate_request_id()

        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = request_id

        rid_bytes = request_id.encode("latin-1")

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, val)
                    for (key, val) in message.get("headers", [])
                    if key.lower() != _HEADER_BYTES
                ]
                headers.append((_HEADER_BYTES, rid_bytes))
                message["headers"] = headers
            await send(message)

        path = str(scope.get("path", ""))
        if path not in _LOG_SKIP_PATHS:
            logger.info(
                "[REQ] %s %s request_id=%s",
                str(scope.get("method", "?")),
                path,
                request_id,
            )

        await self.app(scope, receive, send_with_request_id)
