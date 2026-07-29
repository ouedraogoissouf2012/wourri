"""
Tests d'intégration pour la stratégie de préchargement (ADR-0011 Phase 5).

Sécurise les acquis de Phase 3 (lazy-load Whisper et NLLB) en vérifiant que :

1. Le `lifespan` de l'app **N'APPELLE PAS** `get_whisper_model()` au démarrage.
2. Le `lifespan` **N'APPELLE PAS** `service.preload_nllb()` au démarrage.
3. Le `lifespan` **APPELLE BIEN** les loaders eager (NeMo, TTS Bambara/Dioula,
   dictionnaire de traduction).

Si un futur dev re-précharge accidentellement Whisper ou NLLB dans `main.py`,
ces tests échoueront immédiatement et signaleront la régression.

Note : on utilise `unittest.mock.patch` comme spy. Les loaders sont mockés
pour éviter de charger les vrais modèles (overhead inutile en test), mais
on vérifie ensuite si le mock a été appelé ou pas.
"""
import logging
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def lifespan_spies():
    """Démarre l'app avec des spies sur tous les loaders.

    Yield un dict de mocks qu'on peut interroger après le démarrage pour
    vérifier qui a été appelé et qui ne l'a pas été.
    """
    # Patches sur les modules sources (pas sur app.main car les imports
    # sont locaux dans le lifespan).
    with patch("app.services.stt_whisper.get_whisper_model",
               return_value=None) as spy_whisper, \
         patch("app.services.asr_soloni_nemo.get_nemo_model",
               return_value=object()) as spy_nemo, \
         patch("app.services.tts_bambara.get_tts_model",
               return_value=(object(), object())) as spy_tts_bam, \
         patch("app.services.tts_dioula.get_tts_model_dioula",
               return_value=(object(), object())) as spy_tts_dyu, \
         patch("app.services.translation.get_translation_service") as mock_ts, \
         patch("app.services.nlu.get_nlu_service") as mock_nlu, \
         patch("app.services.corpus_facade.initialiser_vdb"), \
         patch("app.services.audio_cleanup.start_cleanup_scheduler"), \
         patch("app.services.audio_cleanup.stop_cleanup_scheduler"), \
         patch("app.core.logging_config.setup_logging"):
        # mock_ts est appelé pour récupérer le service. On configure le mock
        # pour qu'il ait un attribut preload_nllb (que /lifespan ne doit
        # PAS appeler).
        mock_svc = MagicMock()
        mock_svc.preload_nllb = MagicMock(return_value=None)
        mock_svc.get_stats.return_value = {"dictionnaire": {"total_mots": 0}}
        mock_ts.return_value = mock_svc
        mock_nlu.return_value.get_stats.return_value = {
            "total_concepts": 0,
            "total_keywords": 0,
        }

        from app.main import app
        # Le context manager `with TestClient(app)` déclenche le lifespan
        # startup à l'entrée et shutdown à la sortie.
        with TestClient(app) as client:
            yield {
                "client": client,
                "spy_whisper": spy_whisper,
                "spy_nemo": spy_nemo,
                "spy_tts_bambara": spy_tts_bam,
                "spy_tts_dioula": spy_tts_dyu,
                "mock_translation_service": mock_ts,
                "spy_preload_nllb": mock_svc.preload_nllb,
            }


class TestLazyLoadingPolicy:
    """Vérifie que le lifespan respecte la stratégie ADR-0011 Phase 3."""

    def test_lifespan_does_not_call_get_whisper_model(self, lifespan_spies):
        """Whisper doit être lazy : le lifespan ne le charge pas.

        Régression interdite : un commit qui re-précharge Whisper dans
        main.py ferait échouer ce test.
        """
        spy = lifespan_spies["spy_whisper"]
        spy.assert_not_called()

    def test_lifespan_does_not_call_preload_nllb(self, lifespan_spies):
        """NLLB doit être lazy : le lifespan ne le charge pas.

        Régression interdite : un commit qui rajoute service.preload_nllb()
        dans main.py ferait échouer ce test.
        """
        spy = lifespan_spies["spy_preload_nllb"]
        spy.assert_not_called()

    def test_lifespan_calls_get_nemo_model_eager(self, lifespan_spies):
        """NeMo doit rester eager (cas d'usage principal = vocaux dioula)."""
        spy = lifespan_spies["spy_nemo"]
        spy.assert_called()

    def test_lifespan_calls_get_tts_bambara_eager(self, lifespan_spies):
        """TTS Bambara doit rester eager (réponses audio en mode dioula/both)."""
        spy = lifespan_spies["spy_tts_bambara"]
        spy.assert_called()

    def test_lifespan_calls_get_tts_dioula_eager(self, lifespan_spies):
        """TTS Dioula doit rester eager (voix ivoirienne mode dioula)."""
        spy = lifespan_spies["spy_tts_dioula"]
        spy.assert_called()

    def test_lifespan_calls_get_translation_service_for_dict(self, lifespan_spies):
        """Le dictionnaire doit rester eager (couvre 90% des traductions)."""
        mock_ts = lifespan_spies["mock_translation_service"]
        # Le lifespan appelle get_translation_service() puis service.get_stats()
        mock_ts.assert_called()
        mock_ts.return_value.get_stats.assert_called()


