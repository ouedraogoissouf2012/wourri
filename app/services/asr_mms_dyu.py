"""
WOURI - ASR Dioula via MMS-1B-ALL adapter fine-tuné (AXE-4)

Utilise l'adapter dyu fine-tuné sur Common Voice dyu v24 (295 clips).
Complémentaire à NeMo Soloni : utilisé en second passage quand NeMo
ne détecte pas de mots-clés agricoles attendus.
"""
import asyncio
import logging
import os
import uuid
import subprocess
import tempfile
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

ADAPTER_PATH = Path(__file__).parent.parent.parent / "modeles_manuels" / "mms-dioula-adapter"
TEMP_DIR = os.getenv("MMS_TEMP_DIR", os.path.join(tempfile.gettempdir(), "mms_dyu_temp"))

MMS_DYU_AVAILABLE = False
torch = None

try:
    import torch as _torch
    torch = _torch
    MMS_DYU_AVAILABLE = True
except ImportError:
    logger.warning("[ASR-MMS-DYU] torch non disponible")

from app.services.model_registry import registry


def get_mms_dyu_model():
    """Charge le modèle MMS-dyu fine-tuné (lazy loading, via ModelRegistry)."""
    if not MMS_DYU_AVAILABLE:
        return None, None

    if not ADAPTER_PATH.exists():
        logger.warning(f"[ASR-MMS-DYU] Adapter non trouvé: {ADAPTER_PATH}")
        return None, None

    def _load():
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        logger.info("[ASR-MMS-DYU] Chargement adapter MMS-dyu fine-tuné...")
        model = Wav2Vec2ForCTC.from_pretrained(str(ADAPTER_PATH))
        processor = Wav2Vec2Processor.from_pretrained(str(ADAPTER_PATH))
        model.eval()
        logger.info("[ASR-MMS-DYU] Adapter chargé!")
        return (model, processor)

    try:
        return registry.get("mms_dyu", loader=_load)
    except Exception as e:
        logger.error(f"[ASR-MMS-DYU] Erreur chargement: {e}")
        return None, None


def transcribe_wav_mms(wav_path: str) -> Optional[str]:
    """Transcrit un WAV 16kHz avec MMS-dyu adapter."""
    model, processor = get_mms_dyu_model()
    if model is None:
        return None

    try:
        import librosa
        audio, sr = librosa.load(wav_path, sr=16000)
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt")

        with torch.no_grad():
            logits = model(**inputs).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = processor.batch_decode(predicted_ids)[0]
        return transcription.strip()

    except Exception as e:
        logger.error(f"[ASR-MMS-DYU] Erreur transcription: {e}")
        return None


async def transcribe_dioula_mms(audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
    """Point d'entrée async: bytes audio → texte dioula via MMS-dyu."""
    os.makedirs(TEMP_DIR, exist_ok=True)

    temp_id = uuid.uuid4()
    temp_path = os.path.join(TEMP_DIR, f"mms_{temp_id}.{file_extension}")
    wav_path = os.path.join(TEMP_DIR, f"mms_{temp_id}.wav")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        # Convertir en WAV 16kHz mono
        from app.services._ffmpeg import get_ffmpeg
        try:
            ffmpeg_path = get_ffmpeg()
            cmd = [
                ffmpeg_path, '-y', '-i', temp_path,
                '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
                wav_path
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0 or not os.path.exists(wav_path):
                logger.error("[ASR-MMS-DYU] Échec conversion WAV")
                return None
        except Exception as e:
            logger.error(f"[ASR-MMS-DYU] Erreur ffmpeg: {e}")
            return None

        transcription = await asyncio.to_thread(transcribe_wav_mms, wav_path)
        if transcription:
            logger.info(f"[ASR-MMS-DYU] Transcription: '{transcription}'")
        return transcription

    finally:
        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass


def check_mms_dyu_status() -> dict:
    return {
        "available": MMS_DYU_AVAILABLE,
        "adapter_path": str(ADAPTER_PATH),
        "adapter_exists": ADAPTER_PATH.exists(),
        "model_loaded": registry.is_loaded("mms_dyu"),
    }
