"""Tests unitaires — `app/services/corpus_facade.py` (Sprint F Phase C, issue #183).

Couvre 2 cas symetriques au test integration existant mais en mode mock pur
(pas de Postgres requis) :
    - mode `dual` : `ajouter_reponse_validee` ecrit Chroma + lance thread pgvector
    - `_compare_chercher_in_background` : exception R5 absorbee sans propager

Reference : `tests/integration/test_corpus_facade.py` couvre les memes scenarios
mais avec vraie BDD (skipped sans Postgres). Ces tests unitaires garantissent
la couverture en CI/local sans dependance externe.
"""
from __future__ import annotations

import threading
from unittest.mock import patch

from app.services import corpus_facade


class TestAjouterReponseValideeDualMode:
    """Issue #183 : mode dual ecrit Chroma + pgvector en background."""

    def test_returns_chroma_result_and_calls_pgvector_in_background(self):
        """Mode dual : retour Chroma autoritatif + thread daemon ecrit pgvector.

        Symetrique au test `test_mode_dual_returns_chroma_and_calls_pgvector_in_background`
        de l'integration (qui couvre la LECTURE). Ici on couvre l'ECRITURE.
        """
        pg_called = threading.Event()

        def _track_pg(*args, **kwargs):
            pg_called.set()
            return True

        with patch("app.services.corpus_facade._mode", return_value="dual"), \
             patch("app.services.vdb_service.ajouter_reponse_validee", return_value=True) as mock_vdb, \
             patch("app.services.corpus_service.ajouter_reponse_validee", side_effect=_track_pg) as mock_pg:
            result = corpus_facade.ajouter_reponse_validee(
                intent="CONSEIL_PRODUCTION",
                cultures=["CULTURE_RIZ"],
                reponse_bambara="aw ye malo sɛnɛ",
                reponse_fr="plantez le riz",
                score_validation=0.8,
                conditions=["saison_pluie"],
                tags=["urgence"],
            )

        # Retour Chroma autoritatif
        assert result is True
        mock_vdb.assert_called_once()

        # Thread daemon : attendre jusqu'a 2s qu'il appelle corpus_service
        assert pg_called.wait(timeout=2.0), (
            "Thread daemon n'a pas appele corpus_service.ajouter_reponse_validee"
        )
        mock_pg.assert_called_once()

    def test_pgvector_failure_does_not_propagate_in_dual_mode(self):
        """Mode dual : si pgvector leve, Chroma reste autoritatif (best-effort)."""
        pg_called = threading.Event()

        def _failing_pg(*args, **kwargs):
            pg_called.set()
            raise RuntimeError("pgvector unreachable")

        with patch("app.services.corpus_facade._mode", return_value="dual"), \
             patch("app.services.vdb_service.ajouter_reponse_validee", return_value=True), \
             patch("app.services.corpus_service.ajouter_reponse_validee", side_effect=_failing_pg):
            # Ne doit pas lever malgre l'erreur pgvector dans le thread
            result = corpus_facade.ajouter_reponse_validee(
                intent="X",
                cultures=["CULTURE_RIZ"],
                reponse_bambara="x",
                reponse_fr="x",
                score_validation=0.5,
            )

        assert result is True  # Chroma OK
        assert pg_called.wait(timeout=2.0), "Thread daemon n'a pas tente l'ecriture pgvector"
        # Aucune exception ne remonte au caller -> defense en profondeur OK


class TestCompareChercherInBackground:
    """Issue #183 : exceptions du thread daemon sont absorbees (R5)."""

    def test_swallows_corpus_service_exception(self):
        """R5 : si corpus_service.chercher_reponse_ivr leve, le thread daemon ne propage pas."""
        with patch(
            "app.services.corpus_service.chercher_reponse_ivr",
            side_effect=RuntimeError("pgvector boom"),
        ):
            # Appel direct (pas via thread) — doit retourner None sans lever
            corpus_facade._compare_chercher_in_background(
                intent="CONSEIL_PRODUCTION",
                cultures=["CULTURE_RIZ"],
                conditions=[],
                chroma_result={"id": "chroma_x", "score_validation": 0.8},
                latency_chroma_ms=10,
            )
        # Si on arrive ici sans exception : R5 OK

    def test_swallows_persist_divergence_exception(self):
        """R5 : si _persist_divergence leve, l'exception est absorbee (BD divergences down)."""
        with patch(
            "app.services.corpus_service.chercher_reponse_ivr",
            return_value={"id": "pg_x", "score_validation": 0.7},
        ), patch(
            "app.services.corpus_facade._persist_divergence",
            side_effect=RuntimeError("divergences table down"),
        ):
            corpus_facade._compare_chercher_in_background(
                intent="X",
                cultures=["CULTURE_RIZ"],
                conditions=[],
                chroma_result={"id": "chroma_x", "score_validation": 0.8},
                latency_chroma_ms=10,
            )
        # Pas d'exception propagee -> R5 OK meme quand persistance casse
