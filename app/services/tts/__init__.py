"""
WOURI - Package TTS.

Point d'entrée unique pour la synthèse vocale.
Usage :
    from app.services.tts import get_tts_factory
    factory = get_tts_factory()
    provider = factory.get_provider("bam")
    audio_url = provider.synthesize("texte bambara")
"""
from app.services.tts.base import TTSProvider
from app.services.tts.factory import TTSFactory, get_tts_factory

__all__ = [
    "TTSProvider",
    "TTSFactory",
    "get_tts_factory",
]
