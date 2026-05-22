"""Tests d'intégration — endpoint `/admin/corpus-divergence-report` + persistance
des divergences en mode `dual` (Sprint F Phase D — ADR-0008).

Vérifie :
- Auth : 200 avec `X-API-Key` valide (mode prod) ou sans header (mode dev)
- Auth : 403 sans `X-API-Key` quand `API_SECRET_KEY` est configurée
  (`test_403_without_api_key_when_key_configured` — skip si pas de clé en dev)
- Endpoint répond 200 + schéma JSON valide
- Filtre `?days=N` fonctionne (fenêtre temporelle)
- Insertion d'une divergence via `_persist_divergence` apparaît dans le rapport
- Classification (`_classify_divergence`) couvre les 4 cas Phase D

Pré-requis : container Postgres dev up + migrations 0001/0002 appliquées.
Skip propre via `pytestmark` si Postgres absent (cf. tests/integration/_helpers.py).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.url_resolver import resolve_postgres_url
from tests.integration._helpers import postgres_reachable

_URL = resolve_postgres_url(raise_on_missing=False)
_REACHABLE = postgres_reachable(_URL)

pytestmark = pytest.mark.skipif(
    not _REACHABLE,
    reason=(
        "PostgreSQL+pgvector non disponible. Démarrer le container :\n"
        "  docker compose -f docker-compose.dev.yml up -d\n"
        "et exporter POSTGRES_URL ou le définir dans .env."
    ),
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def api_headers() -> dict:
    """En-têtes incluant `X-API-Key` si `API_SECRET_KEY` est configuré.

    En dev sans clé configurée → headers vides (l'auth est désactivée).
    En dev/CI avec clé → la clé est ajoutée pour passer `require_api_key`.
    """
    from app.security import _API_SECRET_KEY

    if _API_SECRET_KEY:
        return {"X-API-Key": _API_SECRET_KEY}
    return {}


@pytest.fixture(scope="module")
def client(api_headers):
    """TestClient FastAPI préconfiguré avec les headers d'auth."""
    from app.main import app

    c = TestClient(app)
    c.headers.update(api_headers)
    return c


@pytest.fixture
def clean_divergences():
    """Vide `corpus_divergences` avant + après le test pour isolation stricte.

    FIX-7 : utilise le singleton `_get_divergence_engine()` au lieu de
    recréer un engine à chaque test (cf. reviewer DRY/SOLID M2). Pas de
    `engine.dispose()` : le singleton est partagé entre tests.
    """
    from app.services.corpus_facade import _get_divergence_engine

    engine = _get_divergence_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE corpus_divergences RESTART IDENTITY;"))
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE corpus_divergences RESTART IDENTITY;"))


def _insert_match(
    *,
    intent="TEST_INTENT",
    cultures=None,
    chroma_id="match_id",
    pg_id="match_id",
    latency_chroma_ms=10,
    latency_pgvector_ms=20,
):
    """Helper : insère une divergence `match` via `_persist_divergence` facade.

    FIX-2 : utilise la fonction publique de la facade au lieu de dupliquer
    la requête INSERT (cf. reviewer DRY/SOLID M1). Garantit que tout
    changement de schéma `corpus_divergences` est répercuté automatiquement
    dans les tests.
    """
    from app.services.corpus_facade import _persist_divergence

    _persist_divergence(
        intent=intent,
        cultures=cultures or ["CULTURE_RIZ"],
        conditions=[],
        chroma_id=chroma_id,
        pg_id=pg_id,
        chroma_score=None,
        pg_score=None,
        classification="match",
        latency_chroma_ms=latency_chroma_ms,
        latency_pgvector_ms=latency_pgvector_ms,
    )


def _insert_divergent(
    *,
    intent="TEST_INTENT",
    cultures=None,
    chroma_id="chroma_x",
    pg_id="pg_x",
    classification="divergent",
):
    """Helper : insère une divergence (non-match) via `_persist_divergence`."""
    from app.services.corpus_facade import _persist_divergence

    _persist_divergence(
        intent=intent,
        cultures=cultures or ["CULTURE_RIZ"],
        conditions=[],
        chroma_id=chroma_id,
        pg_id=pg_id,
        chroma_score=None,
        pg_score=None,
        classification=classification,
        latency_chroma_ms=10,
        latency_pgvector_ms=20,
    )


# ─────────────────────────────────────────────────────────────────────────
# Classification helper (test unitaire de _classify_divergence)
# ─────────────────────────────────────────────────────────────────────────


class TestClassifyDivergence:
    """`_classify_divergence` couvre les 4 cas Phase D + 1 cas réservé Phase E."""

    def test_match_both_same_id(self):
        from app.services.corpus_facade import _classify_divergence
        assert _classify_divergence("id_1", "id_1") == "match"

    def test_match_both_none(self):
        from app.services.corpus_facade import _classify_divergence
        assert _classify_divergence(None, None) == "match"

    def test_absence_chroma(self):
        from app.services.corpus_facade import _classify_divergence
        assert _classify_divergence(None, "pg_1") == "absence_chroma"

    def test_absence_pgvector(self):
        from app.services.corpus_facade import _classify_divergence
        assert _classify_divergence("chroma_1", None) == "absence_pgvector"

    def test_divergent(self):
        from app.services.corpus_facade import _classify_divergence
        assert _classify_divergence("chroma_1", "pg_2") == "divergent"


# ─────────────────────────────────────────────────────────────────────────
# Endpoint structure + auth
# ─────────────────────────────────────────────────────────────────────────


class TestEndpointStructure:
    def test_endpoint_returns_200_empty_report(self, client, clean_divergences):
        resp = client.get("/admin/corpus-divergence-report")
        # Mode dev : API_SECRET_KEY pas configurée → 200 attendu sans header
        # (cf. app/security.py:42-43 `if not _API_SECRET_KEY: return`)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_queries"] == 0
        assert body["divergences_count"] == 0
        assert body["divergence_rate"] == 0.0
        assert body["by_classification"] == {
            "match": 0, "reorder": 0, "divergent": 0,
            "absence_chroma": 0, "absence_pgvector": 0,
        }
        assert body["top_10_divergences"] == []

    def test_days_param_validation(self, client):
        # ge=1 → 0 rejeté
        assert client.get("/admin/corpus-divergence-report?days=0").status_code == 422
        # le=365 → 500 rejeté
        assert client.get("/admin/corpus-divergence-report?days=500").status_code == 422
        # valide
        assert client.get("/admin/corpus-divergence-report?days=30").status_code == 200

    def test_403_without_api_key_when_key_configured(self):
        """FIX-8 : si `API_SECRET_KEY` est configurée dans `.env`, l'endpoint
        DOIT rejeter une requête sans header `X-API-Key` (403 Forbidden).

        Skip propre si en mode dev (clé absente) : le test ne s'applique pas.
        """
        from app.main import app
        from app.security import _API_SECRET_KEY

        if not _API_SECRET_KEY:
            pytest.skip("API_SECRET_KEY non configurée (mode dev permissif)")

        # TestClient sans header explicite — pas via la fixture `client`
        # qui injecte la clé.
        bare_client = TestClient(app)
        resp = bare_client.get("/admin/corpus-divergence-report")
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# Agrégats sur données réelles
# ─────────────────────────────────────────────────────────────────────────


class TestReportAggregates:
    def test_counts_and_rate_with_3_matches_2_divergent(
        self, client, clean_divergences
    ):
        # Insert 3 matches + 2 divergent → divergence_rate = 2/5 = 0.4
        for i in range(3):
            _insert_match(chroma_id=f"id_{i}", pg_id=f"id_{i}")
        for i in range(2):
            _insert_divergent(chroma_id=f"chroma_{i}", pg_id=f"pg_{i}")

        body = client.get("/admin/corpus-divergence-report").json()
        assert body["total_queries"] == 5
        assert body["divergences_count"] == 2
        assert abs(body["divergence_rate"] - 0.4) < 0.001
        assert body["by_classification"]["match"] == 3
        assert body["by_classification"]["divergent"] == 2
        assert len(body["top_10_divergences"]) == 2
        # FIX-4 : `conditions` doit être présent dans chaque DivergenceDetail
        for d in body["top_10_divergences"]:
            assert "conditions" in d and isinstance(d["conditions"], list)

    def test_absence_classifications_counted(self, client, clean_divergences):
        _insert_divergent(chroma_id=None, pg_id="pg_only", classification="absence_chroma")
        _insert_divergent(chroma_id="chroma_only", pg_id=None, classification="absence_pgvector")

        body = client.get("/admin/corpus-divergence-report").json()
        assert body["by_classification"]["absence_chroma"] == 1
        assert body["by_classification"]["absence_pgvector"] == 1
        assert body["divergences_count"] == 2  # absence_* != match

    def test_latency_p95_and_ratio(self, client, clean_divergences):
        # Insertions avec latences variées pour valider P95 + ratio
        for chroma_ms, pg_ms in [(10, 15), (20, 30), (30, 45), (40, 60), (100, 150)]:
            _insert_match(
                chroma_id="x", pg_id="x",
                latency_chroma_ms=chroma_ms, latency_pgvector_ms=pg_ms,
            )
        body = client.get("/admin/corpus-divergence-report").json()
        # P95 sur 5 valeurs ≈ valeur max
        assert body["latency_p95_chroma_ms"] is not None
        assert body["latency_p95_pgvector_ms"] is not None
        assert body["latency_ratio"] is not None
        # pgvector = 1.5x chroma sur cet échantillon
        assert 1.3 < body["latency_ratio"] < 1.7


# ─────────────────────────────────────────────────────────────────────────
# Persistance via _persist_divergence (bout en bout sans thread daemon)
# ─────────────────────────────────────────────────────────────────────────


class TestPersistDivergence:
    def test_persist_then_report(self, client, clean_divergences):
        from app.services.corpus_facade import _persist_divergence

        _persist_divergence(
            intent="CONSEIL_PRODUCTION",
            cultures=["CULTURE_RIZ"],
            conditions=["saison_pluie"],
            chroma_id="riz_001",
            pg_id="riz_002",
            chroma_score=0.85,
            pg_score=0.83,
            classification="divergent",
            latency_chroma_ms=15,
            latency_pgvector_ms=22,
        )

        body = client.get("/admin/corpus-divergence-report").json()
        assert body["total_queries"] == 1
        assert body["divergences_count"] == 1
        assert len(body["top_10_divergences"]) == 1
        top = body["top_10_divergences"][0]
        assert top["intent"] == "CONSEIL_PRODUCTION"
        assert top["cultures"] == ["CULTURE_RIZ"]
        # FIX-4 : conditions doit être exposé pour reproduire la query
        assert top["conditions"] == ["saison_pluie"]
        assert top["chroma_id"] == "riz_001"
        assert top["pgvector_id"] == "riz_002"
        assert top["classification"] == "divergent"
