"""
WOURI — IVRSearcher : extraction de `chat_service.py` (refactor P2-09 PR 4/5).

Module qui gere la cascade IVR (Interactive Voice Response = corpus pre-redige
par culture/intent) :
  - `try_ivr_exact()` : niveau 1, match exact intent + culture
  - `try_ivr_concept()` : niveau 2, fallback par concept seul
  - `clarify_missing_culture()` : action agricole sans culture → demande clarif
  - `search_ivr_by_concept()` : utilitaire interne pour try_ivr_concept

Pattern : fonctions module-level (pas de classe car aucun etat persistant).
Toutes les fonctions sont async car la facade `corpus_facade` utilise
`asyncio.to_thread` pour wrapper l'embedding SentenceTransformer.

Refs :
  - Issue parent : #204 Sprint L item P2-09
  - PR precedente : #266 (PR 3/5 NLUPreprocessor)
  - Pattern source : #262 (PR 1/5 MeteoInjector), #265 (PR 2/5 CityDetector)
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from app.models.schemas import Language
from app.data.calendrier_agricole import get_conseil_saisonnier
from app.services.chat._types import ChatResult
from app.services.chat.meteo_injector import inject_meteo
from app.services.chat.nlu_preprocessor import ACTION_TO_INTENT, NLUResult

logger = logging.getLogger(__name__)


async def _synthesize_dioula(text: str) -> Optional[str]:
    """Wrapper async pour synthese TTS dioula.

    Identique a `ChatService._synthesize_dioula` — duplique ici pour eviter
    un import circulaire (chat_service importe ivr_searcher). Cette
    duplication peut etre eliminee en PR 5/5 si on extrait aussi
    `synthesize_dioula` dans un module dedie.
    """
    from app.services.tts_dioula import synthesize_dioula_text
    return await asyncio.to_thread(synthesize_dioula_text, text)


# ─────────────────────────────────────────────
# Etape 3 : IVR exact (match intent + culture)
# ─────────────────────────────────────────────


async def try_ivr_exact(
    nlu: NLUResult,
    city: str,
    weather_data: dict | None,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Cherche une reponse IVR exacte par intent + culture.

    Retourne None si nlu.intent est vide, ou erreur VDB, ou pas de match
    corpus. Sinon ChatResult avec response (FR par contrat #167),
    response_dioula, audio_url (TTS si include_audio), meta complete.
    """
    # Facade ADR-0008 §Phase C : route vers Chroma / dual / pgvector
    # via `corpus_storage_mode`. API identique a `vdb_service`.
    from app.services.corpus_facade import chercher_reponse_ivr, get_phrases_for_intent

    cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
    conditions = [k for k in nlu.concepts if k.startswith("PROBLEME_") or k.startswith("TEMPS_")]

    if not nlu.intent:
        return None

    try:
        # Sprint G.2 (issue #193) : `chercher_reponse_ivr` invoque
        # `corpus_service._embed_query()` (SentenceTransformer.encode
        # ~50-200ms) qui bloque le event loop FastAPI sans `to_thread`.
        result = await asyncio.to_thread(
            chercher_reponse_ivr,
            nlu.intent,
            cultures if cultures else ["*"],
            conditions,
        )
    except Exception as e:
        logger.error("[IVR] VDB erreur: %s", e)
        return None

    if not result:
        return None

    logger.info("[IVR] exact: %s (intent=%s)", result["id"], nlu.intent)
    ivr_bambara = result["reponse_bambara"]
    ivr_fr = result.get("reponse_fr", "")

    # Remplacer {{METEO_CONTEXTUEL}} (bam) et {{METEO_FR}} (fr)
    ivr_bambara, ivr_fr = inject_meteo(ivr_bambara, ivr_fr, weather_data, city)

    # Securite : effacer tags residuels
    ivr_bambara = re.sub(r"\{\{[^}]+\}\}", "", ivr_bambara).strip()
    ivr_fr = re.sub(r"\{\{[^}]+\}\}", "", ivr_fr).strip()

    # Conseil saisonnier (bilingue)
    conseil = get_conseil_saisonnier(cultures, intent=nlu.intent)
    if conseil:
        ivr_bambara = ivr_bambara + " " + conseil["bambara"]
        if ivr_fr:
            ivr_fr = ivr_fr + " " + conseil["fr"]

    # TTS base sur le bambara
    audio_url = None
    if include_audio:
        audio_url = await _synthesize_dioula(ivr_bambara)

    # Phrases attestees (pour meta)
    try:
        phrases_att = get_phrases_for_intent(nlu.intent, cultures)
    except Exception:
        phrases_att = []

    return ChatResult(
        # response = FR par contrat (cf. #167). Fallback bambara uniquement si
        # l'entree corpus n'a pas reponse_fr (0/162 actuellement, garde-fou).
        response=ivr_fr or ivr_bambara,
        response_dioula=ivr_bambara,
        audio_url=audio_url,
        city=city,
        language=language.value,
        audio_language="Dioula" if audio_url else None,
        meta={
            "intent": nlu.intent,
            "cultures": cultures,
            "source": "ivr_exact",
            "phrases_attestees": [p["text"] for p in phrases_att[:3]] if phrases_att else [],
        },
    )


