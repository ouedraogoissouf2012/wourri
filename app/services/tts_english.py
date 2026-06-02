"""
WOURI — TTS Anglais (Piper TTS) (ADR-0015 PR 4/4).

100% GRATUIT — Voix locale haute qualité (Piper EN US Amy medium).
Conversion en OGG Opus pour compatibilité WhatsApp.

Pattern strictement identique a `tts_french.py` :
  - Pas un seul chemin hardcoded
  - Lecture de `app.config.Settings` (Pydantic Settings)
  - cwd subprocess dérivé automatiquement du chemin du binaire
  - Graceful degradation si modèle absent (logger warning, retourne None)

Pré-requis utilisateur (téléchargement manuel, 1 fois) :
  Linux/Mac :
    wget -O /opt/piper-voices/en_US-amy-medium.onnx \\
      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
    wget -O /opt/piper-voices/en_US-amy-medium.onnx.json \\
      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
  Windows :
    cf README et docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md

Variables d'env (cf. .env.example) :
  PIPER_PATH     : binaire piper (defaut : "piper" = PATH système)
  PIPER_MODEL_EN : chemin absolu vers en_US-amy-medium.onnx (defaut : vide → TTS désactivé)

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #279 (PR 4/4)
"""
import asyncio
import logging
import re
import subprocess
import uuid
from pathlib import Path

from app.config import get_settings
from app.services._ffmpeg import get_ffmpeg
from app.services.tts_french import _piper_cwd

logger = logging.getLogger(__name__)


def _get_ffmpeg_path() -> str:
    try:
        return get_ffmpeg()
    except RuntimeError:
        return "ffmpeg"


def clean_text(text: str) -> str:
    """Nettoie le texte du markdown avant TTS.

    Identique a `tts_french.clean_text`. Duplique (et non factorise) car
    seuls 2 consommateurs < seuil 4 du projet, et permet d'avoir des règles
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
        None: si TTS échoue, modèle EN absent, ou conversion ffmpeg échoue.
    """
    if not text:
        return None

    settings = get_settings()
    piper_path = settings.piper_path
    piper_model = settings.piper_model_en

    # Graceful degradation : si modèle EN pas configuré (PIPER_MODEL_EN vide),
    # on désactive le TTS EN sans crash — le caller affiche le texte sans audio.
    if not piper_model:
        logger.warning(
            "[TTS-EN] PIPER_MODEL_EN vide dans .env — TTS anglais désactivé"
        )
        return None

    clean = clean_text(text)
    if not clean:
        return None

    try:
        file_id = uuid.uuid4()
        wav_filename = f"en_{file_id}_temp.wav"
        ogg_filename = f"en_{file_id}.ogg"

        base_dir = Path(__file__).resolve().parent.parent.parent
        audio_dir = base_dir / settings.audio_output_dir
        audio_dir.mkdir(parents=True, exist_ok=True)
        wav_filepath = audio_dir / wav_filename
        ogg_filepath = audio_dir / ogg_filename

        # cwd dérivé automatiquement (None ou parent du binaire).
        # JAMAIS de chemin hardcoded.
        await asyncio.to_thread(
            subprocess.run,
            [piper_path, "--model", piper_model, "--output_file", str(wav_filepath)],
            input=clean.encode("utf-8"),
            capture_output=True,
            timeout=30,
            cwd=_piper_cwd(piper_path),
        )

        if wav_filepath.exists() and wav_filepath.stat().st_size > 0:
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    [
                        _get_ffmpeg_path(),
                        "-i", str(wav_filepath),
                        "-c:a", "libopus",
                        "-b:a", "64k",
                        "-ar", "48000",
                        "-ac", "1",
                        "-y",
                        str(ogg_filepath),
                    ],
                    capture_output=True,
                    timeout=30,
                )

                wav_filepath.unlink(missing_ok=True)

                if ogg_filepath.exists() and ogg_filepath.stat().st_size > 0:
                    return f"/static/audio/{ogg_filename}"

            except Exception as conv_err:
                logger.error("Erreur conversion ffmpeg (EN): %s", conv_err)
                if wav_filepath.exists():
                    return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error("Erreur TTS anglais Piper: %s", e)

    return None


# Voix Piper installée par défaut (Amy = femme américaine)
PIPER_EN_VOICE = "en_US-amy-medium"
