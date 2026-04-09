"""
WOURI - ASR Provider MMS-1B-ALL générique (8 langues ivoiriennes).

Provider fallback pour toutes les langues ivoiriennes. Utilise le modèle
facebook/mms-1b-all avec switch d'adapter par langue.
"""
import logging
import os
from typing import Optional

from app.services.asr.base import ASRProvider
from app.services.asr.audio_utils import transcribe_with_temp_files
from app.data.constants import get_asr_languages

logger = logging.getLogger(__name__)

IVORIAN_ASR_LANGUAGES = get_asr_languages()

_torch_available = False
_torchaudio_available = False
_torch = None
_torchaudio = None

try:
    import torch as torch_mod
    _torch = torch_mod
    _torch_available = True
except ImportError:
    pass

try:
    import torchaudio as torchaudio_mod
    _torchaudio = torchaudio_mod
    _torchaudio_available = True
except ImportError:
    pass


class MMSGenericASR(ASRProvider):
    """ASR multi-langues via MMS-1B-ALL (8 langues ivoiriennes)."""

    def __init__(self, language_code: str = "bam"):
        self._language_code = language_code
        self._current_loaded_lang: Optional[str] = None

    @property
    def name(self) -> str:
        lang_name = IVORIAN_ASR_LANGUAGES.get(
            self._language_code, (self._language_code,)
        )[0]
        return f"MMS-generic ({lang_name})"

    def is_available(self) -> bool:
        return _torch_available

    def set_language(self, language_code: str) -> None:
        """Change la langue cible. Force le rechargement de l'adapter si nécessaire."""
        if language_code != self._language_code:
            self._language_code = language_code

    def _get_model(self):
        from app.services.model_registry import registry

        # Si la langue a changé, décharger l'ancien adapter
        if (self._current_loaded_lang is not None
                and self._current_loaded_lang != self._language_code):
            registry.unload("mms_ivorian")

        def _load():
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            logger.info("[%s] Chargement modèle pour %s...", self.name, self._language_code)
            model_id = "facebook/mms-1b-all"
            processor = Wav2Vec2Processor.from_pretrained(model_id)
            model = Wav2Vec2ForCTC.from_pretrained(model_id)

            processor.tokenizer.set_target_lang(self._language_code)
            model.load_adapter(self._language_code)

            logger.info("[%s] Modèle chargé!", self.name)
            return (model, processor)

        result = registry.get("mms_ivorian", loader=_load)
        self._current_loaded_lang = self._language_code
        return result

    def _load_audio(self, wav_path: str):
        """Charge un WAV et retourne (waveform_numpy, sample_rate)."""
        if _torchaudio_available:
            try:
                waveform, sr = _torchaudio.load(wav_path)
                return waveform.squeeze().numpy(), sr
            except Exception:
                pass

        try:
            import soundfile as sf
            return sf.read(wav_path, dtype="float32")
        except Exception:
            pass

        try:
            from scipy.io import wavfile
            sr, waveform = wavfile.read(wav_path)
            return waveform.astype("float32") / 32768.0, sr
        except Exception:
            pass

        return None, None

    def _transcribe_wav(self, wav_path: str) -> Optional[str]:
        """Transcrit un WAV 16kHz avec MMS-1B-ALL."""
        result = self._get_model()
        if result is None:
            return None
        model, processor = result

        try:
            waveform, sample_rate = self._load_audio(wav_path)
            if waveform is None:
                logger.error("[%s] Impossible de charger l'audio", self.name)
                return None

            # Resampler si nécessaire
            if sample_rate != 16000:
                from scipy import signal
                import numpy as np
                num_samples = int(len(waveform) * 16000 / sample_rate)
                waveform = signal.resample(waveform, num_samples).astype(np.float32)

            inputs = processor(waveform, sampling_rate=16000, return_tensors="pt")

            with _torch.no_grad():
                logits = model(**inputs).logits

            predicted_ids = _torch.argmax(logits, dim=-1)[0]
            transcription = processor.decode(predicted_ids)
            return transcription.strip()

        except Exception as e:
            logger.error("[%s] Erreur transcription: %s", self.name, e, exc_info=True)
            return None

    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        if not self.is_available():
            return None

        if self._language_code not in IVORIAN_ASR_LANGUAGES:
            logger.warning("[%s] Langue '%s' non supportée", self.name, self._language_code)
            return None

        result = await transcribe_with_temp_files(
            audio_bytes, file_extension, self._transcribe_wav, self.name,
        )

        if result:
            logger.info("[%s] Transcription: '%s'", self.name, result)

        return result
