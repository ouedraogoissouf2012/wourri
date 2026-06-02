"""
WOURI - TTS Français (Piper TTS)
100% GRATUIT - Voix locale haute qualité
Conversion en OGG Opus pour compatibilité WhatsApp

Portabilité : tous les chemins sont lus depuis `app.config.Settings`
(Pydantic Settings) avec defaults universellement portables (binaire dans
PATH système + modèles via env explicite). Aucun chemin Windows hardcoded.
Voir app/config.py section "Piper TTS" pour la documentation des env vars.
"""
import asyncio
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path

from app.config import get_settings
from app.services._ffmpeg import get_ffmpeg

logger = logging.getLogger(__name__)


def _get_ffmpeg_path() -> str:
    """Chemin ffmpeg résolu dynamiquement (PATH système, fallback "ffmpeg")."""
    try:
        return get_ffmpeg()
    except RuntimeError:
        return "ffmpeg"


def _piper_cwd(piper_path: str) -> str | None:
    """Retourne le cwd à utiliser pour le subprocess Piper.

    Si `piper_path` est un chemin absolu (avec un dossier parent existant),
    on retourne ce parent comme cwd (utile sur Windows où Piper a parfois
    besoin de trouver des DLLs adjacentes). Sinon, on retourne None — le
    subprocess hérite du cwd du process parent, comportement standard POSIX.

    JAMAIS de chemin hardcodé : on dérive automatiquement depuis l'env var.
    """
    p = Path(piper_path)
    if p.is_absolute() and p.parent.exists():
        return str(p.parent)
    return None


def clean_text(text: str) -> str:
    """Nettoie le texte du markdown avant TTS"""
    # Supprimer le gras **text** ou __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Supprimer l'italique *text* ou _text_
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # Supprimer les titres # ## ###
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Supprimer les puces - ou *
    text = re.sub(r'^[\-\*]\s+', '', text, flags=re.MULTILINE)
    # Supprimer les liens [text](url)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # Supprimer les backticks `code`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Nettoyer les espaces multiples
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def synthesize_french(text: str) -> str | None:
    """
    Génère un fichier audio OGG Opus à partir de texte français avec Piper TTS.
    Format OGG Opus = format natif WhatsApp pour meilleure compatibilité.

    Returns:
        str: URL relative du fichier audio (/static/audio/xxx.ogg)
        None: si TTS échoue, modèle absent ou conversion ffmpeg échoue.
    """
    if not text:
        return None

    settings = get_settings()
    piper_path = settings.piper_path
    piper_model = settings.piper_model_fr

    # Graceful degradation : si modèle FR pas configuré, on désactive le TTS
    # sans crash — le caller affiche le texte sans audio.
    if not piper_model:
        logger.warning(
            "[TTS-FR] PIPER_MODEL_FR vide dans .env — TTS français désactivé"
        )
        return None

    clean = clean_text(text)
    if not clean:
        return None

    try:
        # Chemins de sortie (toujours absolus, basés sur le chemin du module)
        file_id = uuid.uuid4()
        wav_filename = f"fr_{file_id}_temp.wav"
        ogg_filename = f"fr_{file_id}.ogg"

        base_dir = Path(__file__).resolve().parent.parent.parent
        audio_dir = base_dir / settings.audio_output_dir
        audio_dir.mkdir(parents=True, exist_ok=True)
        wav_filepath = audio_dir / wav_filename
        ogg_filepath = audio_dir / ogg_filename

        # Générer l'audio avec Piper TTS. cwd dérivé du chemin du binaire (None
        # si binaire dans PATH, parent dir si chemin absolu fourni — utile sur
        # Windows pour les DLLs adjacentes). JAMAIS de chemin hardcoded.
        await asyncio.to_thread(
            subprocess.run,
            [piper_path, "--model", piper_model, "--output_file", str(wav_filepath)],
            input=clean.encode("utf-8"),
            capture_output=True,
            timeout=30,
            cwd=_piper_cwd(piper_path),
        )

        # Conversion WAV -> OGG Opus (format natif WhatsApp)
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
                logger.error("Erreur conversion ffmpeg (FR): %s", conv_err)
                # Fallback : retourner le WAV si conversion ffmpeg échoue
                if wav_filepath.exists():
                    return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error("Erreur TTS français Piper: %s", e)

    return None


async def get_available_voices() -> list[dict]:
    """Liste les voix Piper disponibles"""
    return [
        {"name": "fr_FR-tom-medium", "gender": "Male", "locale": "fr-FR", "quality": "medium"},
        {"name": "fr_FR-siwis-medium", "gender": "Female", "locale": "fr-FR", "quality": "medium"}
    ]


# Voix Piper installée (Tom = homme)
PIPER_VOICE = "fr_FR-tom-medium"