class TestLazyLoadingPolicyDetails:
    """Vérifications fines sur les counts d'appels."""

    def test_whisper_zero_calls_during_lifespan(self, lifespan_spies):
        """Le compteur d'appels Whisper doit être strictement à 0."""
        spy = lifespan_spies["spy_whisper"]
        assert spy.call_count == 0, (
            f"get_whisper_model a été appelé {spy.call_count} fois pendant "
            "le lifespan. Whisper doit rester lazy (ADR-0011 Phase 3)."
        )

    def test_preload_nllb_zero_calls_during_lifespan(self, lifespan_spies):
        """Le compteur d'appels preload_nllb doit être strictement à 0."""
        spy = lifespan_spies["spy_preload_nllb"]
        assert spy.call_count == 0, (
            f"service.preload_nllb a été appelé {spy.call_count} fois pendant "
            "le lifespan. NLLB doit rester lazy (ADR-0011 Phase 3)."
        )

    def test_nemo_called_once_during_lifespan(self, lifespan_spies):
        """NeMo doit être chargé exactement une fois (pas de double appel)."""
        spy = lifespan_spies["spy_nemo"]
        assert spy.call_count == 1, (
            f"get_nemo_model a été appelé {spy.call_count} fois (attendu : 1)."
        )


def test_lifespan_reports_nemo_unavailable_without_false_success(caplog):
    """Un loader NeMo qui renvoie None ne doit jamais être annoncé comme OK."""
    with patch("app.services.asr_soloni_nemo.get_nemo_model",
               return_value=None), \
         patch("app.services.nlu.get_nlu_service") as mock_nlu, \
         patch("app.services.translation.get_translation_service") as mock_ts, \
         patch("app.services.tts_bambara.get_tts_model",
               return_value=(object(), object())), \
         patch("app.services.tts_dioula.get_tts_model_dioula",
               return_value=(object(), object())), \
         patch("app.services.corpus_facade.initialiser_vdb"), \
         patch("app.services.audio_cleanup.start_cleanup_scheduler"), \
         patch("app.services.audio_cleanup.stop_cleanup_scheduler"):
        mock_nlu.return_value.get_stats.return_value = {
            "total_concepts": 0,
            "total_keywords": 0,
        }
        mock_ts.return_value.get_stats.return_value = {
            "dictionnaire": {"total_mots": 0},
        }

        from app.main import app
        with caplog.at_level(logging.INFO):
            with TestClient(app):
                pass

    assert "[PRELOAD] ASR NeMo Soloni: INDISPONIBLE" in caplog.text
    assert "[PRELOAD] ASR NeMo Soloni: OK" not in caplog.text
    assert "service(s) indisponible(s): ASR NeMo Soloni" in caplog.text


def test_lifespan_minimal_dioula_profile_loads_only_required_models():
    """Le profil 4 GB garde le parcours Dioula et évite les modèles inutiles.

    T6 issue #42 est alignée sur l'ADR-0011 : NLLB reste lazy, il ne doit pas
    être réintroduit au démarrage. Le profil minimal précharge donc NeMo et
    MMS-Dioula, désactive MMS-Bambara et ne charge jamais Whisper au boot.
    """
    with patch(
        "app.services.stt_whisper.get_whisper_model", return_value=None
    ) as spy_whisper, patch(
        "app.services.asr_soloni_nemo.get_nemo_model", return_value=object()
    ) as spy_nemo, patch(
        "app.services.tts_bambara.get_tts_model",
        return_value=(object(), object()),
    ) as spy_tts_bam, patch(
        "app.services.tts_dioula.get_tts_model_dioula",
        return_value=(object(), object()),
    ) as spy_tts_dyu, patch(
        "app.services.translation.get_translation_service"
    ) as mock_ts, patch(
        "app.services.nlu.get_nlu_service"
    ) as mock_nlu, patch(
        "app.services.corpus_facade.initialiser_vdb"
    ), patch(
        "app.services.audio_cleanup.start_cleanup_scheduler"
    ), patch(
        "app.services.audio_cleanup.stop_cleanup_scheduler"
    ), patch(
        "app.core.logging_config.setup_logging"
    ):
        mock_svc = MagicMock()
        mock_svc.preload_nllb = MagicMock(return_value=None)
        mock_svc.get_stats.return_value = {
            "dictionnaire": {"total_mots": 0},
        }
        mock_ts.return_value = mock_svc
        mock_nlu.return_value.get_stats.return_value = {
            "total_concepts": 0,
            "total_keywords": 0,
        }

        from app import main as main_module

        minimal_settings = SimpleNamespace(
            app_name="WOURI",
            app_version="test",
            debug=False,
            enable_whisper=False,
            enable_mms_bam=False,
            preload_tts_bambara=False,
            enable_mms_dyu=True,
            preload_tts_dioula=True,
            is_production=False,
        )

        with patch.object(main_module, "settings", minimal_settings):
            with TestClient(main_module.app):
                pass

    spy_nemo.assert_called_once()
    spy_tts_dyu.assert_called_once()
    spy_tts_bam.assert_not_called()
    spy_whisper.assert_not_called()
    mock_svc.preload_nllb.assert_not_called()
