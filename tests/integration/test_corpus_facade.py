"""Tests d'intégration — `app/services/corpus_facade.py` (Sprint F Phase C).

Vérifie :
- mode `chroma` (DÉFAUT) délègue 100% à vdb_service — zéro changement
- mode `pgvector` délègue à corpus_service
- mode `dual` retourne le résultat Chroma + lance comparaison background
- **50 queries** sur le corpus retournent le **même id** chroma vs pgvector
  (critère ADR-0008 §Phase C #5)

Pré-requis : container Postgres dev up + corpus importé (Phase B).
Skip propre via `pytestmark` si Postgres absent.

Référence : ADR-0008 §Phase C.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.url_resolver import resolve_postgres_url
from tests.integration._helpers import postgres_reachable

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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


def _chroma_importable() -> bool:
    """chromadb 0.5.0 (legacy) utilise `np.float_`, supprimé en NumPy 2.0.

    Sur un environnement numpy>=2 (réinstall 2026-07-21), l'import chromadb
    échoue → le backend legacy est indisponible. La prod tourne en mode
    `pgvector` (ADR-0008, dépréciation chroma planifiée Phase E) : les tests
    qui comparent les DEUX backends sont skippés avec raison explicite,
    ceux qui mockent vdb_service restent verts.
    """
    try:
        import chromadb  # noqa: F401
        return True
    except Exception:
        return False


_CHROMA_OK = _chroma_importable()


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _set_mode(monkeypatch, mode: str):
    """Force `corpus_storage_mode` via monkeypatch des settings."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "corpus_storage_mode", mode)


@pytest.fixture(scope="module")
def corpus_sample() -> list[dict]:
    """Charge un sample d'entrées corpus (50 max) pour les tests dual."""
    corpus_path = _PROJECT_ROOT / "dictionnaires" / "corpus_ivr.json"
    with open(corpus_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("entries", [])[:50]


# ─────────────────────────────────────────────────────────────────────────
# Mode routing
# ─────────────────────────────────────────────────────────────────────────


class TestModeRouting:
    """Vérifie que la façade route correctement selon `corpus_storage_mode`."""

    def test_mode_chroma_calls_vdb_service_only(self, monkeypatch):
        from app.services import corpus_facade

        _set_mode(monkeypatch, "chroma")

        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb, \
             patch("app.services.corpus_service.chercher_reponse_ivr") as mock_pg:
            mock_vdb.return_value = {"id": "chroma_id", "reponse_bambara": "x"}
            mock_pg.return_value = {"id": "pg_id", "reponse_bambara": "y"}

            result = corpus_facade.chercher_reponse_ivr(
                "CONSEIL_PRODUCTION", ["CULTURE_RIZ"]
            )

        assert result == {"id": "chroma_id", "reponse_bambara": "x"}
        mock_vdb.assert_called_once()
        mock_pg.assert_not_called()

    def test_mode_pgvector_calls_corpus_service_only(self, monkeypatch):
        from app.services import corpus_facade

        _set_mode(monkeypatch, "pgvector")

        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb, \
             patch("app.services.corpus_service.chercher_reponse_ivr") as mock_pg:
            mock_vdb.return_value = {"id": "chroma_id"}
            mock_pg.return_value = {"id": "pg_id"}

            result = corpus_facade.chercher_reponse_ivr(
                "CONSEIL_PRODUCTION", ["CULTURE_RIZ"]
            )

        assert result == {"id": "pg_id"}
        mock_pg.assert_called_once()
        mock_vdb.assert_not_called()

    def test_mode_dual_returns_chroma_and_calls_pgvector_in_background(self, monkeypatch):
        import threading
        from app.services import corpus_facade

        _set_mode(monkeypatch, "dual")
        pg_called = threading.Event()

        def fake_pg(*args, **kwargs):
            pg_called.set()
            return {"id": "pg_id"}

        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb, \
             patch("app.services.corpus_service.chercher_reponse_ivr", side_effect=fake_pg):
            mock_vdb.return_value = {"id": "chroma_id", "reponse_bambara": "x"}

            result = corpus_facade.chercher_reponse_ivr(
                "CONSEIL_PRODUCTION", ["CULTURE_RIZ"]
            )

        # Chroma est autoritatif → retourné immédiatement
        assert result == {"id": "chroma_id", "reponse_bambara": "x"}
        # Le background thread doit avoir appelé pgvector (laisser 2 s max)
        assert pg_called.wait(timeout=2.0), "thread daemon pgvector pas exécuté"


# ─────────────────────────────────────────────────────────────────────────
# Cohérence sémantique chroma ↔ pgvector (critère ADR §Phase C #5)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not _CHROMA_OK,
    reason=(
        "chromadb non importable (numpy>=2 a retiré np.float_, chromadb 0.5.0 "
        "legacy incompatible). Comparaison chroma↔pgvector impossible ; le "
        "backend prod (pgvector) reste testé par le reste de la suite. "
        "Dépréciation chroma : ADR-0008 Phase E."
    ),
)
class TestChromaVsPgvectorConsistency:
    """Critère ADR §Phase C #5 : 50+ queries retournent le même `id`.

    Tolérance : ≥ 90 % de match (Chroma HNSW et pgvector ivfflat peuvent
    diverger sur des ties à distance cosine équivalente).
    """

    def test_50_queries_match_at_least_90_percent(self, corpus_sample):
        from app.services import corpus_service, vdb_service

        matches = 0
        total = 0
        divergences = []

        for entry in corpus_sample:
            intent = entry["intent"]
            cultures = entry.get("cultures") or ["*"]
            conditions = entry.get("conditions") or []

            chroma_result = vdb_service.chercher_reponse_ivr(intent, cultures, conditions)
            pg_result = corpus_service.chercher_reponse_ivr(intent, cultures, conditions)

            chroma_id = chroma_result.get("id") if chroma_result else None
            pg_id = pg_result.get("id") if pg_result else None

            total += 1
            if chroma_id == pg_id:
                matches += 1
            else:
                divergences.append(
                    f"intent={intent} cultures={cultures} chroma={chroma_id} pg={pg_id}"
                )

        rate = matches / total if total else 0.0
        # Log divergences pour observabilité (utile en cas d'échec)
        if divergences:
            print(f"\n[DIVERGENCES {len(divergences)}/{total}]")
            for d in divergences[:10]:
                print(" ", d)

        assert total > 0, "corpus sample vide"
        assert rate >= 0.90, (
            f"Cohérence chroma↔pgvector trop basse : {rate:.1%} ({matches}/{total}). "
            f"Premières divergences : {divergences[:5]}"
        )
