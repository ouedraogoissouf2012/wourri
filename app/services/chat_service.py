"""
WOURI - ChatService : orchestrateur unique pour le pipeline de chat.

Responsabilité unique (SRP) : coordonne NLU → IVR → DeepSeek → TTS
pour produire une réponse complète à partir d'un message utilisateur.

Le routeur chat.py ne fait que valider l'input et retourner le résultat.
"""
import asyncio
import logging
from typing import Optional

from app.models.schemas import Language
from app.config import get_settings
from app.data.calendrier_agricole import get_conseil_saisonnier
# Note (PR 2/5 refactor #204) : `IVORIAN_CITIES` n'est plus importe ici —
# la detection de ville est deleguee a `app/services/chat/city_detector.py`
# qui importe IVORIAN_CITIES directement depuis app.data.cities.

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Data classes pour les résultats intermédiaires
# ---------------------------------------------------------------------------
#
# Refactor P2-09 PR 3/5 : NLUResult extrait vers app/services/chat/nlu_preprocessor.py
# (defini la-bas car c'est le type de retour de preprocess_nlu()). Re-exporte
# ici pour back-compat (tests + autres modules qui font
# `from app.services.chat_service import NLUResult`).
from app.services.chat.nlu_preprocessor import NLUResult  # noqa: F401


# ChatResult deplace vers app/services/chat/_types.py (PR 4/5 refactor #204).
# Re-export pour back-compat (tests + autres modules qui font
# `from app.services.chat_service import ChatResult`).
from app.services.chat._types import ChatResult  # noqa: F401


# ---------------------------------------------------------------------------
# Labels pour enrichissement DeepSeek
# ---------------------------------------------------------------------------
#
# Refactor P2-09 PR 3/5 : CULTURE_LABELS / ANIMAL_LABELS / ACTION_TO_INTENT
# extraits vers app/services/chat/nlu_preprocessor.py. Re-exportes ici pour
# back-compat (le _ a ete retire = export public, conforme PEP-8).
from app.services.chat.nlu_preprocessor import (  # noqa: F401
    CULTURE_LABELS as _CULTURE_LABELS,
    ANIMAL_LABELS as _ANIMAL_LABELS,
    ACTION_TO_INTENT as _ACTION_TO_INTENT,
)


