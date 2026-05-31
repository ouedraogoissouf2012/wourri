"""
WOURI — DeepSeekRouter : extraction de `chat_service.py` (refactor P2-09 PR 5/5).

Module qui gere les 2 chemins de fallback vers DeepSeek (LLM externe) :
  - `try_deepseek_dioula()` : reponse FR DeepSeek → traduction NLLB → TTS dioula
  - `try_deepseek_french()` : reponse FR DeepSeek + TTS francais (Edge TTS)

Pattern : fonctions module-level (pas d'etat). Toutes async car DeepSeek
API est I/O bound + traductions/TTS sont async/lourdes.

Refs :
  - Issue parent : #204 Sprint L item P2-09
  - PR precedente : #267 (PR 4/5 IVRSearcher)
  - Pattern source : #262 (PR 1/5 MeteoInjector)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult


logger = logging.getLogger(__name__)


async def try_deepseek_dioula(
    nlu: NLUResult,
    weather_data: dict | None,
    city: str,
    include_audio: bool,
    language: Language,
    user_id: Optional[str],
) -> ChatResult:
    """Fallback DeepSeek pour le dioula : reponse FR → traduction NLLB → TTS.

    Pipeline :
      1. DeepSeek API → reponse FR generee par LLM
      2. Si include_audio : NLLB traduit FR → bambara + TTS MMS-dyu → audio
      3. ChatResult avec response=FR, response_dioula=traduction, audio_url=TTS
    """
    from app.services.deepseek import chat_with_deepseek
    from app.services.tts_dioula import synthesize_dioula

    logger.info("[DeepSeek] fallback dioula (intent=%s)", nlu.intent)

    deepseek_response = await chat_with_deepseek(
        message=nlu.message_for_deepseek,
        weather_data=weather_data,
        language=Language.DIOULA,
        user_id=user_id,
    )

    audio_url = None
    bambara_translated = deepseek_response
    if include_audio:
        audio_url, bambara_translated = await synthesize_dioula(deepseek_response)

    cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
    return ChatResult(
        response=deepseek_response,
        response_dioula=bambara_translated or deepseek_response,
        audio_url=audio_url,
        city=city,
        language=language.value,
        audio_language="Dioula" if audio_url else None,
        meta={"intent": nlu.intent, "cultures": cultures, "source": "deepseek_open"},
    )


async def try_deepseek_french(
    nlu: NLUResult,
    weather_data: dict | None,
    city: str,
    include_audio: bool,
    language: Language,
    user_id: Optional[str],
) -> ChatResult:
    """Chemin francais uniquement via DeepSeek.

    Pas de traduction (deja FR), TTS via Edge TTS francais.
    """
    from app.services.deepseek import chat_with_deepseek
    from app.services.tts_french import synthesize_french

    response_text = await chat_with_deepseek(
        message=nlu.message_for_deepseek,
        weather_data=weather_data,
        language=Language.FRENCH,
        user_id=user_id,
    )

    audio_url = None
    if include_audio:
        audio_url = await synthesize_french(response_text)

    return ChatResult(
        response=response_text,
        audio_url=audio_url,
        city=city,
        language=language.value,
        audio_language="Français" if audio_url else None,
    )
