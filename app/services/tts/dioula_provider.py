"""
WOURI - TTS Provider Dioula CI (facebook/mms-tts-dyu).

Wrapper autour de tts_dioula.py existant.
"""
import logging
from typing import Optional

from app.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)


class DioulaTTSProvider(TTSProvider):
    """TTS dioula ivoirien via facebook/mms-tts-dyu."""

    @property
    def language_code(self) -> str:
        return "dyu"

    @property
    def language_name(self) -> str:
        return "Dioula"

    def is_available(self) -> bool:
        from app.services.tts_dioula import TORCH_AVAILABLE
        return TORCH_AVAILABLE

    def synthesize(self, text: str) -> Optional[str]:
        from app.services.tts_dioula import synthesize_dioula_text
        return synthesize_dioula_text(text)
