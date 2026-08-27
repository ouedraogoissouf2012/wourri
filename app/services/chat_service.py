"""
WOURI - ChatService : orchestrateur unique pour le pipeline de chat.

Responsabilité unique (SRP) : coordonne NLU → IVR → DeepSeek → TTS
pour produire une réponse complète à partir d'un message utilisateur.

Le routeur chat.py ne fait que valider l'input et retourner le résultat.

La cascade elle-même n'est plus ici : elle vit dans `app/services/chat/`
(modules purs extraits par le refactor P2-09 #204) et dans
`app/services/chat/handlers/` (Strategy Pattern, ADR-0015). Ce module ne garde
que le dispatcher `process()`, le helper `_synthesize_dioula` (conservé pour
les appelants historiques — les modules de la cascade ont leur propre copie
module-level, dupliquée pour rompre un cycle d'import) et le singleton.

Les 9 méthodes « wrapper compat » qui ne faisaient que déléguer à ces modules
ont été retirées (#495) : elles donnaient l'illusion que la cascade était ici.
Les appelants importent désormais les modules cibles directement — p. ex.
`from app.services.chat.ivr_searcher import try_ivr_exact`.
"""
import asyncio
import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat.city_detector import detect_city
from app.services.chat.nlu_preprocessor import preprocess_nlu
from app.services.deepseek import DeepSeekUnavailableError

# ---------------------------------------------------------------------------
# Re-exports de compatibilité
# ---------------------------------------------------------------------------
#
# Contrairement aux wrappers retirés en #495, ce sont des alias de TYPE et de
# données — aucune logique masquée. Ils restent importés par des tests et des
# modules externes via `from app.services.chat_service import ...`.
#
# NLUResult est défini dans nlu_preprocessor.py (convention « type de retour
# avec sa fonction »). ChatResult est défini dans chat/_types.py pour rompre le
# cycle d'import chat_service → ivr_searcher → ChatResult (cf. son docstring).
from app.services.chat._types import ChatResult  # noqa: F401
from app.services.chat.nlu_preprocessor import NLUResult  # noqa: F401

# CULTURE_LABELS / ANIMAL_LABELS / ACTION_TO_INTENT extraits vers
# nlu_preprocessor.py (PR 3/5 refactor P2-09). Le `_` y a été retiré (export
# public, conforme PEP-8) ; il est conservé ici pour les appelants historiques.
from app.services.chat.nlu_preprocessor import (  # noqa: F401
    ACTION_TO_INTENT as _ACTION_TO_INTENT,
    ANIMAL_LABELS as _ANIMAL_LABELS,
    CULTURE_LABELS as _CULTURE_LABELS,
)

logger = logging.getLogger(__name__)


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
            detected_city = detect_city(message)
            city = detected_city or city

            # Etape 2 : NLU preprocessing
            nlu = preprocess_nlu(message, bambara_text, language)

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

        except DeepSeekUnavailableError:
            # DeepSeek down : propager → FastAPI 500 → le whatsapp-server
            # enregistre l'échec (circuit breaker) et envoie l'audio d'excuse
            # dans la langue de l'utilisateur. Avant ce re-raise, le catch
            # générique ci-dessous renvoyait un texte FR en HTTP 200 : le
            # breaker ne s'ouvrait jamais et le mode dioula vocalisait le
            # message d'erreur (audit 2026-07-21).
            raise
        except Exception as e:
            logger.error("Erreur ChatService: %s", e, exc_info=True)
            return ChatResult(
                response="Désolé, je rencontre des problèmes de connexion. "
                         "Vérifiez votre connexion internet et réessayez.",
                city=city,
                language=language.value,
            )

    # ------------------------------------------------------------------
    # Helper privé
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
