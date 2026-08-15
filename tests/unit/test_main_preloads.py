"""
Tests unitaires des préchargements de démarrage (main._preload_* / _run_preloads).

La décomposition de la god-function lifespan rend chaque préchargement testable
sans démarrer le serveur : on vérifie le contrat de retour (nom du service en
cas d'indisponibilité, None sinon) et l'agrégation ordonnée par _run_preloads.
"""
from unittest.mock import patch

import app.main as main


class TestRunPreloads:
    def test_agrege_les_issues_dans_l_ordre(self):
        # Chaque preloader renvoie un nom (ou None) ; _run_preloads collecte les non-None.
        fakes = (
            lambda: "NLU",
            lambda: None,
            lambda: "TranslationService",
            lambda: None,
            lambda: None,
            lambda: "BD vectorielle IVR",
            lambda: None,
        )
        with patch.object(main, "_PRELOADERS", fakes):
            assert main._run_preloads() == ["NLU", "TranslationService", "BD vectorielle IVR"]

    def test_aucune_issue_si_tout_ok(self):
        with patch.object(main, "_PRELOADERS", (lambda: None, lambda: None)):
            assert main._run_preloads() == []


class TestPreloadNlu:
    def test_retourne_nom_si_service_desactive(self):
        with patch("app.services.nlu.get_nlu_service", return_value=None):
            assert main._preload_nlu() == "NLU"

    def test_retourne_nom_si_exception(self):
        with patch("app.services.nlu.get_nlu_service", side_effect=RuntimeError("boom")):
            assert main._preload_nlu() == "NLU"

    def test_retourne_none_si_ok(self):
        class _FakeNlu:
            def get_stats(self):
                return {"total_concepts": 3, "total_keywords": 10}

        with patch("app.services.nlu.get_nlu_service", return_value=_FakeNlu()):
            assert main._preload_nlu() is None


class TestPreloadTtsFlags:
    def test_bambara_desactive_retourne_none(self, monkeypatch):
        monkeypatch.setattr(main.settings, "enable_mms_bam", False)
        assert main._preload_tts_bambara() is None

    def test_bambara_lazy_retourne_none(self, monkeypatch):
        monkeypatch.setattr(main.settings, "enable_mms_bam", True)
        monkeypatch.setattr(main.settings, "preload_tts_bambara", False)
        assert main._preload_tts_bambara() is None

    def test_dioula_desactive_retourne_none(self, monkeypatch):
        monkeypatch.setattr(main.settings, "enable_mms_dyu", False)
        assert main._preload_tts_dioula() is None
