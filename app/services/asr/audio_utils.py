"""
WOURI - Utilitaires audio partagés par tous les ASR providers.

Mutualise la conversion WAV 16kHz + gestion des fichiers temporaires.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import uuid
from typing import Optional, Callable

logger = logging.getLogger(__name__)

_TEMP_DIR = os.getenv(
    "ASR_TEMP_DIR",
    os.path.join(tempfile.gettempdir(), "wourri_asr_temp"),
)


def convert_to_wav_16k(input_path: str, output_path: str) -> bool:
    """Convertit un fichier audio en WAV 16kHz mono via ffmpeg.

    Utilisé par tous les ASR providers — source unique de conversion.
    """
    from app.services._ffmpeg import get_ffmpeg
    try:
        ffmpeg_path = get_ffmpeg()
    except RuntimeError:
        logger.error("[ASR-UTILS] FFmpeg non trouvé")
        return False

    try:
        cmd = [
            ffmpeg_path, '-y', '-i', input_path,
            '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        logger.error("[ASR-UTILS] Erreur conversion ffmpeg: %s", e)
        return False


async def transcribe_with_temp_files(
    audio_bytes: bytes,
    file_extension: str,
    sync_transcribe_fn: Callable[[str], Optional[str]],
    provider_name: str,
) -> Optional[str]:
    """Pipeline commun : bytes → fichier temp → WAV 16kHz → transcription → cleanup.

    Args:
        audio_bytes: Contenu brut de l'audio.
        file_extension: Extension source (ogg, mp3, wav...).
        sync_transcribe_fn: Fonction synchrone qui transcrit un WAV 16kHz.
        provider_name: Nom du provider (pour les logs et noms de fichiers).

    Returns:
        Texte transcrit, ou None si échec.
    """
    os.makedirs(_TEMP_DIR, exist_ok=True)

    temp_id = uuid.uuid4()
    prefix = provider_name.lower().replace(" ", "_")
    temp_path = os.path.join(_TEMP_DIR, f"{prefix}_{temp_id}.{file_extension}")
    wav_path = os.path.join(_TEMP_DIR, f"{prefix}_{temp_id}.wav")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if not convert_to_wav_16k(temp_path, wav_path):
            logger.error("[%s] Échec conversion WAV", provider_name)
            return None

        result = await asyncio.to_thread(sync_transcribe_fn, wav_path)
        return result

    finally:
        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
