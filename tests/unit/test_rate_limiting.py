"""Tests du rate limiting global configurable + exemption clé API (issue #307, ADR-0018).

Contrats testés :
- RATE_LIMIT (env/.env) a un effet MESURABLE : au-delà de la limite → 429.
- Une requête authentifiée par clé API interne valide (courante OU précédente,
  fenêtre de rotation #222) n'est JAMAIS rate-limitée (trafic whatsapp-server).
- Pas de bypass via X-Forwarded-For : un header forgé ne change ni la clé de
  comptage ni l'exemption (l'exemption est cryptographique, pas IP).
- Aucun décorateur @limiter.limit ne subsiste dans les routers (garde-fou
  anti-régression : un décorateur override default_limits dans slowapi).
- RATE_LIMIT au format invalide → refus explicite au démarrage (fail-fast).
- is_valid_api_key : comparaison constante, mode dev (pas de clé) → False.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

ROUTERS_DIR = Path(__file__).resolve().parents[2] / "app" / "routers"


@pytest.fixture(autouse=True)
def _restore_security_module(monkeypatch):
    """Chaque test recharge app.security avec une env dédiée ; on restaure
    l'état par défaut APRÈS (une fois l'env monkeypatchée annulée) pour ne
    pas polluer les autres fichiers de tests qui importent app.security."""
    yield
    monkeypatch.undo()
    import app.config

    app.config.get_settings.cache_clear()
    importlib.reload(app.config)
    import app.security

    importlib.reload(app.security)


def _reload_security(monkeypatch, **env):
    """Recharge app.config + app.security avec une env contrôlée."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.config

    app.config.get_settings.cache_clear()
    importlib.reload(app.config)
    import app.security

    return importlib.reload(app.security)


def _build_app(security_module):
    """App minimale câblée comme app/main.py (limiter + middleware + handler)."""
    from app.middleware.rate_limit import ApiKeyExemptRateLimitMiddleware

    application = FastAPI()
    application.state.limiter = security_module.limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.add_middleware(ApiKeyExemptRateLimitMiddleware)

    @application.get("/t")
    async def target():
        return {"ok": True}

    @application.get("/health")
    @security_module.limiter.exempt
    async def health():
        return {"status": "ok"}

    return application


# ─────────────────────────────────────────────
# RATE_LIMIT effectif
# ─────────────────────────────────────────────


def test_rate_limit_env_effectif_429_au_dela(monkeypatch):
    sec = _reload_security(monkeypatch, RATE_LIMIT="3/minute", API_SECRET_KEY="cle_prod")
    client = TestClient(_build_app(sec))

    codes = [client.get("/t").status_code for _ in range(4)]

    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_health_exempt_de_la_limite(monkeypatch):
    """La sonde /health (healthcheck Docker) n'est jamais throttlée."""
    sec = _reload_security(monkeypatch, RATE_LIMIT="2/minute", API_SECRET_KEY="cle_prod")
    client = TestClient(_build_app(sec))

    codes = [client.get("/health").status_code for _ in range(6)]

    assert codes == [200] * 6


# ─────────────────────────────────────────────
# Exemption par clé API interne
# ─────────────────────────────────────────────


def test_cle_api_valide_jamais_limitee(monkeypatch):
    sec = _reload_security(monkeypatch, RATE_LIMIT="2/minute", API_SECRET_KEY="cle_prod")
    client = TestClient(_build_app(sec))

    codes = [
        client.get("/t", headers={"X-API-Key": "cle_prod"}).status_code
        for _ in range(8)
    ]

    assert codes == [200] * 8


def test_cle_precedente_exemptee_pendant_rotation(monkeypatch):
    """Fenêtre de rotation #222 : la clé précédente reste exemptée."""
    sec = _reload_security(
        monkeypatch,
        RATE_LIMIT="2/minute",
        API_SECRET_KEY="nouvelle",
        API_SECRET_KEY_PREVIOUS="ancienne",
    )
    client = TestClient(_build_app(sec))

    codes = [
        client.get("/t", headers={"X-API-Key": "ancienne"}).status_code
        for _ in range(6)
    ]

    assert codes == [200] * 6


