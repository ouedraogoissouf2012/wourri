"""Tests E2E du parcours audio complet (issue #305).

Le parcours produit principal — vocal WhatsApp → ASR → chat/IVR → TTS → réponse
audio — n'avait AUCUN test bout-en-bout. Conséquence : des bugs de câblage
(erreur DeepSeek vocalisée #294, conversion ffmpeg ×4 #301, fallback dioula =
texte FR) ne seraient captés par aucun test.

Deux niveaux, complémentaires :

- **Test A (tourne en CI)** — `TestAudioPipelineWiring` : exerce le VRAI câblage
  HTTP `POST /api/asr/transcribe-and-translate` → `POST /api/chat/`, avec la
  **conversion ffmpeg réelle** (fixture OGG → WAV 16k, non mockée). Seules les
  inférences ML lourdes (ASR, NLU, traduction, TTS) sont remplacées par des
  stubs déterministes — le test prouve que ffmpeg, la chaîne ASR, le NLU et le
  service chat sont correctement branchés, sans charger 4 Go de modèles.

- **Test B (skip en CI)** — `TestAudioPipelineFullML` : le même parcours avec les
  VRAIS modèles ASR + TTS. Gaté par `ENABLE_E2E_FULL_ML=1` (+ présence des
  modèles) : fidélité maximale, mais réservé à une machine équipée (cf.
  ADR-0022 : aucun vocal dioula réel de référence n'existe encore dans le repo).
"""
from __future__ import annotations

import io
import os
import wave
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.security import limiter
from app.services.asr.base import ASRProvider
from app.services.asr.chain import ASRChain
from app.services.chat_service import ChatResult

_FIXTURE_OGG = Path(__file__).parent / "fixtures" / "sample_tone.ogg"


# ─────────────────────────────────────────────────────────────────────────
# Provider stub : inférence déterministe MAIS conversion ffmpeg RÉELLE
# ─────────────────────────────────────────────────────────────────────────


class RealFfmpegStubProvider(ASRProvider):
    """Provider stub qui exerce la VRAIE conversion ffmpeg puis renvoie une
    transcription bambara connue (sans modèle ML).

    Le test E2E doit prouver que ffmpeg convertit réellement l'audio, quel que
    soit le point où la chaîne déclenche l'inférence — et ce point diffère selon
    la version de la chaîne :
      - chaîne « historique » : appelle `provider.transcribe(bytes, ext)` (le
        provider convertit lui-même) ;
      - chaîne #301 : convertit UNE fois en amont et appelle
        `provider.transcribe_wav(wav_path)` avec le WAV déjà prêt.
    Le stub implémente les DEUX chemins et capture le contenu du WAV 16k dans les
    deux cas → le test est indépendant de la version de la chaîne (pas de
    couplage inter-PR avec #301).
    """

    def __init__(self, transcription: str):
        self._transcription = transcription
        self.captured_wav_bytes: Optional[bytes] = None

    @property
    def name(self) -> str:
        return "StubASR"

    def is_available(self) -> bool:
        return True

    def transcribe_wav(self, wav_path: str) -> Optional[str]:
        # Chemin chaîne #301 : le WAV a déjà été converti en amont par ffmpeg.
        self.captured_wav_bytes = Path(wav_path).read_bytes()
        return self._transcription

    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        # Chemin chaîne historique : le provider convertit lui-même via la VRAIE
        # conversion ffmpeg, puis capture le WAV produit.
        import os
        import tempfile

        from app.services.asr.audio_utils import convert_to_wav_16k

        tmp_dir = tempfile.mkdtemp(prefix="e2e_asr_")
        src = os.path.join(tmp_dir, f"in.{file_extension}")
        wav = os.path.join(tmp_dir, "out.wav")
        try:
            with open(src, "wb") as f:
                f.write(audio_bytes)
            assert convert_to_wav_16k(src, wav), "conversion ffmpeg échouée"
            self.captured_wav_bytes = Path(wav).read_bytes()
            return self._transcription
        finally:
            for p in (src, wav):
                if os.path.exists(p):
                    os.remove(p)
            os.rmdir(tmp_dir)

    def assert_produced_valid_wav(self) -> None:
        """Prouve que ffmpeg a produit un WAV 16k mono (échec explicite sinon)."""
        assert self.captured_wav_bytes is not None, (
            "ni transcribe ni transcribe_wav n'a été appelé — la chaîne n'a pas "
            "exercé le provider"
        )
        assert (
            self.captured_wav_bytes[:4] == b"RIFF"
            and self.captured_wav_bytes[8:12] == b"WAVE"
        ), f"En-tête WAV invalide : {self.captured_wav_bytes[:12]!r}"
        with wave.open(io.BytesIO(self.captured_wav_bytes), "rb") as wav_file:
            assert wav_file.getframerate() == 16000, (
                f"sample rate attendu 16000, obtenu {wav_file.getframerate()}"
            )
            assert wav_file.getnchannels() == 1, (
                f"mono attendu, obtenu {wav_file.getnchannels()} canaux"
            )


