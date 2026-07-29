"""
WOURI — NLUPreprocessor : extraction de `chat_service.py` (refactor P2-09 PR 3/5).

Module PUR (pas d'etat persistant) qui gere le preprocessing NLU :
  - `preprocess_nlu()` : applique le NLU sur le message si dioula/bambara,
    avec fallback FR pour `language=BOTH` (Sprint G.1 #171/#191).
  - `enrich_for_deepseek()` : ajoute un contexte [Paysan cultive: X] pour
    guider DeepSeek.
  - Constante `NLUResult` (dataclass) : type de retour partage avec les
    autres etapes du pipeline chat (IVR, DeepSeek).

Pattern aligne avec PR 1/5 (MeteoInjector) + PR 2/5 (CityDetector) : fonctions
module-level pour helpers sans etat. `NLUResult` est defini ici car c'est le
type de retour de ce module ; chat_service.py le re-exporte pour back-compat.

Refs :
  - Issue parent : #204 Sprint L item P2-09
  - PR precedente : #265 (PR 2/5 CityDetector)
  - Pattern source : #262 (PR 1/5 MeteoInjector)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.models.schemas import Language

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass de resultat (re-exporte par chat_service pour back-compat)
# ---------------------------------------------------------------------------

@dataclass
class NLUResult:
    """Resultat du preprocessing NLU.

    Defini ici car c'est le type de retour de `preprocess_nlu()`. Consomme
    par les autres etapes du pipeline chat (IVR exact, IVR concept, DeepSeek).

    Fields :
      message_for_deepseek: message a passer a DeepSeek (peut etre enrichi
                            via `enrich_for_deepseek()`)
      intent: intent NLU detecte (ou None si non reconnu)
      concepts: dict des concepts trouves (CULTURE_RIZ, ACTION_PLANTER, etc.)
      is_out_of_scope: True si message hors-sujet agricole detecte
    """
    message_for_deepseek: str
    intent: Optional[str] = None
    concepts: dict = field(default_factory=dict)
    is_out_of_scope: bool = False


# ---------------------------------------------------------------------------
# Labels pour enrichissement DeepSeek
# ---------------------------------------------------------------------------

CULTURE_LABELS = {
    "CULTURE_RIZ": "riz", "CULTURE_MAIS": "maïs", "CULTURE_MIL": "mil",
    "CULTURE_ARACHIDE": "arachide", "CULTURE_IGNAME": "igname", "CULTURE_MANIOC": "manioc",
    "CULTURE_HARICOT": "haricot", "CULTURE_COTON": "coton", "CULTURE_SESAME": "sésame",
    "CULTURE_BANANE": "banane", "CULTURE_TOMATE": "tomate", "CULTURE_OIGNON": "oignon",
    "CULTURE_PATATE": "patate douce", "CULTURE_GOMBO": "gombo", "CULTURE_CACAO": "cacao",
    "CULTURE_CAFE": "café", "CULTURE_ANANAS": "ananas", "CULTURE_MANGUE": "mangue",
    "CULTURE_AGRUMES": "agrumes", "CULTURE_NERE": "néré",
    "CULTURE_ANACARDE": "anacarde", "CULTURE_PALMIER_HUILE": "palmier à huile",
}

ANIMAL_LABELS = {
    "ANIMAL_POULET": "poulets", "ANIMAL_BOVIN": "bovins", "ANIMAL_OVIN": "moutons",
    "ANIMAL_CAPRIN": "chèvres", "ANIMAL_PORC": "porcs", "ANIMAL_POISSON": "poissons",
}

ACTION_TO_INTENT = {
    "ACTION_PLANTER": "QUESTION_SAISON_PLANTATION",
    "ACTION_RECOLTER": "QUESTION_RECOLTE",
    "ACTION_ARROSER": "QUESTION_IRRIGATION",
    "ACTION_TRAITER": "DIAGNOSTIC_PROBLEME",
    "ACTION_STOCKER": "QUESTION_STOCKAGE",
    "ACTION_VENDRE": "QUESTION_VENTE",
    "ACTION_CHERCHER_CONSEIL": "CONSEIL_PRODUCTION",
    "ACTION_LABOURER": "CONSEIL_PRODUCTION",
}


# ---------------------------------------------------------------------------
# Fonctions module
# ---------------------------------------------------------------------------

def preprocess_nlu(
    message: str,
    bambara_text: Optional[str],
    language: Language,
) -> NLUResult:
    """Applique le NLU si le message est en dioula/bambara.

    Sprint G.1 (issue #171, #191) : fallback FR pour `language=BOTH` quand
    aucun texte dioula n'est disponible. Le `ConceptExtractor` indexe deja
    les mots-cles francais (`riz`, `planter`, `mais`, etc. dans
    `dictionnaires/nlu_concepts.json`) — verifie empiriquement sur 6 phrases
    FR variees. Sans ce fallback, la cascade tombe sur DeepSeek+NLLB qui
    invente des termes hors-vocabulaire valide (ex: `rɛzɛnmɔw` au lieu
    de `malo` pour le riz).

    Args:
        message: Message utilisateur original (FR ou autre).
        bambara_text: Texte deja transcrit en dioula/bambara (peut etre None).
        language: Mode de langue choisi par l'utilisateur (FR/DIOULA/BOTH).

    Returns:
        NLUResult avec message_for_deepseek + intent + concepts + flag hors-sujet.
    """
    if language not in (Language.DIOULA, Language.BOTH):
        return NLUResult(message_for_deepseek=message)

    text_to_analyze = bambara_text or ""
    bambara_chars = set("ɛɔŋɲɛ̀ɛ́ɔ̀ɔ́")
    if not text_to_analyze and any(c in message for c in bambara_chars):
        text_to_analyze = message

    # Fallback FR (Sprint G.1) : si mode BOTH et pas de texte dioula,
    # passer le message FR au NLU qui a aussi les keywords agricoles FR.
    if not text_to_analyze and language == Language.BOTH:
        text_to_analyze = message

    if not text_to_analyze:
        return NLUResult(message_for_deepseek=message)

    try:
        from app.services.nlu import get_nlu_service
        nlu = get_nlu_service()
        if nlu is None:
            return NLUResult(message_for_deepseek=message)

        result = nlu.process(text_to_analyze)

        if result.is_out_of_scope:
            logger.info("[NLU] Hors sujet: '%s'", text_to_analyze[:50])
            return NLUResult(
                message_for_deepseek=result.out_of_scope_message_fr or message,
                intent="HORS_SUJET",
                is_out_of_scope=True,
            )

        concepts = result.concepts or {}
        if result.french_sentence:
            enriched = enrich_for_deepseek(result.french_sentence, concepts)
            logger.info("[NLU] phrase: '%s'", result.french_sentence)
            return NLUResult(
                message_for_deepseek=enriched,
                intent=result.intent,
                concepts=concepts,
            )

        return NLUResult(
            message_for_deepseek=message,
            intent=result.intent,
            concepts=concepts,
        )

    except Exception as e:
        logger.error("[NLU] erreur: %s", e)
        return NLUResult(message_for_deepseek=message)


def enrich_for_deepseek(french_sentence: str, concepts: dict) -> str:
    """Ajoute un contexte [Paysan cultive: X] pour guider DeepSeek.

    Prend la 1ere culture trouvee dans `concepts`, sinon le 1er animal.
    Si aucun sujet detecte, retourne la phrase inchangee.
    """
    culture = next((CULTURE_LABELS[k] for k in concepts if k in CULTURE_LABELS), None)
    animal = next((ANIMAL_LABELS[k] for k in concepts if k in ANIMAL_LABELS), None)
    sujet = culture or animal
    if sujet:
        prefix = f"[Paysan cultive: {sujet}] "
        logger.info("[NLU] Contexte: %s", prefix.strip())
        return prefix + french_sentence
    return french_sentence
