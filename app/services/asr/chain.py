"""
WOURI - ASRChain : chaîne de fallback configurable entre providers ASR.

La chaîne essaie chaque provider dans l'ordre jusqu'à obtenir un résultat.
Optionnel : filtre par mots-clés agricoles pour déclencher un second passage.

Usage :
    from app.services.asr import get_asr_chain
    chain = get_asr_chain()
    text = await chain.transcribe(audio_bytes, "ogg")
"""
import logging
from typing import Optional

from app.services.asr.base import ASRProvider

logger = logging.getLogger(__name__)

# Mots-clés agricoles : si aucun n'est trouvé dans la transcription,
# un provider secondaire peut être tenté
AGRI_KEYWORDS: frozenset[str] = frozenset({
    "malo", "kaba", "tiga", "bananku", "foro", "sɛnɛ",
    "sanji", "ji", "bana", "gan", "jaba", "woso", "ku",
    "kɔrɔni", "tamati", "mangoro", "wagati", "kalo",
    "nyɔ", "keninge", "kakawo", "soso", "bɛnɛ",
})


class ASRChain:
    """Chaîne de providers ASR avec fallback automatique.

    Respecte le principe Open/Closed : ajouter un provider = l'ajouter
    dans la liste, sans modifier la logique de chaîne.

    Args:
        providers: Liste ordonnée de providers (essayés du premier au dernier).
        agri_fallback: Provider optionnel à tenter si le provider principal
                       ne détecte aucun mot-clé agricole.
    """

    def __init__(
        self,
        providers: list[ASRProvider],
        agri_fallback: Optional[ASRProvider] = None,
    ):
        self._providers = providers
        self._agri_fallback = agri_fallback

    @property
    def providers(self) -> list[ASRProvider]:
        return list(self._providers)

    async def transcribe(
        self,
        audio_bytes: bytes,
        file_extension: str = "ogg",
    ) -> Optional[str]:
        """Transcrit l'audio en essayant chaque provider dans l'ordre.

        Si un provider réussit mais sans mot-clé agricole détecté,
        et qu'un agri_fallback est configuré, tente le fallback.
        """
        result = await self._try_chain(audio_bytes, file_extension)

        if result and self._agri_fallback and self._agri_fallback.is_available():
            if not self._has_agri_keywords(result):
                words_count = len(result.split())
                if words_count >= 3:
                    logger.info(
                        "[ASRChain] Pas de mot agricole détecté → second passage %s",
                        self._agri_fallback.name,
                    )
                    fallback_result = await self._agri_fallback.transcribe(
                        audio_bytes, file_extension,
                    )
                    if fallback_result and self._has_agri_keywords(fallback_result):
                        logger.info(
                            "[ASRChain] Fallback %s a trouvé des mots agricoles",
                            self._agri_fallback.name,
                        )
                        return fallback_result
                    else:
                        logger.info("[ASRChain] Fallback non concluant, on garde le résultat initial")

        return result

    async def _try_chain(
        self,
        audio_bytes: bytes,
        file_extension: str,
    ) -> Optional[str]:
        """Essaie chaque provider dans l'ordre."""
        for provider in self._providers:
            if not provider.is_available():
                logger.debug("[ASRChain] %s non disponible, skip", provider.name)
                continue

            try:
                result = await provider.transcribe(audio_bytes, file_extension)
                if result:
                    logger.info("[ASRChain] %s → '%s'", provider.name, result)
                    return result
                else:
                    logger.warning("[ASRChain] %s → résultat vide", provider.name)
            except Exception as e:
                logger.error("[ASRChain] %s erreur: %s", provider.name, e)

        logger.warning("[ASRChain] Tous les providers ont échoué")
        return None

    @staticmethod
    def _has_agri_keywords(text: str) -> bool:
        """Vérifie si le texte contient au moins un mot-clé agricole."""
        words = set(text.lower().split())
        return bool(words & AGRI_KEYWORDS)