class ChatService:
    """Orchestrateur du pipeline de chat Wourri.

    Usage :
        service = ChatService()
        result = await service.process(message, city, language, bambara_text, include_audio)
    """

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def process(
        self,
        message: str,
        city: str = "Abidjan",
        language: Language = Language.BOTH,
        bambara_text: Optional[str] = None,
        include_audio: bool = True,
        user_id: Optional[str] = None,
    ) -> ChatResult:
        """Pipeline complet : message → NLU → handler[language] → résultat.

        Strategy Pattern (ADR-0015 PR 3/4) : dispatcher pur sur le registre
        `HANDLERS`. Chaque langue (FRENCH, DIOULA, BOTH, futurement ENGLISH)
        a son propre handler implementant le Protocol `LanguageHandler`.

        Ajouter une langue future = 1 nouveau handler + 1 entree dans HANDLERS.
        **Zero modification** de cette methode (OCP strict).
        """
        try:
            # Etape 1 : detection ville
            detected_city = self._detect_city(message)
            city = detected_city or city

            # Etape 2 : NLU preprocessing
            nlu = self._preprocess_nlu(message, bambara_text, language)

            # Etape 3 : meteo
            from app.services.weather import get_weather
            weather_data = await get_weather(city)

            # Etape 4 : dispatch via Strategy Pattern
            from app.services.chat.handlers import HANDLERS
            handler = HANDLERS[language]
            return await handler.process(
                nlu=nlu,
                weather_data=weather_data,
                city=city,
                include_audio=include_audio,
                language=language,
                user_id=user_id,
            )

        except Exception as e:
            logger.error("Erreur ChatService: %s", e, exc_info=True)
            return ChatResult(
                response="Désolé, je rencontre des problèmes de connexion. "
                         "Vérifiez votre connexion internet et réessayez.",
                city=city,
                language=language.value,
            )

    # ------------------------------------------------------------------
    # Étape 1 : Détection de ville
    #
    # Refactor P2-09 PR 2/5 (Sprint L #204) : logique extraite vers
    # app/services/chat/city_detector.py (module pur). La methode
    # _detect_city devient un wrapper 1-line pour preserver l'API
    # publique de ChatService (utilisee par process() ligne 102).
    # ------------------------------------------------------------------

    def _detect_city(self, message: str) -> Optional[str]:
        """Wrapper compat (PR 2/5) : delegue a city_detector.detect_city()."""
        from app.services.chat.city_detector import detect_city
        return detect_city(message)

    # ------------------------------------------------------------------
    # Étape 2 : NLU preprocessing
    #
    # Refactor P2-09 PR 3/5 (Sprint L #204) : logique extraite vers
    # app/services/chat/nlu_preprocessor.py (module pur). Wrappers 1-line
    # ci-dessous pour preserver l'API publique de ChatService.
    # ------------------------------------------------------------------

    def _preprocess_nlu(
        self,
        message: str,
        bambara_text: Optional[str],
        language: Language,
    ) -> NLUResult:
        """Wrapper compat (PR 3/5) : delegue a nlu_preprocessor.preprocess_nlu()."""
        from app.services.chat.nlu_preprocessor import preprocess_nlu
        return preprocess_nlu(message, bambara_text, language)

    def _enrich_for_deepseek(self, french_sentence: str, concepts: dict) -> str:
        """Wrapper compat (PR 3/5) : delegue a nlu_preprocessor.enrich_for_deepseek()."""
        from app.services.chat.nlu_preprocessor import enrich_for_deepseek
        return enrich_for_deepseek(french_sentence, concepts)

    # ------------------------------------------------------------------
    # Étapes 3-4 : Recherche IVR (PR 4/5 refactor P2-09 Sprint L #204)
    #
    # 4 méthodes IVR extraites vers app/services/chat/ivr_searcher.py
    # (~240 lignes module pur). Wrappers 1-line ci-dessous preservent
    # l'API publique de ChatService pour minimiser le changement dans
    # process() ligne 113-127.
    # ------------------------------------------------------------------

    async def _try_ivr_exact(
        self,
        nlu: NLUResult,
        city: str,
        weather_data: dict | None,
        include_audio: bool,
        language: Language,
    ) -> Optional[ChatResult]:
        """Wrapper compat (PR 4/5) : delegue a ivr_searcher.try_ivr_exact()."""
        from app.services.chat.ivr_searcher import try_ivr_exact
        return await try_ivr_exact(nlu, city, weather_data, include_audio, language)

    async def _try_ivr_concept(
        self,
        nlu: NLUResult,
        city: str,
        include_audio: bool,
        language: Language,
    ) -> Optional[ChatResult]:
        """Wrapper compat (PR 4/5) : delegue a ivr_searcher.try_ivr_concept()."""
        from app.services.chat.ivr_searcher import try_ivr_concept
        return await try_ivr_concept(nlu, city, include_audio, language)

    async def _clarify_missing_culture(
        self,
        city: str,
        include_audio: bool,
        language: Language,
        nlu: NLUResult,
    ) -> ChatResult:
        """Wrapper compat (PR 4/5) : delegue a ivr_searcher.clarify_missing_culture()."""
        from app.services.chat.ivr_searcher import clarify_missing_culture
        return await clarify_missing_culture(city, include_audio, language, nlu)

    async def _search_ivr_by_concept(self, concepts: dict) -> Optional[dict]:
        """Wrapper compat (PR 4/5) : delegue a ivr_searcher.search_ivr_by_concept()."""
        from app.services.chat.ivr_searcher import search_ivr_by_concept
        return await search_ivr_by_concept(concepts)

    # ------------------------------------------------------------------
    # Étapes 5-6 : Fallback DeepSeek (PR 5/5 refactor P2-09 Sprint L #204)
    #
    # 2 méthodes DeepSeek extraites vers app/services/chat/deepseek_router.py
    # (~105 lignes module pur). Wrappers 1-line preservent l'API publique.
    # ------------------------------------------------------------------

    async def _try_deepseek_dioula(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        """Wrapper compat (PR 5/5) : delegue a deepseek_router.try_deepseek_dioula()."""
        from app.services.chat.deepseek_router import try_deepseek_dioula
        return await try_deepseek_dioula(
            nlu, weather_data, city, include_audio, language, user_id,
        )

    async def _try_deepseek_french(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        """Wrapper compat (PR 5/5) : delegue a deepseek_router.try_deepseek_french()."""
        from app.services.chat.deepseek_router import try_deepseek_french
        return await try_deepseek_french(
            nlu, weather_data, city, include_audio, language, user_id,
        )

    # ------------------------------------------------------------------
    # Helpers privés
    #
    # Refactor P2-09 PR 1 (Sprint L #204) : _inject_meteo + _build_meteo_bambara
    # extraits vers app/services/chat/meteo_injector.py (module pur, fonctions
    # module-level). Le seul appelant (_try_ivr_exact) importe directement
    # `inject_meteo` depuis le module.
    # ------------------------------------------------------------------

    async def _synthesize_dioula(self, text: str) -> Optional[str]:
        """Synthétise du texte dioula en audio (async wrapper)."""
        from app.services.tts_dioula import synthesize_dioula_text
        return await asyncio.to_thread(synthesize_dioula_text, text)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Retourne le ChatService singleton."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
