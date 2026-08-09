"""
WOURI - ASR Provider MMS-dyu (adapter fine-tuné sur Common Voice dioula).

Provider spécialisé pour le dioula ivoirien. Utilise l'adapter AXE-4
fine-tuné sur 295 clips Common Voice dyu v24.
"""
import logging
from pathlib import Path
from typing import Optional

from app.services.asr.base import ASRProvider
from app.services.asr.audio_utils import transcribe_with_temp_files

logger = logging.getLogger(__name__)

# Racine du repo = 4 niveaux au-dessus de app/services/asr/ (fix #358 : la
# formule à 3 .parent, copiée de l'ancien asr_mms_dyu.py un niveau moins
# profond, résolvait vers app/modeles_manuels/ inexistant → is_available()
# retournait toujours False et l'adapter dioula n'a jamais servi).
ADAPTER_PATH = Path(__file__).parent.parent.parent.parent / "modeles_manuels" / "mms-dioula-adapter"

_torch_available = False
_torch = None

try:
    import torch as torch_mod
    _torch = torch_mod
    _torch_available = True
except ImportError:
    pass


class MMSDyuASR(ASRProvider):
    """ASR dioula CI via MMS-1B-ALL adapter fine-tuné."""

    @property
    def name(self) -> str:
        return "MMS-dyu"

    def is_available(self) -> bool:
        return _torch_available and ADAPTER_PATH.exists()

    def _get_model(self):
        from app.services.model_registry import registry

        def _load():
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            logger.info("[%s] Chargement adapter fine-tuné...", self.name)
            model = Wav2Vec2ForCTC.from_pretrained(str(ADAPTER_PATH))
            processor = Wav2Vec2Processor.from_pretrained(str(ADAPTER_PATH))
            model.eval()
            logger.info("[%s] Adapter chargé!", self.name)
            return (model, processor)

        return registry.get("mms_dyu", loader=_load)

    def _transcribe_wav(self, wav_path: str) -> Optional[str]:
        """Transcrit un WAV 16kHz avec MMS-dyu."""
        result = self._get_model()
        if result is None:
            return None
        model, processor = result

        try:
            import librosa
            audio, _ = librosa.load(wav_path, sr=16000)
            inputs = processor(audio, sampling_rate=16000, return_tensors="pt")

            with _torch.no_grad():
                logits = model(**inputs).logits

            predicted_ids = _torch.argmax(logits, dim=-1)
            transcription = processor.batch_decode(predicted_ids)[0]
            return transcription.strip()

        except Exception as e:
            logger.error("[%s] Erreur transcription: %s", self.name, e)
            return None

    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        if not self.is_available():
            return None

        result = await transcribe_with_temp_files(
            audio_bytes, file_extension, self._transcribe_wav, self.name,
        )

        if result:
            logger.info("[%s] Transcription: '%s'", self.name, result)

        return result
