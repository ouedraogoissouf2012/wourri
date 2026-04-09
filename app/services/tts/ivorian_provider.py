"""
WOURI - TTS Provider langues ivoiriennes (facebook/mms-tts-*).

Wrapper autour de tts_ivoirian.py existant.
Supporte les 8 langues ivoiriennes via un seul provider configurable.
"""
import logging
from typing import Optional

from app.services.tts.base import TTSProvider
from app.data.constants import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


class IvorianTTSProvider(TTSProvider):
    """TTS pour une langue ivoirienne spécifique via facebook/mms-tts-*."""

    def __init__(self, lang_code: str):
        if lang_code not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Langue '{lang_code}' non supportée. "
                             f"Codes valides: {list(SUPPORTED_LANGUAGES.keys())}")
        self._lang_code = lang_code

    @property
    def language_code(self) -> str:
        return self._lang_code

    @property
    def language_name(self) -> str:
        return SUPPORTED_LANGUAGES[self._lang_code]["display_name"]

    def is_available(self) -> bool:
        from app.services.tts_ivoirian import TORCH_AVAILABLE
        return TORCH_AVAILABLE

    def synthesize(self, text: str) -> Optional[str]:
        from app.services.tts_ivoirian import synthesize_ivorian_text
        return synthesize_ivorian_text(text, self._lang_code)
