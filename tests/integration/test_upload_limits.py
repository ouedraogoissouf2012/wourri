"""
Tests d'intégration pour les limites d'upload (issue #47).

Valide :
- Un fichier > 10 MB retourne HTTP 413 sur /api/asr/transcribe
- Un fichier > 10 MB retourne HTTP 413 sur /api/asr/transcribe-and-translate
- Un fichier > 10 MB retourne HTTP 413 sur /api/stt/transcribe
- Un fichier vide retourne HTTP 400
- Un fichier de taille normale (< 10 MB) passe la validation de taille

Note : ces tests utilisent TestClient (pas de serveur réel).
Les modèles ML ne sont PAS chargés — on teste uniquement la validation d'entrée.
"""
import io
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Client de test FastAPI sans charger les modèles ML.

    Mocker les modules sources (pas app.main) car les imports sont locaux.
    """
    # `_API_SECRET_KEY` est lu depuis .env au moment de l'import de app.security.
    # Si la clé existe sur disque (dev local), require_api_key retourne 403
    # avant la validation de taille (413). On patch à None pour reproduire le
    # mode dev sans auth attendu par ces tests (Sprint B issue #146).
    with patch("app.security._API_SECRET_KEY", None), \
         patch("app.services.nlu.get_nlu_service", return_value=None), \
         patch("app.services.asr_soloni_nemo.get_nemo_model", return_value=None), \
         patch("app.services.translation.get_translation_service") as mock_ts, \
         patch("app.services.tts_bambara.get_tts_model", return_value=(None, None)), \
         patch("app.services.tts_dioula.get_tts_model_dioula", return_value=(None, None)), \
         patch("app.services.stt_whisper.get_whisper_model", return_value=None), \
         patch("app.services.vdb_service.initialiser_vdb"), \
         patch("app.services.audio_cleanup.start_cleanup_scheduler"), \
         patch("app.services.audio_cleanup.stop_cleanup_scheduler"):
        # TranslationService mock doit avoir preload_nllb et get_stats
        mock_svc = mock_ts.return_value
        mock_svc.preload_nllb.return_value = None
        mock_svc.get_stats.return_value = {"dictionnaire": {"total_mots": 0}}
        from app.main import app
        yield TestClient(app, raise_server_exceptions=False)


class TestUploadLimits:
    """Vérifie que les endpoints rejettent les fichiers > 10 MB."""

    @staticmethod
    def _make_audio_bytes(size_mb: float) -> bytes:
        """Génère des bytes factices de la taille demandée."""
        return b"\x00" * int(size_mb * 1024 * 1024)

    def test_asr_transcribe_rejects_oversized(self, client):
        """POST /api/asr/transcribe rejette un fichier > 10 MB."""
        big_audio = self._make_audio_bytes(11)
        response = client.post(
            "/api/asr/transcribe",
            files={"audio": ("big.ogg", io.BytesIO(big_audio), "audio/ogg")},
            data={"language": "bam"},
        )
        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"]

    def test_asr_translate_rejects_oversized(self, client):
        """POST /api/asr/transcribe-and-translate rejette un fichier > 10 MB."""
        big_audio = self._make_audio_bytes(11)
        response = client.post(
            "/api/asr/transcribe-and-translate",
            files={"audio": ("big.ogg", io.BytesIO(big_audio), "audio/ogg")},
            data={"language": "bam"},
        )
        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"]

    def test_stt_transcribe_rejects_oversized(self, client):
        """POST /api/stt/transcribe rejette un fichier > 10 MB."""
        big_audio = self._make_audio_bytes(11)
        response = client.post(
            "/api/stt/transcribe",
            files={"audio": ("big.wav", io.BytesIO(big_audio), "audio/wav")},
            data={"language": "fr"},
        )
        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"]

    def test_asr_transcribe_rejects_empty(self, client):
        """POST /api/asr/transcribe rejette un fichier vide."""
        response = client.post(
            "/api/asr/transcribe",
            files={"audio": ("empty.ogg", io.BytesIO(b""), "audio/ogg")},
            data={"language": "bam"},
        )
        assert response.status_code == 400
        assert "vide" in response.json()["detail"].lower()

    def test_asr_transcribe_accepts_normal_size(self, client):
        """POST /api/asr/transcribe accepte un fichier de taille normale.

        Note: le fichier sera rejeté plus loin (format invalide) mais
        la validation de taille doit passer (pas de 413).
        """
        normal_audio = self._make_audio_bytes(0.05)  # 50 KB
        response = client.post(
            "/api/asr/transcribe",
            files={"audio": ("test.ogg", io.BytesIO(normal_audio), "audio/ogg")},
            data={"language": "bam"},
        )
        # Ne doit PAS être 413 — peut être 500 (pas de modèle) mais pas 413
        assert response.status_code != 413
