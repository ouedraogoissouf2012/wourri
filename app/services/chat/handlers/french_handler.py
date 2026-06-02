"""
WOURI — FrenchHandler : chemin francais via DeepSeek direct (ADR-0015 PR 1/4).

Premier handler implementant le Protocol `LanguageHandler`. Extrait de
`app.services.chat.deepseek_router.try_deepseek_french` (refactor P2-09 PR 5/5).

Pipeline :
    1. DeepSeek API genere une reponse FR (cf. system prompt `Language.FRENCH`)
    2. Si include_audio : Piper TTS FR -> audio OGG Opus
    3. ChatResult avec response=FR, audio_url=TTS_FR

Pattern : classe stateless (pas d'etat instance) — l'instance dans
`HANDLERS[Language.FRENCH]` est partagee entre toutes les requetes. Toute
ressource (modele Piper, client httpx DeepSeek) est gerée via singletons
lazy dans les modules importes (`app.services.deepseek`, `app.services.tts_french`).

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #276 (PR 1/4)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)


class FrenchHandler:
    """Handler pour `Language.FRENCH` : DeepSeek FR direct + TTS Piper FR.

    Pas de cascade IVR : le corpus n'a pas de chemin direct FR-seulement
    (les entrees corpus servent au mode dioula/both via traduction NLLB).
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
        """Genere reponse FR via DeepSeek + TTS optionnel.

        Identique a `deepseek_router.try_deepseek_french` mais encapsule
        dans une classe respectant le Protocol `LanguageHandler`.
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
