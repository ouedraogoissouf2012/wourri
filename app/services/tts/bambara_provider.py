"""
WOURI - TTS Provider Bambara (facebook/mms-tts-bam).

Wrapper autour de tts_bambara.py existant.
"""
import logging
from typing import Optional

from app.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)


class BambaraTTSProvider(TTSProvider):
    """TTS bambara via facebook/mms-tts-bam."""

    @property
    def language_code(self) -> str:
        return "bam"

    @property
    def language_name(self) -> str:
        return "Bambara"

    def is_available(self) -> bool:
        from app.services.tts_bambara import TORCH_AVAILABLE
        return TORCH_AVAILABLE

    def synthesize(self, text: str) -> Optional[str]:
        from app.services.tts_bambara import synthesize_bambara_text
        return synthesize_bambara_text(text)
