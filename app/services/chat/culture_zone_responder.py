"""WOURI — CultureZoneResponder : « quelle culture pour ma zone ? » (#509 C2).

Répond de façon DÉTERMINISTE à « quoi cultiver dans ma région » (intent
`QUESTION_GENERALE`) à partir de la zone agro-écologique de la ville
(`zones_agricoles`) + du calendrier (cultures de saison), au lieu de dépendre
de DeepSeek — qui échoue quand le LLM est lent/indisponible (cas démo SODEXAM :
« quelle culture pour ma région » → aucun résultat).

Texte FR (contrat both = texte FR lisible) + audio dans la langue : Piper FR en
mode FRANÇAIS, MMS-dyu en dioula/both à partir d'une phrase dioula VALIDÉE
NATIVEMENT (#545 ; gabarit « {Ville} la, aw ye {cultures} sɛnɛ. »). Patron
identique à `meteo_responder`. Repli audio FR si une culture n'a pas de nom dioula
validé (règle §14 GRAMMAIRE : ne jamais perdre l'information présente dans le FR).

Pattern : fonctions module-level, orchestrées par les handlers comme un niveau
de cascade, à l'identique de `meteo_responder`.
"""
from __future__ import annotations

import asyncio
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


# Noms dioula des cultures — validés : §12 GRAMMAIRE_DIOULA_REGLES.md (multi-sources)
# + validation native 2026-09-22 (#545) pour sɔmɔ / mana su / ntentulu. Tons
# simplifiés pour le TTS MMS-dyu (§13.5 : « malo » pas « màlo »).
NOMS_CULTURES_DYU = {
    "CULTURE_RIZ": "malo",
    "CULTURE_MAIS": "kaba",
    "CULTURE_MIL": "nyɔ",
    "CULTURE_ARACHIDE": "tiga",
    "CULTURE_IGNAME": "ku",
    "CULTURE_MANIOC": "bananku",
    "CULTURE_COTON": "kɔrɔni",
    "CULTURE_SESAME": "bɛnɛ",
    "CULTURE_CACAO": "kakawo",
    "CULTURE_CAFE": "kafe",
    "CULTURE_BANANE": "baranda",
    "CULTURE_ANACARDE": "sɔmɔ",           # validation native 2026-09-22 (#545)
    "CULTURE_HEVEA": "mana su",            # validation native 2026-09-22 (#545)
    "CULTURE_PALMIER_HUILE": "ntentulu",   # validation native 2026-09-22 (#545)
}

# Ordre d'énumération (vivriers d'abord, cultures de rente ensuite) — reproduit
# l'ordre de la phrase validée nativement (#545 : malo, kaba, tiga, bananku, ku,
# kɔrɔni, sɔmɔ) et le rend cohérent pour toutes les zones, en FR comme en dioula.
CULTURE_ORDER = {
    "CULTURE_RIZ": 1, "CULTURE_MAIS": 2, "CULTURE_MIL": 3,
    "CULTURE_ARACHIDE": 4, "CULTURE_SESAME": 5,
    "CULTURE_MANIOC": 6, "CULTURE_IGNAME": 7,
    "CULTURE_BANANE": 8,
    "CULTURE_COTON": 9, "CULTURE_ANACARDE": 10,
    "CULTURE_CACAO": 11, "CULTURE_CAFE": 12,
    "CULTURE_HEVEA": 13, "CULTURE_PALMIER_HUILE": 14,
}


def _ordonner(concept_keys: list) -> list:
    """Trie les cultures dans l'ordre canonique (vivriers → rente, #545) — même
    ordre en FR et en dioula. Une culture hors liste est rejetée en fin."""
    return sorted(concept_keys, key=lambda c: CULTURE_ORDER.get(c, 99))


def _liste_dyu(concept_keys: list) -> Optional[str]:
    """Liste dioula « a, b, c ni d » (connecteur `ni` validé nativement, #545).

    Renvoie None si une culture n'a pas de nom dioula validé → repli audio FR
    (règle §14 : ne jamais supprimer une information présente dans le texte FR).
    """
    noms = [NOMS_CULTURES_DYU.get(c) for c in concept_keys]
    if not noms or any(n is None for n in noms):
        return None
    if len(noms) == 1:
        return noms[0]
    return ", ".join(noms[:-1]) + " ni " + noms[-1]


