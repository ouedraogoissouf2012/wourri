"""
WOURI — DioulaHandler : cascade IVR exact → concept → DeepSeek (ADR-0015 PR 2/4).

Deuxieme handler implementant le Protocol `LanguageHandler`. Orchestre la
**cascade 3 niveaux** historique pour le mode dioula :

    Niveau 1 — IVR exact      : match intent + culture dans le corpus
    Niveau 2 — IVR concept    : fallback par concept seul (CULTURE_RIZ, etc.)
    Niveau 3 — DeepSeek dioula : LLM externe + traduction NLLB → TTS MMS-dyu

Chaque niveau peut retourner un `ChatResult` ; si None, le suivant est tente.
La cascade est equivalente strict a la logique historique de
`chat_service.process()` lignes 90-109 (extrait pour OCP + tests isoles).

Pattern : classe stateless. Les fonctions de cascade restent dans leurs
modules dedies (`ivr_searcher`, `deepseek_router`) — DioulaHandler ne fait
que les orchestrer dans le bon ordre. Cela preserve la separation des
responsabilites et garde les tests existants verts.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #277 (PR 2/4)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)


class DioulaHandler:
    """Handler pour `Language.DIOULA` : cascade IVR exact → concept → DeepSeek dioula.

    La cascade preserve la priorite historique :
      1. Si `nlu.intent` existe : tenter IVR exact (intent + culture).
      2. Sinon ou si IVR exact echoue : tenter IVR concept (par culture seule).
      2.5. Question météo PURE (`QUESTION_METEO_AGRICOLE`, issue #355 T4) :
           réponse construite depuis Open-Meteo + templates dioula validés,
           au lieu du fallback DeepSeek. Ignoré pour tout autre intent.
      3. Fallback final : DeepSeek + traduction NLLB FR→BAM + TTS dioula.

    Note : `try_ivr_concept` peut declencher `clarify_missing_culture` quand une
    action agricole est detectee sans culture (fix #94 — pas de fallback silencieux
    vers CULTURE_MAIS). Ce comportement est preserve.
    """

    async def process(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        """Orchestre la cascade 3 niveaux. Retourne TOUJOURS un ChatResult."""
        from app.services.chat.deepseek_router import try_deepseek_dioula
        from app.services.chat.ivr_searcher import try_ivr_concept, try_ivr_exact
        from app.services.chat.meteo_responder import (
            build_meteo_response,
            is_pure_weather_intent,
        )

        # Niveau 1 : IVR exact (uniquement si intent NLU detecte)
        if nlu.intent:
            result = await try_ivr_exact(
                nlu=nlu,
                city=city,
                weather_data=weather_data,
                include_audio=include_audio,
                language=language,
            )
            if result is not None:
                return result

        # Niveau 2 : IVR concept (par culture seule)
        # Peut retourner une clarification si action sans culture (fix #94).
        result = await try_ivr_concept(
            nlu=nlu,
            city=city,
            include_audio=include_audio,
            language=language,
        )
        if result is not None:
            return result

        # Niveau 2.5 : question météo PURE (issue #355 T4). Répondre depuis la
        # prévision/météo construite (dioula validé, weather_conditions) plutôt
        # que d'inventer du dioula via DeepSeek+NLLB. Placé APRÈS l'IVR : quand
        # le corpus météo natif (T5) existera, try_ivr_exact gagnera
        # (source=ivr_exact, critère de succès #355) sans re-toucher ce routage.
        if is_pure_weather_intent(nlu):
            result = await build_meteo_response(
                nlu=nlu,
                weather_data=weather_data,
                city=city,
                include_audio=include_audio,
                language=language,
            )
            if result is not None:
                return result

        # Niveau 3 : DeepSeek dioula + traduction NLLB + TTS
        return await try_deepseek_dioula(
            nlu=nlu,
            weather_data=weather_data,
            city=city,
            include_audio=include_audio,
            language=language,
            user_id=user_id,
        )
