"""WOURI — CultureZoneResponder : « quelle culture pour ma zone ? » (#509 C2).

Répond de façon DÉTERMINISTE à « quoi cultiver dans ma région » (intent
`QUESTION_GENERALE`) à partir de la zone agro-écologique de la ville
(`zones_agricoles`) + du calendrier (cultures de saison), au lieu de dépendre
de DeepSeek — qui échoue quand le LLM est lent/indisponible (cas démo SODEXAM :
« quelle culture pour ma région » → aucun résultat).

La réponse est rendue en FRANÇAIS pour toutes les langues (FR/DIOULA/BOTH), comme
`date_responder` — un conseil factuel exact vaut mieux que le refus HORS_SUJET
(#543, démo SODEXAM). La formulation DIOULA reste une dette tracée (ADR-0014,
validation native).

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

# Intent DÉDIÉ « quelle culture pour ma zone » (concept DEMANDE_CULTURE_ZONE, #543).
# Traité dans TOUS les handlers (FR + dioula/both).
CULTURE_ZONE_INTENT = "QUESTION_CULTURE_ZONE"

# Intents pris en charge par ce responder :
#   - CULTURE_ZONE_INTENT : l'intent dédié ci-dessus ;
#   - "QUESTION_GENERALE" : fallback historique #511 (culture citée sans intent
#     précis) — pris en charge UNIQUEMENT dans la FrenchHandler, pour ne pas
#     altérer le comportement dioula existant de QUESTION_GENERALE.
CULTURE_ZONE_INTENTS = (CULTURE_ZONE_INTENT, "QUESTION_GENERALE")


def is_culture_zone_intent(nlu: NLUResult) -> bool:
    """True si l'intent relève de « quelle culture pour ma zone » (dédié + fallback #511)."""
    return nlu.intent in CULTURE_ZONE_INTENTS


async def build_culture_zone_response(
    nlu: NLUResult,
    city: str,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Réponse déterministe « cultures adaptées à ta zone », rendue en français.

    Rendue en FRANÇAIS pour TOUTES les langues (FR/DIOULA/BOTH), au même titre que
    `date_responder` : un conseil factuel exact vaut mieux que le refus HORS_SUJET
    (#543). La formulation DIOULA reste une dette tracée (ADR-0014, validation
    native). Renvoie None seulement si la donnée de zone manque (→ fallback DeepSeek
    inchangé).
    """
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
