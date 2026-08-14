# -*- coding: utf-8 -*-
"""
WOURI — Sécurité API

- X-API-Key : authentification simple sur toutes les routes /api/*
- Rate limiting (issue #307, ADR-0018) : limite GLOBALE unique pilotée par
  RATE_LIMIT (.env, défaut 120/minute), appliquée via default_limits +
  ApiKeyExemptRateLimitMiddleware. AUCUN @limiter.limit par route (un
  décorateur override default_limits dans slowapi → config morte —
  garde-fou : tests/unit/test_rate_limiting.py).
- Le trafic authentifié par clé API interne (whatsapp-server) est EXEMPTÉ du
  rate limiting — exemption cryptographique, pas de sentinelle IP.
- La clé est lue depuis .env (API_SECRET_KEY)
  Si non configurée → mode dev permissif (warn uniquement)
"""
import logging
import secrets as _secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from limits import parse_many
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

logger = logging.getLogger(__name__)

# Lecture via Pydantic Settings (qui charge .env correctement) plutôt que
# os.getenv() qui n'a pas connaissance du .env
_settings = get_settings()

# ── Rate limiter (partagé, instancié une seule fois) ──────────────────────────
# Fail-fast : un RATE_LIMIT invalide doit refuser le démarrage (sinon slowapi
# n'échouerait qu'à la première requête — panne différée et illisible).
try:
    parse_many(_settings.rate_limit)
except ValueError as exc:
    raise ValueError(
        f"RATE_LIMIT invalide : {_settings.rate_limit!r}. Format attendu du "
        'style "120/minute", "10/second" ou "1000/hour" (cf. .env.example).'
    ) from exc

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.rate_limit],
)

# ── API Key header ─────────────────────────────────────────────────────────────
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_SECRET_KEY: str | None = _settings.api_secret_key or None
# Issue #222 : clé précédente acceptée temporairement (rotation zero-downtime)
_API_SECRET_KEY_PREVIOUS: str | None = _settings.api_secret_key_previous or None

if not _API_SECRET_KEY:
    logger.warning(
        "[SECURITY] API_SECRET_KEY non configurée dans .env — "
        "authentification désactivée (mode dev)"
    )

if _API_SECRET_KEY_PREVIOUS:
    # Présence intentionnelle = rotation en cours. Logger un warning visible
    # pour rappeler à l'opérateur de purger cette variable après la fenêtre
    # de rotation (par défaut 5 min, cf. docs/deployment.md §rotation).
    logger.warning(
        "[SECURITY] API_SECRET_KEY_PREVIOUS définie → rotation en cours. "
        "Les 2 clés sont acceptées. Pense à vider API_SECRET_KEY_PREVIOUS "
        "après la fenêtre de transition (procédure : deployment.md §rotation)."
    )


def is_valid_api_key(api_key: str | None) -> bool:
    """True si `api_key` est la clé interne courante OU précédente (#222).

    Comparaison en temps constant (`secrets.compare_digest`) — la validation
    sert aussi de critère d'exemption du rate limiting (ADR-0018), elle ne
    doit pas fuiter d'information par timing.

    Mode dev (aucune clé configurée) → False : personne n'est « authentifié »,
    donc personne n'est exempté du rate limiting (défaut sûr) — l'accès aux
    routes reste, lui, permissif via require_api_key.
    """
    if not _API_SECRET_KEY or not api_key:
        return False
    # Comparaison sur BYTES : compare_digest(str, str) lève TypeError sur du
    # non-ASCII, et Starlette décode les headers en latin-1 → un X-API-Key
    # forgé avec un octet 0x80-0xFF ferait un 500 (non compté par le rate
    # limiting) au lieu d'un simple « clé invalide ».
    candidate = api_key.encode("utf-8")
    if _secrets.compare_digest(candidate, _API_SECRET_KEY.encode("utf-8")):
        return True
    if _API_SECRET_KEY_PREVIOUS and _secrets.compare_digest(
        candidate, _API_SECRET_KEY_PREVIOUS.encode("utf-8")
    ):
        return True
    return False


async def require_api_key(api_key: str | None = Depends(_API_KEY_HEADER)) -> None:
    """Dependency FastAPI : vérifie le header X-API-Key.

    Si API_SECRET_KEY n'est pas configurée → pass (mode dev).
    En production, toute requête sans clé valide reçoit un 403.

    Issue #222 : si API_SECRET_KEY_PREVIOUS est définie, accepte AUSSI
    cette clé (fenêtre de rotation zero-downtime).
    """
    if not _API_SECRET_KEY:
        return  # mode dev

    if is_valid_api_key(api_key):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Clé API invalide ou manquante (header X-API-Key requis)",
    )
