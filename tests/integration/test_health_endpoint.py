"""
Tests d'intégration pour l'endpoint /health enrichi (ADR-0011 Phase 4).

Valide :
- /health retourne HTTP 200 avec la structure attendue
- Le bloc `models.registry.loaded_keys` reflète le contenu de ModelRegistry
- Le bloc `models.process.rss_mb` / `vms_mb` est numérique et > 0
- Le bloc `services` historique est préservé (rétrocompatibilité)

Note : ces tests utilisent TestClient + mocks pour ne pas charger les
vrais modèles ML.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Client de test FastAPI sans charger les modèles ML."""
    with patch("app.services.nlu.get_nlu_service", return_value=None), \
         patch("app.services.asr.nemo_provider.preload_nemo_model", return_value=None), \
         patch("app.services.translation.get_translation_service") as mock_ts, \
         patch("app.services.tts_bambara.get_tts_model", return_value=(None, None)), \
         patch("app.services.tts_dioula.get_tts_model_dioula", return_value=(None, None)), \
         patch("app.services.stt_whisper.get_whisper_model", return_value=None), \
         patch("app.services.corpus_service.initialiser_vdb"), \
         patch("app.services.audio_cleanup.start_cleanup_scheduler"), \
         patch("app.services.audio_cleanup.stop_cleanup_scheduler"):
        mock_svc = mock_ts.return_value
        mock_svc.preload_nllb.return_value = None
        mock_svc.get_stats.return_value = {"dictionnaire": {"total_mots": 0}}
        from app.main import app
        yield TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    """Vérifie le format et le contenu de /health (ADR-0011 Phase 4)."""

    def test_health_returns_200(self, client):
        """/health retourne HTTP 200 même sans modèle chargé."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        assert response.status_code == 200

    def test_health_top_level_keys(self, client):
        """/health retourne les clés top-level attendues."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        assert set(data.keys()) >= {"status", "app_name", "version", "services", "models"}

    def test_health_services_preserved(self, client):
        """Le bloc `services` historique est préservé (rétrocompatibilité)."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        services = data["services"]
        # Clés historiques attendues
        for key in ("deepseek", "weather", "tts_french", "tts_bambara",
                    "stt_whisper", "rag_knowledge"):
            assert key in services, f"Clé manquante dans services: {key}"

    def test_health_exposes_nemo_status(self, client):
        """/health expose la disponibilité, le modèle et son chargement NeMo."""
        expected = {
            "nemo_available": False,
            "model_path_exists": True,
            "model_loaded": False,
        }
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)), \
             patch("app.main.get_nemo_status",
                   return_value=expected):
            response = client.get("/health")
        assert response.json()["services"]["asr_nemo"] == expected

    def test_health_models_block_structure(self, client):
        """Le bloc `models` a la structure attendue."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        models = data["models"]
        assert "registry" in models
        assert "process" in models
        assert "loaded_keys" in models["registry"]
        assert "count" in models["registry"]
        assert "rss_mb" in models["process"]
        assert "vms_mb" in models["process"]

    def test_health_registry_loaded_keys_is_list(self, client):
        """`loaded_keys` est une liste de strings (potentiellement vide)."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        loaded = data["models"]["registry"]["loaded_keys"]
        assert isinstance(loaded, list)
        assert all(isinstance(k, str) for k in loaded)

    def test_health_registry_count_matches_loaded_keys_length(self, client):
        """`count` correspond toujours à la longueur de `loaded_keys`."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        registry_block = data["models"]["registry"]
        assert registry_block["count"] == len(registry_block["loaded_keys"])

    def test_health_process_rss_positive(self, client):
        """RSS du process Python est > 0 (process actif)."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        rss = data["models"]["process"]["rss_mb"]
        assert isinstance(rss, (int, float))
        assert rss > 0

    def test_health_process_vms_positive(self, client):
        """VMS du process Python est > 0."""
        with patch("app.main.check_deepseek_status",
                   AsyncMock(return_value=True)):
            response = client.get("/health")
        data = response.json()
        vms = data["models"]["process"]["vms_mb"]
        assert isinstance(vms, (int, float))
        assert vms > 0

    def test_health_registry_reflects_loaded_models(self, client):
        """Si le registry contient une clé, /health la liste."""
        from app.services.model_registry import registry
        # Charger un fake modèle dans le registry
        fake_key = "test_fake_model_for_health_endpoint"
        registry.get(fake_key, loader=lambda: object())
        try:
            with patch("app.main.check_deepseek_status",
                       AsyncMock(return_value=True)):
                response = client.get("/health")
            data = response.json()
            assert fake_key in data["models"]["registry"]["loaded_keys"]
            assert data["models"]["registry"]["count"] >= 1
        finally:
            # Cleanup : retirer le fake modèle pour ne pas polluer les autres tests
            registry.unload(fake_key)