def test_cle_invalide_reste_limitee(monkeypatch):
    sec = _reload_security(monkeypatch, RATE_LIMIT="2/minute", API_SECRET_KEY="cle_prod")
    client = TestClient(_build_app(sec))

    codes = [
        client.get("/t", headers={"X-API-Key": "fausse_cle"}).status_code
        for _ in range(4)
    ]

    assert 429 in codes


# ─────────────────────────────────────────────
# Anti-bypass X-Forwarded-For
# ─────────────────────────────────────────────


def test_pas_de_bypass_via_x_forwarded_for(monkeypatch):
    """Un XFF forgé (127.0.0.1) sans clé valide ne lève PAS la limite :
    l'exemption est par clé API, jamais par IP/sentinelle."""
    sec = _reload_security(monkeypatch, RATE_LIMIT="2/minute", API_SECRET_KEY="cle_prod")
    client = TestClient(_build_app(sec))

    codes = [
        client.get("/t", headers={"X-Forwarded-For": "127.0.0.1"}).status_code
        for _ in range(4)
    ]

    assert 429 in codes


def test_xff_ne_fragmente_pas_le_compteur(monkeypatch):
    """Des XFF variés (rotation d'IP fictives) ne créent pas des compteurs
    distincts : sans proxy de confiance, le header est ignoré (clé = IP réelle)."""
    sec = _reload_security(monkeypatch, RATE_LIMIT="3/minute", API_SECRET_KEY="cle_prod")
    client = TestClient(_build_app(sec))

    codes = [
        client.get("/t", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
        for i in range(5)
    ]

    assert 429 in codes


# ─────────────────────────────────────────────
# Garde-fous statiques et de démarrage
# ─────────────────────────────────────────────


def test_aucun_decorateur_limiter_dans_les_routers():
    """ADR-0018 : un @limiter.limit dans un router override default_limits →
    RATE_LIMIT redeviendrait silencieusement sans effet. Interdit."""
    offenders = [
        f.name
        for f in ROUTERS_DIR.glob("*.py")
        if "@limiter.limit(" in f.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"@limiter.limit interdit (ADR-0018) : {offenders}"


def test_rate_limit_invalide_refus_au_demarrage(monkeypatch):
    with pytest.raises(ValueError, match="RATE_LIMIT"):
        _reload_security(monkeypatch, RATE_LIMIT="nimporte_quoi", API_SECRET_KEY="k")


# ─────────────────────────────────────────────
# is_valid_api_key
# ─────────────────────────────────────────────


def test_is_valid_api_key_mode_dev_sans_cle(monkeypatch):
    """Pas de clé configurée (dev) → aucune clé n'est « valide » pour
    l'exemption : tout le monde est limité (défaut sûr)."""
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    monkeypatch.delenv("API_SECRET_KEY_PREVIOUS", raising=False)
    sec = _reload_security(monkeypatch, RATE_LIMIT="120/minute")

    assert sec.is_valid_api_key("nimporte") is False
    assert sec.is_valid_api_key(None) is False


def test_cle_non_ascii_rejetee_sans_crash(monkeypatch):
    """Starlette décode les headers en latin-1 : un X-API-Key non-ASCII doit
    donner « invalide » (et rester rate-limité), jamais un TypeError → 500
    hors comptage (compare_digest(str, str) refuse le non-ASCII)."""
    sec = _reload_security(monkeypatch, RATE_LIMIT="2/minute", API_SECRET_KEY="cle_prod")

    assert sec.is_valid_api_key("caféÿ") is False

    client = TestClient(_build_app(sec))
    # Forme wire (bytes latin-1) : ce qu'enverrait un client forgé — httpx
    # refuse les str non-ASCII mais accepte les bytes tels quels.
    codes = [
        client.get("/t", headers=[(b"x-api-key", "café".encode("latin-1"))]).status_code
        for _ in range(4)
    ]
    assert 500 not in codes
    assert 429 in codes


def test_is_valid_api_key_courante_et_precedente(monkeypatch):
    sec = _reload_security(
        monkeypatch,
        RATE_LIMIT="120/minute",
        API_SECRET_KEY="courante",
        API_SECRET_KEY_PREVIOUS="ancienne",
    )

    assert sec.is_valid_api_key("courante") is True
    assert sec.is_valid_api_key("ancienne") is True
    assert sec.is_valid_api_key("autre") is False
    assert sec.is_valid_api_key(None) is False
    assert sec.is_valid_api_key("") is False
