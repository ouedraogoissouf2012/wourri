"""
WOURI - ASR Dioula via MMS-1B-ALL adapter fine-tuné (AXE-4)

Utilise l'adapter dyu fine-tuné sur Common Voice dyu v24 (295 clips).
Complémentaire à NeMo Soloni : utilisé en second passage quand NeMo
ne détecte pas de mots-clés agricoles attendus.
"""
import asyncio
import os
import uuid
import subprocess
import tempfile
from typing import Optional
from pathlib import Path

ADAPTER_PATH = Path(__file__).parent.parent.parent / "modeles_manuels" / "mms-dioula-adapter"
TEMP_DIR = os.getenv("MMS_TEMP_DIR", os.path.join(tempfile.gettempdir(), "mms_dyu_temp"))

MMS_DYU_AVAILABLE = False
torch = None

try:
    import torch as _torch
    torch = _torch
    MMS_DYU_AVAILABLE = True
except ImportError:
    print("[ASR-MMS-DYU] torch non disponible")

_model = None
_processor = None


def get_mms_dyu_model():
    """Charge le modèle MMS-dyu fine-tuné (lazy loading, singleton)."""
    global _model, _processor

    if not MMS_DYU_AVAILABLE:
        return None, None

    if _model is not None:
        return _model, _processor

    if not ADAPTER_PATH.exists():
        print(f"[ASR-MMS-DYU] Adapter non trouvé: {ADAPTER_PATH}")
        return None, None

    try:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        print("[ASR-MMS-DYU] Chargement adapter MMS-dyu fine-tuné...")
        _model = Wav2Vec2ForCTC.from_pretrained(str(ADAPTER_PATH))
        _processor = Wav2Vec2Processor.from_pretrained(str(ADAPTER_PATH))
        _model.eval()
        print("[ASR-MMS-DYU] Adapter chargé!")
        return _model, _processor

    except Exception as e:
        print(f"[ASR-MMS-DYU] Erreur chargement: {e}")
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
        print(f"[ASR-MMS-DYU] Erreur transcription: {e}")
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
                print("[ASR-MMS-DYU] Échec conversion WAV")
                return None
        except Exception as e:
            print(f"[ASR-MMS-DYU] Erreur ffmpeg: {e}")
            return None

        transcription = await asyncio.to_thread(transcribe_wav_mms, wav_path)
        if transcription:
            print(f"[ASR-MMS-DYU] Transcription: '{transcription}'")
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
        "model_loaded": _model is not None,
    }
