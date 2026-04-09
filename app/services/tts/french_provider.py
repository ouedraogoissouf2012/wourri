"""
WOURI - TTS Provider Français (Piper TTS local).

Wrapper autour de tts_french.py existant.
"""
import asyncio
import logging
from typing import Optional

from app.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)


class FrenchTTSProvider(TTSProvider):
    """TTS français via Piper TTS (local, pas de modèle ML lourd)."""

    @property
    def language_code(self) -> str:
        return "fra"

    @property
    def language_name(self) -> str:
        return "Français"

    def is_available(self) -> bool:
        # Piper TTS est toujours disponible si installé
        return True

    def synthesize(self, text: str) -> Optional[str]:
        # synthesize_french est async, on l'appelle via asyncio
        from app.services.tts_french import synthesize_french_sync
        try:
            return synthesize_french_sync(text)
        except AttributeError:
            # Fallback si synthesize_french_sync n'existe pas
            logger.warning("[TTS-FR] synthesize_french_sync non disponible")
            return None
