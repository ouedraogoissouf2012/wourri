"""
WOURI - Normaliseur post-ASR pour le bambara/dioula

NeMo TDT (Soloni) produit deux types d'erreurs sur le bambara/dioula :
1. Fusions syllabiques : "a ni sɔgɔma" → "anisogma"
2. Substitutions phonétiques sur mots courts (2 chars) :
   "ku" (igname) → "ko"  (confusion u/o sur voyelles courtes)

Ce module corrige ces erreurs APRÈS la transcription NeMo,
AVANT que le texte arrive au NLU.
"""
import logging
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# DICTIONNAIRE DE CORRECTIONS
# Fusions syllabiques courantes de NeMo TDT sur le bambara/dioula
# ============================================================

# Mots fusionnés → forme correcte (espaces restaurés)
FUSIONS: dict[str, str] = {

    # ── "a ni sɔgɔma" (bonjour du matin — bambara/dioula) ──
    "anisogma":    "a ni sɔgɔma",
    "anisogoma":   "a ni sɔgɔma",
    "ansogma":     "a ni sɔgɔma",
    "anisɔgɔma":   "a ni sɔgɔma",
    "anisɔgma":    "a ni sɔgɔma",
    "anisogɔma":   "a ni sɔgɔma",

    # ── "i ni sɔgɔma" (bonjour du matin — forme polie) ──
    "inisogma":    "i ni sɔgɔma",
    "inisogoma":   "i ni sɔgɔma",
    "insogma":     "i ni sɔgɔma",
    "inisɔgɔma":   "i ni sɔgɔma",
    "inisɔgma":    "i ni sɔgɔma",

    # ── "an ni sɔgɔma" (bonjour pluriel) ──
    "annisogma":   "an ni sɔgɔma",
    "annisogoma":  "an ni sɔgɔma",
    "annisɔgɔma":  "an ni sɔgɔma",

    # ── "i ni cɛ" / "a ni cɛ" (bonjour générique) ──
    "inice":       "i ni cɛ",
    "inicé":       "i ni cɛ",
    "inicɛ":       "i ni cɛ",
    "anice":       "a ni cɛ",
    "anicɛ":       "a ni cɛ",
    "anicé":       "a ni cɛ",

    # ── "i ni wula" (bonsoir) ──
    "iniwula":     "i ni wula",
    "inwula":      "i ni wula",
    "aniwula":     "a ni wula",

    # ── "i ni tile" (bonne journée) ──
    "initile":     "i ni tile",
    "intile":      "i ni tile",

    # ── "i ni su" (bonne nuit) ──
    "inisu":       "i ni su",
    "anisu":       "a ni su",

    # ── Fusions de particules grammaticales courantes ──
    # b'a fɛ (il/elle veut)
    "bafe":        "b'a fɛ",
    "bafɛ":        "b'a fɛ",
    # n'a bɛ (je/nous sommes)
    "nabe":        "n'a bɛ",
    "nabe":        "n a bɛ",
}


# ============================================================
# SUBSTITUTIONS PHONÉTIQUES EN CONTEXTE AGRICOLE
# NeMo TDT confond les voyelles courtes sur les mots de 2 chars.
# Observé : "ku" (igname) → "ko"  (confusion u/o)
# Correction par bi-gramme pour éviter les faux positifs
# ("ko" seul = "chose/affaire" en bambara, ne pas remplacer globalement)
# ============================================================

PHRASE_SUBS: dict[str, str] = {
    # ku = igname — NeMo produit "ko" au lieu de "ku"
    "ko sɛnɛ":    "ku sɛnɛ",     # planter l'igname
    "ko foro":    "ku foro",      # champ d'igname
    "k'a ko":     "k'a ku",       # pour (faire) l'igname (k'a ku sɛnɛ)
    "ko bɔ":      "ku bɔ",        # récolter l'igname
    "ko tilalen": "ku tilalen",   # récolte igname
    "ko dɛmɛ":   "ku dɛmɛ",     # aider l'igname (croissance)
}


# ============================================================
# INDEX SANS TONS (pour matcher les variantes non tonées de NeMo)
# ============================================================

def _strip_tones(text: str) -> str:
    """Retire les diacritiques de ton tout en gardant ɛ, ɔ, ŋ, ɲ."""
    result = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn":   # Mark, Nonspacing
            continue
        result.append(ch)
    return "".join(result).lower()


# Construit une fois au chargement du module
_FUSIONS_NOTONE: dict[str, str] = {
    _strip_tones(k): v for k, v in FUSIONS.items()
}


# ============================================================
# FONCTIONS PRINCIPALES
# ============================================================

def _apply_phrase_subs(text: str) -> str:
    """Corrige les substitutions phonétiques de n-grammes agricoles."""
    result = text
    for wrong, correct in PHRASE_SUBS.items():
        if wrong in result:
            result = result.replace(wrong, correct)
            logger.info(f"[ASR-NORM] Substitution phonétique: '{wrong}' → '{correct}'")
    return result


def normalize_bambara_asr(text: str) -> Optional[str]:
    """
    Corrige les erreurs NeMo dans une transcription bambara.

    Étape 1 : substitutions phonétiques de n-grammes (ku→ko, etc.)
    Étape 2 : fusions syllabiques mot par mot

    Args:
        text: texte brut retourné par NeMo

    Returns:
        texte corrigé (inchangé si aucune erreur détectée)
    """
    if not text:
        return text

    # Étape 1 — substitutions phonétiques (bi-grammes contextuels)
    text = _apply_phrase_subs(text)

    # Étape 2 — fusions syllabiques mot par mot
    words = text.split()
    corrected_words = []

    for word in words:
        word_clean = word.strip(".,!?;:\"'")
        suffix = word[len(word_clean):]

        word_notone = _strip_tones(word_clean)
        correction = FUSIONS.get(word_clean) or _FUSIONS_NOTONE.get(word_notone)

        if correction:
            corrected_words.append(correction + suffix)
        else:
            corrected_words.append(word)

    result = " ".join(corrected_words)

    if result != text:
        logger.info(f"[ASR-NORM] Fusion corrigée: '{text}' → '{result}'")

    return result
