"""
WOURI - ASR Bambara via NeMo (decodeur TDT complet)
Utilise model.transcribe() directement - beaucoup plus precis que la tete CTC seule.
Les fichiers temp sont dans C:/soloni/temp/ pour eviter les problemes de chemin.
"""
import asyncio
import logging
import os
import uuid
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

import tempfile
# Chemin du modèle NeMo — configurable via NEMO_MODEL_PATH dans .env
# Par défaut : cherche dans le cache HuggingFace standard (cross-platform)
NEMO_PATH = os.getenv(
    "NEMO_MODEL_PATH",
    os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface", "hub",
        "models--RobotsMali--soloni-114m-tdt-ctc-v0", "snapshots",
        "c0078bb2285e6157960710c5751bbdf83b1a758d", "soloni-114m-tdt-ctc-v0.nemo"
    )
)
TEMP_DIR = os.getenv("NEMO_TEMP_DIR", os.path.join(tempfile.gettempdir(), "soloni_temp"))

NEMO_AVAILABLE = False
nemo_asr = None
torch = None

try:
    import nemo.collections.asr as _nemo_asr
    import torch as _torch
    nemo_asr = _nemo_asr
    torch = _torch
    NEMO_AVAILABLE = True
    logger.info("[ASR-NEMO] NeMo disponible")
except ImportError as e:
    logger.warning(f"[ASR-NEMO] NeMo non installe: {e}")

from app.services.model_registry import registry


def get_nemo_model():
    """Charge le modele NeMo Soloni (lazy loading, via ModelRegistry)"""
    if not NEMO_AVAILABLE:
        return None

    if not os.path.exists(NEMO_PATH):
        logger.warning(f"[ASR-NEMO] Modele non trouve: {NEMO_PATH}")
        return None

    def _load():
        logger.info("[ASR-NEMO] Chargement modele NeMo Soloni...")
        model = nemo_asr.models.ASRModel.restore_from(
            NEMO_PATH, map_location=torch.device('cpu')
        )
        model.eval()

        # Activer malsd_batch — stratégie recommandée par NeMo pour les modèles TDT
        # (beam/default est expérimental et moins précis sur les syllabes courtes)
        try:
            from omegaconf import open_dict
            with open_dict(model.cfg):
                model.cfg.decoding.strategy = "beam"
                model.cfg.decoding.beam.beam_size = 4
                model.cfg.decoding.beam.search_type = "malsd_batch"
            model.change_decoding_strategy(model.cfg.decoding)
            logger.info("[ASR-NEMO] Décodeur malsd_batch activé (beam_size=4, TDT optimisé)")
        except Exception as beam_err:
            logger.warning(f"[ASR-NEMO] malsd_batch non disponible, mode greedy: {beam_err}")

        logger.info("[ASR-NEMO] Modele charge!")
        return model

    try:
        return registry.get("nemo_soloni", loader=_load)
    except Exception as e:
        logger.error(f"[ASR-NEMO] Erreur chargement: {e}")
        return None


def transcribe_wav(wav_path: str) -> Optional[str]:
    """Transcrit un fichier WAV avec le decodeur TDT complet de NeMo"""
    model = get_nemo_model()
    if model is None:
        return None

    try:
        with torch.no_grad():
            results = model.transcribe([wav_path])

        if not results:
            return ""

        result = results[0]
        # Avec beam search (beam_size > 1), results[0] est une LISTE d'hypothèses
        # La meilleure hypothèse est toujours en position [0]
        if isinstance(result, list):
            if not result:
                return ""
            result = result[0]
        # EncDecHybridRNNTCTCBPEModel retourne des objets Hypothesis
        if hasattr(result, 'text'):
            return result.text.strip()
        return str(result).strip()

    except Exception as e:
        logger.error(f"[ASR-NEMO] Erreur inference: {e}", exc_info=True)
        return None


def _convert_to_wav_16k(input_path: str, output_path: str) -> bool:
    """Convertit en WAV 16kHz mono via ffmpeg"""
    from app.services._ffmpeg import get_ffmpeg
    try:
        ffmpeg_path = get_ffmpeg()
    except RuntimeError:
        logger.error("[ASR-NEMO] FFmpeg non trouve")
        return False

    try:
        cmd = [
            ffmpeg_path, '-y', '-i', input_path,
            '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        logger.error(f"[ASR-NEMO] Erreur ffmpeg: {e}")
        return False


async def transcribe_bambara_nemo(audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
    """Point d'entree: bytes audio -> texte bambara via NeMo TDT"""
    os.makedirs(TEMP_DIR, exist_ok=True)

    temp_id = uuid.uuid4()
    temp_path = os.path.join(TEMP_DIR, f"nemo_{temp_id}.{file_extension}")
    wav_path  = os.path.join(TEMP_DIR, f"nemo_{temp_id}.wav")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if not _convert_to_wav_16k(temp_path, wav_path):
            logger.error("[ASR-NEMO] Echec conversion WAV")
            return None

        # Inférence ML dans un thread séparé pour ne pas bloquer asyncio
        result = await asyncio.to_thread(transcribe_wav, wav_path)
        # Corriger les fusions syllabiques typiques de NeMo (ex: "anisogma" → "a ni sɔgɔma")
        if result:
            from app.services.asr_bambara_normalizer import normalize_bambara_asr
            result = normalize_bambara_asr(result)
        logger.info(f"[ASR-NEMO] Transcription: '{result}'")
        return result

    finally:
        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass


def check_nemo_asr_status() -> dict:
    return {
        "nemo_available": NEMO_AVAILABLE,
        "model_path_exists": os.path.exists(NEMO_PATH),
        "model_loaded": registry.is_loaded("nemo_soloni"),
    }
