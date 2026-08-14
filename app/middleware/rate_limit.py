# -*- coding: utf-8 -*-
"""
WOURI - Middleware de rate limiting avec exemption par clé API (issue #307, ADR-0018).

Applique les `default_limits` slowapi (= `RATE_LIMIT` du `.env`) à toutes les
routes, SAUF pour les requêtes authentifiées par la clé API interne — le
trafic légitime du whatsapp-server, seul client du backend (docs/vision.md).

Pourquoi un middleware maison plutôt que le `request_filter` slowapi : les
callbacks `Limiter._request_filters` sont appelés SANS la requête (`fn()`,
vérifié dans slowapi 0.1.9) — impossible d'y lire `X-API-Key`. On enveloppe
donc `SlowAPIASGIMiddleware` : clé valide → passe-droit direct, sinon
délégation au middleware slowapi qui applique `default_limits`.

Propriétés de sécurité (ADR-0018) :
- AUCUNE sentinelle « clé vide » ni exemption par IP : l'exemption est
  cryptographique (`secrets.compare_digest` dans `is_valid_api_key`),
  insensible à X-Forwarded-For et à la topologie réseau (local/Docker/prod).
- Les routes marquées `@limiter.exempt` (ex : /health, sonde Docker) restent
  gérées par slowapi lui-même.
"""
from __future__ import annotations

from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.security import is_valid_api_key


class ApiKeyExemptRateLimitMiddleware:
    """ASGI pur (pas de BaseHTTPMiddleware : pas de buffering, pas de coût)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._limited = SlowAPIASGIMiddleware(app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        api_key = Headers(scope=scope).get("x-api-key")
        if is_valid_api_key(api_key):
            # Trafic interne authentifié (whatsapp-server) : jamais throttlé.
            return await self.app(scope, receive, send)

        return await self._limited(scope, receive, send)