def _build_culture_zone_dioula(
    city: str, cultures: list, saison_keys: list
) -> Optional[str]:
    """Phrase dioula validée nativement (#545, gabarit figé) :

        {Ville} la, aw ye {cultures} sɛnɛ.
        Sisan, aw bɛ se ka {cultures_saison} sɛnɛ.

    SOV (verbe `sɛnɛ` en fin), impératif pluriel `aw ye` (§3), locatif `la` (§4),
    `se ka` = pouvoir (§5). Renvoie None si une culture de zone n'a pas de nom
    dioula validé (→ repli audio FR).
    """
    liste = _liste_dyu(cultures)
    if liste is None:
        return None
    phrase = f"{city} la, aw ye {liste} sɛnɛ."
    liste_saison = _liste_dyu(saison_keys) if saison_keys else None
    if liste_saison:
        phrase += f" Sisan, aw bɛ se ka {liste_saison} sɛnɛ."
    return phrase


async def _synthesize_dioula(text: str) -> Optional[str]:
    """Wrapper async pour la synthèse TTS dioula MMS-dyu (patron `meteo_responder`).

    Import paresseux (module TTS lourd) ; `tts_dioula.py` est APPELÉ, jamais modifié.
    """
    from app.services.tts_dioula import synthesize_dioula_text

    return await asyncio.to_thread(synthesize_dioula_text, text)


async def build_culture_zone_response(
    nlu: NLUResult,
    city: str,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Réponse déterministe « cultures adaptées à ta zone ».

    Texte FR (contrat #167 : `response` reste le FR lisible) + audio dans la langue :
    Piper FR en mode FRANÇAIS, MMS-dyu en dioula/both à partir de la phrase dioula
    validée nativement (#545). Repli audio FR si le dioula est indisponible (culture
    sans nom validé). Renvoie None seulement si la donnée de zone manque (→ fallback
    DeepSeek inchangé).
    """
    from app.data.calendrier_agricole import NOMS_CULTURES_FR, get_cultures_du_mois
    from app.data.zones_agricoles import ZONES, get_cultures_zone, get_zone_for_city

    cultures = _ordonner(get_cultures_zone(city))
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
    saison = sorted(saison, key=lambda c: CULTURE_ORDER.get(c.get("culture_key"), 99))
    saison_keys = [c.get("culture_key") for c in saison]
    if saison:
        noms_saison = ", ".join(c["fr"] for c in saison)
        phrase_saison = f" En ce moment, c'est une bonne période pour : {noms_saison}."

    fr = f"À {city}, en {label.lower()}, tu peux cultiver : {liste}.{phrase_saison}"

    # Texte dioula validé nativement (#545) — sert l'audio MMS-dyu en dioula/both.
    dyu = _build_culture_zone_dioula(city, cultures, saison_keys)

    # Audio dans la langue demandée (patron meteo_responder) : Piper FR en FRANÇAIS
    # ou si le dioula manque ; MMS-dyu en dioula/both sur la phrase validée.
    audio_url = None
    audio_lang = None
    if include_audio:
        if language == Language.FRENCH or dyu is None:
            from app.services.tts_french import synthesize_french

            audio_url = await synthesize_french(fr)
            audio_lang = "Français" if audio_url else None
        else:
            audio_url = await _synthesize_dioula(dyu)
            audio_lang = "Dioula" if audio_url else None

    logger.info(
        "[CULTURE-ZONE] Réponse directe (ville=%s, zone=%s, audio=%s)",
        city, zone_id, audio_lang,
    )
    return ChatResult(
        response=fr,
        response_dioula=dyu,
        city=city,
        language=language.value,
        audio_url=audio_url,
        audio_language=audio_lang,
        meta={"intent": nlu.intent, "source": "culture_zone"},
    )
