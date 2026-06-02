"""
WOURI — EnglishHandler : DeepSeek direct + Piper TTS EN (ADR-0015 PR 4/4).

Quatrieme handler implementant le Protocol `LanguageHandler`. **Pure extension** :
aucune modification du code des PRs 1-3, juste un nouveau fichier + 1 entree
dans `HANDLERS`. Valide que le pattern Strategy installe en PRs 1-3 fonctionne.

## Pipeline (pas de cascade IVR)

Le corpus IVR contient uniquement des entrees bambara/francais (162 entrees,
adaptees agriculteurs CI/Mali). L'utiliser pour des requetes anglaises serait
soit inutile (pas de match) soit incorrect (traduction machine FR→EN de
qualite degradee). On bypasse donc la cascade :

    DeepSeek direct EN (prompt agricole EN adapte)
        + Piper TTS EN (en_US-amy-medium) si include_audio

Cette decision est explicite dans l'ADR-0015 §"Vrai support EN agricole ou
passthrough ?" : reserve a un futur ADR-0016 si export commercial confirme.

## Use case : demos investisseurs

Un investisseur teste le bot en EN. Il ne mesure pas les subtilites du
dioula ivoirien — il evalue si le bot **comprend** et **repond** en EN
de maniere coherente. DeepSeek natif EN + TTS de qualite suffit largement.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #279 (PR 4/4)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)


class EnglishHandler:
    """Handler pour `Language.ENGLISH` : DeepSeek direct EN + Piper TTS EN.

    Pas de cascade IVR (corpus = BAM/FR uniquement). Reponse generee
    entierement par DeepSeek avec le system prompt ENGLISH_PROMPT.
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
        """Pipeline EN : DeepSeek direct → TTS EN si include_audio.

        Note : `nlu.intent` et `nlu.concepts` peuvent etre None/vide pour les
        requetes EN car le NLU bambara/dioula ne s'applique pas. C'est OK,
        DeepSeek gere le sens de la requete sans pre-extraction NLU.
        """
        from app.services.deepseek import chat_with_deepseek
        from app.services.tts_english import synthesize_english

        logger.info("[EnglishHandler] DeepSeek direct EN (intent=%s)", nlu.intent)

        response_text = await chat_with_deepseek(
            message=nlu.message_for_deepseek,
            weather_data=weather_data,
            language=Language.ENGLISH,
            user_id=user_id,
        )

        audio_url = None
        if include_audio:
            audio_url = await synthesize_english(response_text)

        return ChatResult(
            response=response_text,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="English" if audio_url else None,
            meta={"source": "deepseek_english"},
        )
