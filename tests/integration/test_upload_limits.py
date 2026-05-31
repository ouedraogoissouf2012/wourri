"""
Tests d'intégration pour les limites d'upload audio (10 MB).

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
    # mode dev sans auth attendu par ces tests.
    # `WHISPER_AVAILABLE` doit aussi être forcé à True : `stt.py` check cette
    # variable AVANT la lecture du body et renvoie 503 si False. Sur une
    # machine sans `faster-whisper` installé, le 503 court-circuiterait la
    # validation 413 testée ici.
    with patch("app.security._API_SECRET_KEY", None), \
         patch("app.routers.stt.stt_whisper.WHISPER_AVAILABLE", True), \
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

        Fix #150 : remplace l'assertion `!= 413` (negation faible qui passait
        meme avec 422/4xx) par un set positif des statuts attendus.

        Statuts attendus :
          - 200 : success (avec modele ML reel)
          - 500 : modele ML mocke None → erreur serveur attendue dans ce test
          - 503 : service unavailable (modele non disponible)
        Exclu explicitement : 413 (taille), 4xx (auth/format/validation).
        """
        normal_audio = self._make_audio_bytes(0.05)  # 50 KB
        response = client.post(
            "/api/asr/transcribe",
            files={"audio": ("test.ogg", io.BytesIO(normal_audio), "audio/ogg")},
            data={"language": "bam"},
        )
        assert response.status_code in {200, 500, 503}, (
            f"unexpected status {response.status_code}: {response.text[:200]}"
        )


class TestUploadLimitsWithAuth:
    """Verrouille l'ordre Depends : auth → puis validation taille.

    Fix #149 : les tests `TestUploadLimits` desactivent l'auth via
    `patch(_API_SECRET_KEY, None)`. Ils ne couvrent que le mode dev.
    Ici on active l'auth ET on envoie un header X-API-Key valide pour
    prouver que la validation taille (413) intervient APRES l'auth.
    Si un refactor inverse l'ordre des Depends, ces tests echouent.
    """

    AUTH_KEY = "secret-test-149"

    @pytest.fixture
    def client_with_auth(self):
        """Client identique au fixture `client` mais avec auth activee."""
        with patch("app.security._API_SECRET_KEY", self.AUTH_KEY), \
             patch("app.routers.stt.stt_whisper.WHISPER_AVAILABLE", True), \
             patch("app.services.nlu.get_nlu_service", return_value=None), \
             patch("app.services.asr_soloni_nemo.get_nemo_model", return_value=None), \
             patch("app.services.translation.get_translation_service") as mock_ts, \
             patch("app.services.tts_bambara.get_tts_model", return_value=(None, None)), \
             patch("app.services.tts_dioula.get_tts_model_dioula", return_value=(None, None)), \
             patch("app.services.stt_whisper.get_whisper_model", return_value=None), \
             patch("app.services.vdb_service.initialiser_vdb"), \
             patch("app.services.audio_cleanup.start_cleanup_scheduler"), \
             patch("app.services.audio_cleanup.stop_cleanup_scheduler"):
            mock_svc = mock_ts.return_value
            mock_svc.preload_nllb.return_value = None
            mock_svc.get_stats.return_value = {"dictionnaire": {"total_mots": 0}}
            from app.main import app
            yield TestClient(app, raise_server_exceptions=False)

    @staticmethod
    def _big_audio() -> bytes:
        return b"\x00" * (11 * 1024 * 1024)

    def test_asr_transcribe_rejects_oversized_with_auth(self, client_with_auth):
        """Auth valide + fichier > 10 MB → 413 (auth passe, taille rejette)."""
        response = client_with_auth.post(
            "/api/asr/transcribe",
            files={"audio": ("big.ogg", io.BytesIO(self._big_audio()), "audio/ogg")},
            data={"language": "bam"},
            headers={"X-API-Key": self.AUTH_KEY},
        )
        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"]

    def test_asr_translate_rejects_oversized_with_auth(self, client_with_auth):
        """Auth valide + fichier > 10 MB → 413 sur /transcribe-and-translate."""
        response = client_with_auth.post(
            "/api/asr/transcribe-and-translate",
            files={"audio": ("big.ogg", io.BytesIO(self._big_audio()), "audio/ogg")},
            data={"language": "bam"},
            headers={"X-API-Key": self.AUTH_KEY},
        )
        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"]

    def test_stt_transcribe_rejects_oversized_with_auth(self, client_with_auth):
        """Auth valide + fichier > 10 MB → 413 sur /stt/transcribe."""
        response = client_with_auth.post(
            "/api/stt/transcribe",
            files={"audio": ("big.wav", io.BytesIO(self._big_audio()), "audio/wav")},
            data={"language": "fr"},
            headers={"X-API-Key": self.AUTH_KEY},
        )
        assert response.status_code == 413
        assert "10 MB" in response.json()["detail"]

    def test_asr_transcribe_without_auth_returns_403(self, client_with_auth):
        """Sentinelle : sans header X-API-Key → 403 (verrouille l'auth active)."""
        response = client_with_auth.post(
            "/api/asr/transcribe",
            files={"audio": ("big.ogg", io.BytesIO(self._big_audio()), "audio/ogg")},
            data={"language": "bam"},
        )
        assert response.status_code == 403