# ─────────────────────────────────────────────
# Etape 4 : Fallback IVR par concept
# ─────────────────────────────────────────────


async def try_ivr_concept(
    nlu: NLUResult,
    city: str,
    include_audio: bool,
    language: Language,
) -> Optional[ChatResult]:
    """Cherche une reponse IVR approchee par concept (niveau 2)."""
    logger.info("[IVR] Hors corpus (intent=%s) → recherche concept", nlu.intent)

    # Fix #94 : detection action agricole sans culture → clarification
    has_agri_action = any(
        a in nlu.concepts for a in (
            "ACTION_PLANTER", "ACTION_CHERCHER_CONSEIL",
            "ACTION_RECOLTER", "ACTION_ARROSER",
            "ACTION_TRAITER", "ACTION_STOCKER",
        )
    )
    has_culture = any(
        k.startswith("CULTURE_") or k.startswith("ANIMAL_")
        for k in nlu.concepts
    )
    if has_agri_action and not has_culture:
        logger.info("[IVR] Action agricole sans culture → clarification")
        return await clarify_missing_culture(city, include_audio, language, nlu)

    ivr_result = await search_ivr_by_concept(nlu.concepts)
    if not ivr_result:
        return None

    ivr_bambara = ivr_result["reponse_bambara"]
    ivr_fr = ivr_result["reponse_fr"]

    audio_url = None
    if include_audio:
        audio_url = await _synthesize_dioula(ivr_bambara)

    cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
    return ChatResult(
        response=ivr_fr or ivr_bambara,
        response_dioula=ivr_bambara,
        audio_url=audio_url,
        city=city,
        language=language.value,
        audio_language="Dioula" if audio_url else None,
        meta={"intent": nlu.intent, "cultures": cultures, "source": "ivr_fallback"},
    )


async def clarify_missing_culture(
    city: str,
    include_audio: bool,
    language: Language,
    nlu: NLUResult,
) -> ChatResult:
    """Demande a l'utilisateur de preciser la culture (fix #94)."""
    message_dyu = (
        "N'ma a faamu ka ɲɛ. I be kuma sɛnɛ fɛn juma kan? "
        "Malo, kaba, tiga, kakawo wala dɔ wɛrɛ?"
    )
    message_fr = (
        "Je n'ai pas bien compris. De quelle culture parles-tu ? "
        "Riz, maïs, arachide, cacao ou autre ?"
    )

    audio_url = None
    if include_audio:
        audio_url = await _synthesize_dioula(message_dyu)

    return ChatResult(
        response=message_fr,
        response_dioula=message_dyu,
        audio_url=audio_url,
        city=city,
        language=language.value,
        audio_language="Dioula" if audio_url else None,
        meta={
            "intent": nlu.intent,
            "source": "clarification_culture",
            "detected_actions": [a for a in nlu.concepts if a.startswith("ACTION_")],
        },
    )


# ─────────────────────────────────────────────
# Utilitaire interne : recherche par concept
# ─────────────────────────────────────────────


async def search_ivr_by_concept(concepts: dict) -> Optional[dict]:
    """Recherche IVR par concept (fallback niveau 2).

    Retourne un dict {reponse_bambara, reponse_fr} pour permettre au caller
    d'envoyer la version FR dans `response` et la version dioula dans
    `response_dioula` (cf. issue #166).
    """
    if not concepts:
        return None

    from app.services.corpus_facade import chercher_reponse_ivr

    cultures = [k for k in concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
    if not cultures:
        # Fix #94 : plus de fallback silencieux vers CULTURE_MAIS.
        logger.info("[IVR] Action agricole sans culture detectee → clarification necessaire")
        return None

    intent_candidat = next(
        (intent for action, intent in ACTION_TO_INTENT.items() if action in concepts),
        None,
    )

    try:
        if intent_candidat:
            result = await asyncio.to_thread(
                chercher_reponse_ivr, intent_candidat, cultures, []
            )
            if result:
                logger.info("[IVR] concept: %s (intent=%s)", result["id"], intent_candidat)
                return {
                    "reponse_bambara": result["reponse_bambara"],
                    "reponse_fr": result.get("reponse_fr", ""),
                }

        result = await asyncio.to_thread(
            chercher_reponse_ivr, "CONSEIL_PRODUCTION", cultures, []
        )
        if result:
            logger.info("[IVR] concept: %s (CONSEIL_PRODUCTION)", result["id"])
            return {
                "reponse_bambara": result["reponse_bambara"],
                "reponse_fr": result.get("reponse_fr", ""),
            }
    except Exception as e:
        logger.error("[IVR] erreur recherche par concept: %s", e)

    return None