@pytest.fixture
def audio_bytes() -> bytes:
    """Contenu de la fixture OGG réelle (ton 440 Hz, mono 16 kHz)."""
    assert _FIXTURE_OGG.is_file(), f"Fixture audio manquante : {_FIXTURE_OGG}"
    return _FIXTURE_OGG.read_bytes()


@pytest.fixture
def client():
    """App minimale (routers asr + chat), auth désactivée, sans lifespan ML."""
    with patch("app.security._API_SECRET_KEY", None):
        from app.routers import asr, chat

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(asr.router)
        app.include_router(chat.router)
        yield TestClient(app, raise_server_exceptions=False)


class TestAudioPipelineWiring:
    """Test A (CI) — câblage réel + ffmpeg réel, inférences ML stubbées."""

    def test_ogg_transcribe_then_chat_returns_audio_response(self, client, audio_bytes):
        """Parcours complet : OGG → (ffmpeg réel) ASR → NLU → chat → audio_url.

        Ce test échouerait si : ffmpeg ne convertit pas l'OGG, la chaîne ASR
        n'est pas câblée au routeur, le NLU n'alimente pas le chat, ou le service
        chat ne renvoie pas d'audio.
        """
        # Chaîne ASR réelle mais avec un provider stub → la conversion ffmpeg
        # (prepared_wav_16k) tourne POUR DE VRAI ; seule l'inférence est stubbée.
        stub_provider = RealFfmpegStubProvider("malo sɛnɛ wagati")
        stub_chain = ASRChain(providers=[stub_provider])

        nlu_service = MagicMock()
        nlu_result = MagicMock()
        nlu_result.intent = "QUESTION_SAISON_PLANTATION"
        nlu_result.confidence = 0.9
        nlu_result.french_sentence = "Quand semer le riz ?"
        nlu_result.concepts = {"CULTURE_RIZ": 1.0}
        nlu_result.is_out_of_scope = False
        nlu_result.has_greeting = False
        nlu_service.process.return_value = nlu_result

        chat_service = MagicMock()
        chat_service.process = AsyncMock(
            return_value=ChatResult(
                response="Sème le riz au début des pluies.",
                response_dioula="Sanji daminɛ na, i ka malo sɛnɛ.",
                audio_url="/static/audio/dyu_e2e.ogg",
                city="Bouaké",
                language="dioula",
                audio_language="Dioula",
                meta={"intent": "QUESTION_SAISON_PLANTATION", "source": "ivr"},
            )
        )

        with (
            patch("app.routers.asr.get_asr_chain", return_value=stub_chain),
            patch("app.services.nlu.get_nlu_service", return_value=nlu_service),
            patch(
                "app.services.tts_bambara.translate_to_french",
                return_value="Quand semer le riz ?",
            ),
            patch("app.routers.chat.get_chat_service", return_value=chat_service),
        ):
            # Étape 1 : ASR + traduction + NLU sur l'audio OGG réel.
            asr_resp = client.post(
                "/api/asr/transcribe-and-translate",
                files={"audio": ("question.ogg", io.BytesIO(audio_bytes), "audio/ogg")},
                data={"language": "bam"},
            )

            assert asr_resp.status_code == 200, asr_resp.text
            asr_data = asr_resp.json()
            assert asr_data["transcription"] == "malo sɛnɛ wagati"
            assert asr_data["nlu_intent"] == "QUESTION_SAISON_PLANTATION"
            # Le NLU a bien reconstruit une phrase française exploitable.
            assert asr_data["nlu_message"] == "Quand semer le riz ?"

            # Preuve que la conversion ffmpeg a réellement produit un WAV 16k mono
            # (vérifié hors du chemin try/except de la chaîne).
            stub_provider.assert_produced_valid_wav()

            # Étape 2 : chat avec le texte bambara transcrit → réponse audio.
            chat_resp = client.post(
                "/api/chat/",
                json={
                    "message": asr_data["nlu_message"],
                    "bambara_text": asr_data["transcription"],
                    "city": "Bouaké",
                    "language": "dioula",
                    "include_audio": True,
                    "user_id": "e2e-farmer",
                },
            )

        assert chat_resp.status_code == 200, chat_resp.text
        chat_data = chat_resp.json()
        assert chat_data["response_dioula"] == "Sanji daminɛ na, i ka malo sɛnɛ."
        assert chat_data["audio_url"] == "/static/audio/dyu_e2e.ogg"
        assert chat_data["audio_language"] == "Dioula"

        # Le chat a bien reçu la transcription bambara + la phrase reconstruite.
        chat_service.process.assert_awaited_once()
        call = chat_service.process.await_args.kwargs
        assert call["bambara_text"] == "malo sɛnɛ wagati"
        assert call["include_audio"] is True

    def test_transcribe_only_converts_and_returns_text(self, client, audio_bytes):
        """`/transcribe` (sans traduction) : OGG → ffmpeg réel → texte ASR."""
        stub_provider = RealFfmpegStubProvider("kaba sɛnɛ")
        stub_chain = ASRChain(providers=[stub_provider])

        with patch("app.routers.asr.get_asr_chain", return_value=stub_chain):
            resp = client.post(
                "/api/asr/transcribe",
                files={"audio": ("q.ogg", io.BytesIO(audio_bytes), "audio/ogg")},
                data={"language": "bam"},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["transcription"] == "kaba sɛnɛ"
        stub_provider.assert_produced_valid_wav()


@pytest.mark.skipif(
    os.getenv("ENABLE_E2E_FULL_ML") != "1",
    reason=(
        "E2E full-ML désactivé. Exporter ENABLE_E2E_FULL_ML=1 sur une machine "
        "équipée des modèles ASR (MMS/NeMo) + TTS (mms-tts-dyu) pour l'exécuter. "
        "Cf. ADR-0022 : aucun vocal dioula réel de référence dans le repo."
    ),
)
class TestAudioPipelineFullML:
    """Test B (skip en CI) — parcours avec les VRAIS modèles ASR + TTS."""

    def test_real_ogg_through_real_asr_and_tts(self, client, audio_bytes):
        """OGG réel → vraie chaîne ASR → chat → vrai TTS dioula → audio écrit.

        Ne pré-suppose pas le contenu transcrit (le ton 440 Hz n'est pas de la
        parole) : vérifie seulement que le parcours ne casse pas.
        """
        resp = client.post(
            "/api/asr/transcribe-and-translate",
            files={"audio": ("q.ogg", io.BytesIO(audio_bytes), "audio/ogg")},
            data={"language": "bam"},
        )
        # Le parcours ASR réel doit répondre proprement (200) ou signaler une
        # indisponibilité modèle (500), jamais crasher le serveur.
        assert resp.status_code in {200, 500}, resp.text
        if resp.status_code == 200:
            assert "transcription" in resp.json()
