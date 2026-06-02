"""
WOURI - TTS Anglais (Piper TTS) (ADR-0015 PR 4/4).

100% GRATUIT - Voix locale haute qualité (Piper EN US Amy medium).
Conversion en OGG Opus pour compatibilité WhatsApp.

Pattern identique a tts_french.py (Piper FR Tom). Permet ajout simple de
nouvelles langues europeennes (espagnol, portugais) dans le futur via le
meme template, sans toucher au code existant — OCP.

Pré-requis (téléchargement manuel par l'utilisateur) :
  - Modèle ONNX : C:\\piper-tts\\en_US-amy-medium.onnx (~60 MB)
  - Config ONNX : C:\\piper-tts\\en_US-amy-medium.onnx.json (~1 KB)

Téléchargement depuis HuggingFace rhasspy/piper-voices :
  https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/amy/medium

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #279 (PR 4/4)
"""
import asyncio
import logging
import os
import re
import subprocess
import uuid

from app.config import get_settings
from app.services._ffmpeg import get_ffmpeg

logger = logging.getLogger(__name__)
settings = get_settings()

# Chemins Piper TTS EN (configurables via .env, defaults Windows usuels)
PIPER_PATH = os.getenv("PIPER_PATH", r"C:\piper-tts\piper.exe")
PIPER_EN_MODEL = os.getenv(
    "PIPER_EN_MODEL", r"C:\piper-tts\en_US-amy-medium.onnx"
)


def _get_ffmpeg_path() -> str:
    try:
        return get_ffmpeg()
    except RuntimeError:
        return "ffmpeg"


FFMPEG_PATH = _get_ffmpeg_path()


def clean_text(text: str) -> str:
    """Nettoie le texte du markdown avant TTS.

    Identique a tts_french.clean_text. Duplique (et non factorise) car
    seuls 2 consommateurs < seuil 4 du projet, et permettre des regles
    propres a EN dans le futur (ex: contractions "you're" si besoin).
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def synthesize_english(text: str) -> str | None:
    """Génère un fichier audio OGG Opus à partir de texte anglais avec Piper TTS.

    Format OGG Opus = format natif WhatsApp.

    Returns:
        str: URL relative du fichier audio (/static/audio/xxx.ogg)
        None: si TTS ou conversion echoue (le caller doit gerer le fallback texte)
    """
    if not text:
        return None

    clean = clean_text(text)
    if not clean:
        return None

    try:
        file_id = uuid.uuid4()
        wav_filename = f"en_{file_id}_temp.wav"
        ogg_filename = f"en_{file_id}.ogg"

        # Chemins absolus pour Piper (cwd Windows)
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        audio_dir = os.path.join(base_dir, settings.audio_output_dir)
        wav_filepath = os.path.join(audio_dir, wav_filename)
        ogg_filepath = os.path.join(audio_dir, ogg_filename)

        os.makedirs(audio_dir, exist_ok=True)

        # Generer WAV avec Piper EN (text via stdin)
        await asyncio.to_thread(
            subprocess.run,
            [PIPER_PATH, "--model", PIPER_EN_MODEL, "--output_file", wav_filepath],
            input=clean.encode("utf-8"),
            capture_output=True,
            timeout=30,
            cwd=r"C:\piper-tts",
        )

        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            try:
                # Conversion WAV -> OGG Opus (format WhatsApp)
                await asyncio.to_thread(
                    subprocess.run,
                    [
                        FFMPEG_PATH,
                        "-i", wav_filepath,
                        "-c:a", "libopus",
                        "-b:a", "64k",
                        "-ar", "48000",
                        "-ac", "1",
                        "-y",
                        ogg_filepath,
                    ],
                    capture_output=True,
                    timeout=30,
                )

                os.remove(wav_filepath)

                if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                    return f"/static/audio/{ogg_filename}"

            except Exception as conv_err:
                logger.error(f"Erreur conversion ffmpeg (EN): {conv_err}")
                # Fallback : retourner le WAV brut si conversion echoue
                if os.path.exists(wav_filepath):
                    return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error(f"Erreur TTS anglais Piper: {e}")

    return None


# Voix Piper installée (Amy = femme americaine)
PIPER_EN_VOICE = "en_US-amy-medium"
