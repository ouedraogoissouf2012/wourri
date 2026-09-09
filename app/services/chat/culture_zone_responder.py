"""WOURI — CultureZoneResponder : « quelle culture pour ma zone ? » (#509 C2).

Répond de façon DÉTERMINISTE à « quoi cultiver dans ma région » (intent
`QUESTION_GENERALE`) à partir de la zone agro-écologique de la ville
(`zones_agricoles`) + du calendrier (cultures de saison), au lieu de dépendre
de DeepSeek — qui échoue quand le LLM est lent/indisponible (cas démo SODEXAM :
« quelle culture pour ma région » → aucun résultat).

Le français est servi maintenant. La version DIOULA nécessite une validation
native de la formulation (ADR-0014) → renvoie None pour dioula/both en attendant
(le fallback DeepSeek reste alors inchangé).

Pattern : fonctions module-level, orchestrées par les handlers comme un niveau
de cascade, à l'identique de `meteo_responder`.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)

# Fallback agricole « quoi cultiver » sans culture précise (cf. intent_classifier :
# QUESTION_GENERALE est l'intent par défaut ; ex. « mun ka kan ka sɛnɛ », « quoi
# cultiver ici »).
CULTURE_ZONE_INTENT = "QUESTION_GENERALE"


def is_culture_zone_intent(nlu: NLUResult) -> bool:
    """True si l'intent est le fallback « quoi cultiver » (QUESTION_GENERALE)."""
    return nlu.intent == CULTURE_ZONE_INTENT


async def build_culture_zone_response(
    nlu: NLUResult,
    city: str,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Réponse déterministe « cultures adaptées à ta zone » (FR).

    Renvoie None si la donnée manque (→ fallback DeepSeek) ou si la langue n'est
    pas le français (formulation dioula à valider nativement, ADR-0014).
    """
    # Dioula/both : formulation dioula à valider nativement → fallback DeepSeek.
    if language != Language.FRENCH:
        return None

    from app.data.calendrier_agricole import NOMS_CULTURES_FR, get_cultures_du_mois
    from app.data.zones_agricoles import ZONES, get_cultures_zone, get_zone_for_city

    cultures = get_cultures_zone(city)
    if not cultures:
        return None

    zone_id = get_zone_for_city(city)
    label = ZONES.get(zone_id, {}).get("label_fr", "ta région")
    liste = ", ".join(NOMS_CULTURES_FR.get(c, c) for c in cultures)

    # Cultures de saison (plantation/entretien ce mois-ci) — priorisation utile.
    phrase_saison = ""
    try:
        saison = get_cultures_du_mois(city)
    except Exception:
        saison = []
    if saison:
        noms_saison = ", ".join(c["fr"] for c in saison)
        phrase_saison = f" En ce moment, c'est une bonne période pour : {noms_saison}."

    fr = f"À {city}, en {label.lower()}, tu peux cultiver : {liste}.{phrase_saison}"

    audio_url = None
    if include_audio:
        from app.services.tts_french import synthesize_french

        audio_url = await synthesize_french(fr)

    logger.info("[CULTURE-ZONE] Réponse directe (ville=%s, zone=%s)", city, zone_id)
    return ChatResult(
        response=fr,
        city=city,
        language=language.value,
        audio_url=audio_url,
        audio_language="Français" if audio_url else None,
        meta={"intent": nlu.intent, "source": "culture_zone"},
    )
