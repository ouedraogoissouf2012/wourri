# -*- coding: utf-8 -*-
"""
WOURI - Nettoyage automatique des fichiers audio temporaires

Supprime les fichiers .ogg et .wav de static/audio/ plus vieux que MAX_AGE_DAYS.
Appelé au démarrage de l'API et toutes les 24h via asyncio.
"""
import asyncio
import time
import logging
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 7
_cleanup_task: asyncio.Task | None = None


def cleanup_old_audio() -> int:
    """Supprime les fichiers audio plus vieux que MAX_AGE_DAYS.
    Retourne le nombre de fichiers supprimés.
    """
    settings = get_settings()
    audio_dir = Path(settings.audio_output_dir)

    if not audio_dir.exists():
        return 0

    max_age_seconds = MAX_AGE_DAYS * 24 * 3600
    now = time.time()
    deleted = 0

    for pattern in ("*.ogg", "*.wav", "*.mp3"):
        for f in audio_dir.glob(pattern):
            try:
                if now - f.stat().st_mtime > max_age_seconds:
                    f.unlink()
                    deleted += 1
            except OSError:
                pass  # fichier déjà supprimé ou en cours d'utilisation

    if deleted:
        logger.info(f"[CLEANUP] {deleted} fichiers audio supprimés (>{MAX_AGE_DAYS}j)")
    return deleted


async def _cleanup_loop():
    """Boucle de nettoyage toutes les 24h."""
    while True:
        await asyncio.sleep(24 * 3600)
        await asyncio.to_thread(cleanup_old_audio)


def start_cleanup_scheduler():
    """Lance la tâche de nettoyage périodique en arrière-plan.
    À appeler dans le lifespan FastAPI après yield.
    """
    global _cleanup_task
    # Nettoyage immédiat au démarrage
    deleted = cleanup_old_audio()
    logger.info(f"[CLEANUP] Démarrage: {deleted} fichiers supprimés")

    # Planifier le nettoyage toutes les 24h
    _cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("[CLEANUP] Planificateur 24h actif")


def stop_cleanup_scheduler():
    """Annule la tâche de nettoyage (graceful shutdown)."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
