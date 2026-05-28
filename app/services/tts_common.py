"""
Wouri - Helpers TTS partages entre les services bambara/dioula.

Extrait du refactor 2026-05-28 (audit P1 #4 — DRY mutualisation tts_bambara /
tts_dioula). Comportement strictement identique aux 2 implementations
precedentes (verifie par smoke + pytest 202/202).

NOTE : `tts_ivoirian.py` a sa propre implementation `convert_wav_to_ogg`
SANS normalisation EBU R128 (pipeline subprocess simple). Issue backlog
dediee pour aligner si besoin (regression audio possible si on bascule).
"""
from __future__ import annotations

import logging
import os

from app.services._ffmpeg import get_ffmpeg as find_ffmpeg
from app.services._ffmpeg import wav_to_ogg_normalized

logger = logging.getLogger(__name__)


def convert_wav_to_ogg(wav_path: str, ogg_path: str) -> bool:
    """Convertit un fichier WAV en OGG Opus avec normalisation loudnorm EBU R128.

    Strategie en 2 niveaux :
      1. `_ffmpeg.wav_to_ogg_normalized` (source unique, loudnorm si dispo)
      2. Fallback pydub sans loudnorm si ffmpeg echoue

    Le fichier WAV source est supprime apres conversion reussie (les 2 chemins).

    Args:
        wav_path: chemin du fichier WAV source
        ogg_path: chemin du fichier OGG cible

    Returns:
        True si la conversion a reussi, False sinon
    """
    # Chemin 1 : ffmpeg avec normalisation EBU R128 (preferred)
    if wav_to_ogg_normalized(wav_path, ogg_path):
        return True

    # Chemin 2 : Fallback pydub (sans loudnorm)
    try:
        from pydub import AudioSegment
        try:
            ffmpeg_path = find_ffmpeg()
            if ffmpeg_path != "ffmpeg":
                AudioSegment.converter = ffmpeg_path
        except RuntimeError:
            pass
        audio = AudioSegment.from_wav(wav_path)
        audio.export(ogg_path, format="ogg", codec="libopus", bitrate="64k")
        try:
            os.remove(wav_path)
        except OSError:
            pass
        logger.info("Conversion WAV -> OGG reussie avec pydub")
        return True
    except Exception as e:
        logger.error(f"Erreur pydub: {e}")

    return False
