"""WOURI — MeteoResponder : réponse météo directe (issue #355 T4).

Route les questions météo PURES (intent `QUESTION_METEO_AGRICOLE`) vers une
réponse construite à partir des données Open-Meteo + des templates dioula
validés nativement (`weather_conditions`, ADR-0014), au lieu du fallback
DeepSeek+NLLB (qui invente du dioula hors vocabulaire validé et raisonne sur
la météo actuelle, jamais la prévision).

Deux fenêtres temporelles :
  - « demain » (concept `TEMPS_DEMAIN` présent) → prévision J+1 via
    `weather.get_weather_forecast_tomorrow` + `meteo_injector.build_meteo_prevision`.
  - sinon → météo actuelle via `meteo_injector.build_meteo_bambara`
    (données déjà chargées en amont par `ChatService.process`).

Dégradation gracieuse : si la donnée météo est indisponible, renvoie None →
la cascade `DioulaHandler` retombe sur DeepSeek.

Pattern : fonctions module-level (pas d'état), orchestrées par `DioulaHandler`
comme un niveau de cascade, à l'identique de `ivr_searcher` / `deepseek_router`.

Ref : issue #355 (T3 = build_meteo_prevision, T4 = routage ci-dessous).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)

# Intent NLU d'une question météo « pure » (météo/saison sans culture précise).
# Défini dans dictionnaires/nlu_concepts.json (required_any : TEMPS_SAISON_PLUIE
# / TEMPS_SAISON_SECHE / TEMPS_METEO).
PURE_WEATHER_INTENT = "QUESTION_METEO_AGRICOLE"


def is_pure_weather_intent(nlu: NLUResult) -> bool:
    """True si l'intent NLU est une question météo pure (sans culture)."""
    return nlu.intent == PURE_WEATHER_INTENT


async def _synthesize_dioula(text: str) -> Optional[str]:
    """Wrapper async pour la synthèse TTS dioula.

    Dupliqué à l'identique de `ivr_searcher._synthesize_dioula` /
    `chat_service._synthesize_dioula` pour éviter un import circulaire
    (le module TTS est lourd et importé paresseusement).
    """
    from app.services.tts_dioula import synthesize_dioula_text
    return await asyncio.to_thread(synthesize_dioula_text, text)


async def build_meteo_response(
    nlu: NLUResult,
    weather_data: dict | None,
    city: str,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Construit la réponse à une question météo pure (issue #355 T4).

    Choisit prévision J+1 vs météo actuelle selon la présence du concept
    `TEMPS_DEMAIN`. Renvoie None si la donnée météo requise est indisponible
    (→ fallback DeepSeek assuré par l'appelant).
    """
    from app.services.chat.meteo_injector import (
        build_meteo_bambara,
        build_meteo_prevision,
    )

    if "TEMPS_DEMAIN" in nlu.concepts:
        from app.services.weather import get_weather_forecast_tomorrow

        forecast = await get_weather_forecast_tomorrow(city)
        if not forecast:
            logger.info("[MÉTÉO] Prévision J+1 indisponible pour %s → fallback", city)
            return None
        bam, fr = build_meteo_prevision(forecast, city)
        source = "meteo_prevision"
    else:
        if not weather_data:
            logger.info("[MÉTÉO] Météo actuelle indisponible pour %s → fallback", city)
            return None
        bam, fr = build_meteo_bambara(weather_data, city)
        source = "meteo_actuel"

    audio_url = None
    if include_audio:
        audio_url = await _synthesize_dioula(bam)

    logger.info("[MÉTÉO] Réponse directe (source=%s, ville=%s)", source, city)
    return ChatResult(
        # response = FR par contrat (#167) ; fallback bam si FR vide (garde-fou).
        response=fr or bam,
        response_dioula=bam,
        audio_url=audio_url,
        city=city,
        language=language.value,
        audio_language="Dioula" if audio_url else None,
        meta={"intent": nlu.intent, "source": source},
    )
