"""
WOURI - TTSFactory : crée le bon TTSProvider selon la langue demandée.

Respecte Open/Closed : ajouter une langue = ajouter un provider,
sans modifier la factory.

Gestion mémoire LRU : max 3 providers chargés simultanément.
"""
import logging
from collections import OrderedDict
from typing import Optional

from app.services.tts.base import TTSProvider
from app.data.constants import SUPPORTED_LANGUAGES, resolve_language_alias

logger = logging.getLogger(__name__)

# Nombre max de providers en cache (limite mémoire)
_MAX_CACHED_PROVIDERS = 3


class TTSFactory:
    """Factory + cache LRU pour les TTSProviders.

    Usage :
        factory = get_tts_factory()
        provider = factory.get_provider("bam")
        audio_url = provider.synthesize("texte bambara")
    """

    def __init__(self, max_cached: int = _MAX_CACHED_PROVIDERS):
        self._cache: OrderedDict[str, TTSProvider] = OrderedDict()
        self._max_cached = max_cached

    def get_provider(self, language: str) -> Optional[TTSProvider]:
        """Retourne le TTSProvider pour la langue demandée.

        Accepte les codes ISO (bam, dyu, fra) et les alias (dioula, bambara).
        Gère un cache LRU : les providers les moins utilisés sont évincés.

        Returns:
            TTSProvider ou None si la langue n'est pas supportée.
        """
        resolved = self._resolve(language)
        if resolved is None:
            logger.warning("[TTSFactory] Langue '%s' non reconnue", language)
            return None

        # Cache hit → déplacer en fin (most recently used)
        if resolved in self._cache:
            self._cache.move_to_end(resolved)
            return self._cache[resolved]

        # Cache miss → créer le provider
        provider = self._create_provider(resolved)
        if provider is None:
            return None

        # Evincer le plus ancien si cache plein
        if len(self._cache) >= self._max_cached:
            evicted_key, evicted = self._cache.popitem(last=False)
            logger.info("[TTSFactory] Provider '%s' évincé du cache (LRU)", evicted_key)

        self._cache[resolved] = provider
        return provider

    def list_cached(self) -> list[str]:
        """Retourne les codes des providers actuellement en cache."""
        return list(self._cache.keys())

    def _resolve(self, language: str) -> Optional[str]:
        """Résout un code ou alias vers un code canonique."""
        lang_lower = language.lower().strip()

        # Codes spéciaux hors SUPPORTED_LANGUAGES
        if lang_lower in ("fra", "french", "français"):
            return "fra"
        if lang_lower in ("dyu", "dioula_ci"):
            return "dyu"

        # Résolution via constants
        resolved = resolve_language_alias(lang_lower)
        if resolved:
            return resolved

        return None

    def _create_provider(self, code: str) -> Optional[TTSProvider]:
        """Crée une instance du provider approprié."""
        if code == "fra":
            from app.services.tts.french_provider import FrenchTTSProvider
            return FrenchTTSProvider()

        if code == "dyu":
            from app.services.tts.dioula_provider import DioulaTTSProvider
            return DioulaTTSProvider()

        if code == "bam":
            from app.services.tts.bambara_provider import BambaraTTSProvider
            return BambaraTTSProvider()

        if code in SUPPORTED_LANGUAGES:
            from app.services.tts.ivorian_provider import IvorianTTSProvider
            return IvorianTTSProvider(code)

        logger.warning("[TTSFactory] Pas de provider pour '%s'", code)
        return None


# Singleton
_factory: Optional[TTSFactory] = None


def get_tts_factory() -> TTSFactory:
    """Retourne la factory TTS singleton."""
    global _factory
    if _factory is None:
        _factory = TTSFactory()
    return _factory
