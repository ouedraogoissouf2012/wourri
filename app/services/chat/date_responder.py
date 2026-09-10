"""WOURI — DateResponder : réponse déterministe « quelle est la date du jour ».

Répond avec la VRAIE date (`datetime.now()`) au lieu de laisser DeepSeek halluciner
une date fausse (ex. « mardi 15 avril 2025 » observé en prod) ou de refuser
(HORS_SUJET → « je ne peux pas t'aider »). Le moteur connaît déjà la date (le
calendrier saisonnier l'utilise) ; ce responder l'expose directement.

Pattern : fonctions module-level, orchestrées par les handlers comme un niveau de
cascade, à l'identique de `meteo_responder` / `culture_zone_responder`.

Dette tracée (ADR-0014, « ne jamais inventer de dioula ») : la date est rendue en
FRANÇAIS (factuel, compréhensible, audio Piper FR). La formulation dioula de la date
viendra avec un locuteur natif.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from app.data.calendrier_agricole import MOIS_FR
from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)

# Intent NLU d'une demande de date (défini dans dictionnaires/nlu_concepts.json,
# required_any: TEMPS_DATE).
DATE_INTENT = "QUESTION_DATE"

JOURS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def is_date_intent(nlu: NLUResult) -> bool:
    """True si l'intent NLU est une demande de date (QUESTION_DATE)."""
    return nlu.intent == DATE_INTENT


def _format_date_fr(now: datetime.datetime) -> str:
    """Formate une date en français : « mercredi 9 septembre 2026 »."""
    return f"{JOURS_FR[now.weekday()]} {now.day} {MOIS_FR[now.month]} {now.year}"


async def build_date_response(
    nlu: NLUResult,
    city: str,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Réponse déterministe à « quelle est la date du jour » : la VRAIE date.

    Rendue en français (la date est toujours disponible → ne renvoie jamais None).
    Corrige à la fois le refus (mode BOTH) et la date hallucinée (mode FR).
    """
    fr = f"Aujourd'hui, nous sommes le {_format_date_fr(datetime.datetime.now())}."

    audio_url = None
    if include_audio:
        from app.services.tts_french import synthesize_french

        audio_url = await synthesize_french(fr)

    logger.info("[DATE] Réponse directe (ville=%s, langue=%s)", city, language.value)
    return ChatResult(
        response=fr,
        city=city,
        language=language.value,
        audio_url=audio_url,
        audio_language="Français" if audio_url else None,
        meta={"intent": nlu.intent, "source": "date"},
    )
