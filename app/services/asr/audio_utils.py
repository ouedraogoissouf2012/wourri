"""
WOURI - Utilitaires audio partagés par tous les ASR providers.

Mutualise la conversion WAV 16kHz + gestion des fichiers temporaires.
"""
import contextlib
import logging
import os
import re
import subprocess
import tempfile
import uuid
from typing import Optional, Iterator

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


def _safe_prefix(label: str) -> str:
    """Neutralise les séparateurs de chemin d'un nom lisible.

    Le nom lisible d'un provider peut contenir des caractères invalides pour
    un nom de fichier (ex. "MMS-generic (Bambara/Dioula)"). On les remplace
    avant de construire les chemins temporaires, sinon le "/" créerait un
    sous-dossier inexistant.
    """
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


@contextlib.contextmanager
def prepared_wav_16k(audio_bytes: bytes, file_extension: str, label: str) -> Iterator[Optional[str]]:
    """Convertit `audio_bytes` en WAV 16kHz UNE fois et yield son chemin.

    Écrit les bytes dans un fichier temp, convertit via ffmpeg, puis yield le
    chemin du WAV 16k (ou `None` si la conversion échoue). Les deux fichiers
    temporaires (source + WAV) sont nettoyés à la sortie du contexte, même en
    cas d'exception.

    #301 : mutualise la conversion pour que la chaîne ASR ne convertisse qu'une
    seule fois un audio partagé par plusieurs providers (avant : chaque provider
    reconvertissait — 2 à 4 fois le même audio par requête).

    Args:
        audio_bytes: Contenu brut de l'audio.
        file_extension: Extension source (ogg, mp3, wav...).
        label: Nom lisible (provider/chaîne) — logs + préfixe des fichiers temp.

    Yields:
        Le chemin du WAV 16k prêt, ou `None` si la conversion a échoué.
    """
    os.makedirs(_TEMP_DIR, exist_ok=True)

    temp_id = uuid.uuid4()
    prefix = _safe_prefix(label)
    temp_path = os.path.join(_TEMP_DIR, f"{prefix}_{temp_id}.{file_extension}")
    wav_path = os.path.join(_TEMP_DIR, f"{prefix}_{temp_id}.wav")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if not convert_to_wav_16k(temp_path, wav_path):
            logger.error("[%s] Échec conversion WAV", label)
            yield None
        else:
            yield wav_path

    finally:
        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
