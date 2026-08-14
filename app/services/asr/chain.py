"""
WOURI - ASRChain : chaîne de fallback configurable entre providers ASR.

La chaîne essaie chaque provider dans l'ordre jusqu'à obtenir un résultat.
Optionnel : filtre par mots-clés agricoles pour déclencher un second passage.

Usage :
    from app.services.asr import get_asr_chain
    chain = get_asr_chain()
    text = await chain.transcribe(audio_bytes, "ogg")
"""
import asyncio
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

        #301 : l'audio est converti en WAV 16kHz UNE seule fois en amont, puis
        le WAV prêt est partagé entre tous les providers (et l'agri_fallback) via
        `ASRProvider.transcribe_wav`. Avant, chaque provider reconvertissait —
        2 à 4 conversions ffmpeg du même audio par requête.

        Si un provider réussit mais sans mot-clé agricole détecté,
        et qu'un agri_fallback est configuré, tente le fallback.
        """
        from app.services.asr.audio_utils import prepared_wav_16k

        with prepared_wav_16k(audio_bytes, file_extension, "ASRChain") as wav_path:
            if wav_path is None:
                # Conversion échouée : rien à transcrire.
                return None
            return await self._transcribe_wav(wav_path)

    async def _transcribe_wav(self, wav_path: str) -> Optional[str]:
        """Orchestration sur un WAV 16k déjà converti (cascade + agri_fallback)."""
        from app.services.asr_normalizer import normalize_asr_output

        result, winner = await self._try_chain(wav_path)

        # Normalisation post-ASR (corrections exactes + fuzzy matching NLU)
        if result:
            normalized = normalize_asr_output(result)
            if normalized != result:
                logger.info("[ASRChain] Normalisé: '%s' → '%s'", result, normalized)
                result = normalized

        # Second passage agricole : inutile si le résultat vient déjà de
        # l'agri_fallback lui-même (re-transcrire avec le même modèle donnerait
        # le même texte pour ~45s de CPU — cas réel depuis la réparation #358
        # où MMS-dyu est à la fois provider principal effectif et fallback).
        if (
            result
            and self._agri_fallback
            and winner is not self._agri_fallback
            and self._agri_fallback.is_available()
        ):
            if not self._has_agri_keywords(result):
                words_count = len(result.split())
                if words_count >= 3:
                    logger.info(
                        "[ASRChain] Pas de mot agricole détecté → second passage %s",
                        self._agri_fallback.name,
                    )
                    # Réutilise le MÊME WAV déjà converti (#301) — pas de
                    # reconversion pour le second passage.
                    fallback_result = await asyncio.to_thread(
                        self._agri_fallback.transcribe_wav, wav_path,
                    )
                    if fallback_result:
                        # Même normalisation que le résultat principal (revue
                        # #358 F1 : le texte du fallback partait brut — les
                        # corrections exactes/fuzzy ne s'y appliquaient pas,
                        # et le check agricole ratait les formes corrigibles).
                        fallback_result = normalize_asr_output(fallback_result)
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
        wav_path: str,
    ) -> tuple[Optional[str], Optional[ASRProvider]]:
        """Essaie chaque provider dans l'ordre sur un WAV 16k déjà converti.

        Retourne (résultat, provider gagnant) — le provider sert à éviter un
        second passage agricole redondant quand le gagnant est déjà
        l'agri_fallback.
        """
        for provider in self._providers:
            if not provider.is_available():
                logger.debug("[ASRChain] %s non disponible, skip", provider.name)
                continue

            try:
                result = await asyncio.to_thread(provider.transcribe_wav, wav_path)
                if result:
                    logger.info("[ASRChain] %s → '%s'", provider.name, result)
                    return result, provider
                else:
                    logger.warning("[ASRChain] %s → résultat vide", provider.name)
            except Exception as e:
                logger.error("[ASRChain] %s erreur: %s", provider.name, e)

        logger.warning("[ASRChain] Tous les providers ont échoué")
        return None, None

    @staticmethod
    def _has_agri_keywords(text: str) -> bool:
        """Vérifie si le texte contient au moins un mot-clé agricole."""
        words = set(text.lower().split())
        return bool(words & AGRI_KEYWORDS)
