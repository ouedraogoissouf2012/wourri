"""
WOURI — Normalizer post-ASR unifié pour le bambara/dioula.

Placé entre l'ASR et le reste du pipeline (NLU, traduction, TTS).
Tout le pipeline profite des corrections.

Architecture (validée par la littérature ASR error correction 2025-2026) :
    1. Corrections exactes multi-mots depuis JSON (fusions, fragmentations, particules)
    2. Corrections exactes mono-mot depuis le normalizer bambara existant (NeMo fusions)
    3. Fuzzy matching Levenshtein (distance adaptative) sur le vocabulaire NLU (645 mots)

Références :
    - Hybrid phonetic-neural model for ASR correction (arXiv:2102.06744)
    - Bambara phonology : 7 voyelles (a,e,ɛ,i,o,ɔ,u), paires proches e/ɛ o/ɔ
    - Nasalisation documentée (An Ka Taa, Vydrin 2020)
"""
import json
import logging
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # wouri-api/
_CORRECTIONS_PATH = _PROJECT_ROOT / "dictionnaires" / "asr_corrections.json"
_NLU_CONCEPTS_PATH = _PROJECT_ROOT / "dictionnaires" / "nlu_concepts.json"


# ---------------------------------------------------------------------------
# Chargement des données (une seule fois au premier import)
# ---------------------------------------------------------------------------

def _load_exact_corrections() -> dict[str, str]:
    """Charge les corrections exactes depuis asr_corrections.json.

    Fusionne toutes les catégories en un dict plat {wrong: correct}.
    """
    corrections: dict[str, str] = {}
    try:
        with open(_CORRECTIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for category, pairs in data.get("corrections", {}).items():
            if isinstance(pairs, dict):
                corrections.update(pairs)
        logger.info("[ASR-NORM] %d corrections exactes chargées depuis JSON", len(corrections))
    except FileNotFoundError:
        logger.warning("[ASR-NORM] Fichier %s non trouvé", _CORRECTIONS_PATH)
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement corrections: %s", e)
    return corrections


def _load_nlu_vocabulary() -> set[str]:
    """Charge les mots-clés du NLU comme vocabulaire de référence pour le fuzzy matching."""
    vocab: set[str] = set()
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        concepts = data.get("concepts", {})
        for name, concept_data in concepts.items():
            if isinstance(concept_data, dict):
                for kw in concept_data.get("keywords", []):
                    vocab.add(kw.lower())
            elif isinstance(concept_data, list):
                for kw in concept_data:
                    vocab.add(kw.lower())
        logger.info("[ASR-NORM] %d mots-clés NLU chargés pour fuzzy matching", len(vocab))
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement vocabulaire NLU: %s", e)
    return vocab


# Chargement au premier import
_EXACT_CORRECTIONS = _load_exact_corrections()
_NLU_VOCAB = _load_nlu_vocabulary()
_NLU_VOCAB_LIST = sorted(_NLU_VOCAB)  # Liste triée pour rapidfuzz


# ---------------------------------------------------------------------------
# Étape 1 : Corrections exactes multi-mots
# ---------------------------------------------------------------------------

def _apply_exact_corrections(text: str) -> str:
    """Applique les corrections exactes (JSON + normalizer bambara fusions).

    Les corrections multi-mots (espaces, particules) sont appliquées
    par remplacement de sous-chaîne, ordonnées par longueur décroissante
    pour éviter les conflits (ex: "ani sɔgɔma" avant "ani").
    """
    result = f" {text} "  # Pad pour matcher les frontières de mot
    for wrong in sorted(_EXACT_CORRECTIONS, key=len, reverse=True):
        if wrong in result:
            result = result.replace(wrong, _EXACT_CORRECTIONS[wrong])
    return result.strip()


# ---------------------------------------------------------------------------
# Étape 2 : Corrections fusions NeMo (normalizer bambara existant)
# ---------------------------------------------------------------------------

def _apply_nemo_fusions(text: str) -> str:
    """Applique les corrections de fusions syllabiques NeMo.

    Délègue au normalizer bambara existant (FUSIONS + PHRASE_SUBS).
    """
    from app.services.asr_bambara_normalizer import normalize_bambara_asr
    return normalize_bambara_asr(text) or text


# ---------------------------------------------------------------------------
# Étape 3 : Fuzzy matching Levenshtein sur vocabulaire NLU
# ---------------------------------------------------------------------------

def _max_distance_for_word(word: str) -> int:
    """Distance max adaptative selon la longueur du mot.

    - Mots ≤ 3 chars : pas de fuzzy (trop de faux positifs)
    - Mots 4 chars : distance ≤ 1
    - Mots ≥ 5 chars : distance ≤ 2

    Justification : les mots courts bambara (ku, ji, ba) ont trop de
    voisins à distance 1. Les mots longs (sɛnɛ, wagati) tolèrent
    plus de variation sans ambiguïté.
    """
    n = len(word)
    if n <= 3:
        return 0
    if n == 4:
        return 1
    return 2


def _consonant_changes(word_a: str, word_b: str) -> int:
    """Compte le nombre de consonnes différentes entre deux mots de même longueur.

    Sert à départager les candidats fuzzy : on préfère les corrections
    qui ne changent que les voyelles (confusions e/ɛ, o/ɔ, i/o documentées
    en bambara) plutôt que les consonnes.
    """
    _VOWELS = set("aeɛiouɔàáâèéêìíòóôùú")
    changes = 0
    for a, b in zip(word_a.lower(), word_b.lower()):
        if a != b and (a not in _VOWELS or b not in _VOWELS):
            changes += 1
    return changes


def _fuzzy_correct_word(word: str) -> str:
    """Corrige un mot par fuzzy matching contre le vocabulaire NLU.

    Utilise rapidfuzz (C++ backend) pour des performances < 0.1ms.
    Départage : à distance égale, préfère le candidat avec moins de
    changements de consonnes (les confusions voyelles sont plus probables
    en bambara : e/ɛ, o/ɔ, i/o — sources : Wikipedia Bambara phonology, Vydrin 2020).
    """
    if not _NLU_VOCAB_LIST:
        return word

    max_dist = _max_distance_for_word(word)
    if max_dist == 0:
        return word

    word_lower = word.lower()
    if word_lower in _NLU_VOCAB:
        return word

    try:
        from rapidfuzz.distance import Levenshtein

        best_match: Optional[str] = None
        best_distance = max_dist + 1
        best_consonant_changes = 999

        for candidate in _NLU_VOCAB_LIST:
            if abs(len(candidate) - len(word_lower)) > max_dist:
                continue

            dist = Levenshtein.distance(word_lower, candidate, score_cutoff=max_dist)
            if dist <= max_dist:
                cons = _consonant_changes(word_lower, candidate)
                # Préférer : distance plus petite, puis moins de consonnes changées
                if (dist < best_distance) or (dist == best_distance and cons < best_consonant_changes):
                    best_distance = dist
                    best_consonant_changes = cons
                    best_match = candidate

        if best_match:
            # Sécurité : rejeter si des consonnes ont changé (risque de faux positif)
            # SAUF : ajout/suppression de 'n' final = nasalisation bambara (documenté)
            # Source : An Ka Taa, Vydrin 2020 — le 'n' final signale la nasalisation
            is_nasal_only = (
                abs(len(word_lower) - len(best_match)) == 1
                and (word_lower.endswith("n") or best_match.endswith("n"))
                and (word_lower.rstrip("n") == best_match or best_match.rstrip("n") == word_lower
                     or word_lower[:-1] == best_match or best_match[:-1] == word_lower)
            )

            if best_consonant_changes > 0 and not is_nasal_only:
                logger.debug(
                    "[ASR-NORM] Fuzzy rejeté: '%s' → '%s' (consonnes changées=%d)",
                    word, best_match, best_consonant_changes,
                )
                return word

            logger.info(
                "[ASR-NORM] Fuzzy: '%s' → '%s' (distance=%d)",
                word, best_match, best_distance,
            )
            return best_match

    except ImportError:
        logger.warning("[ASR-NORM] rapidfuzz non installé — fuzzy matching désactivé")
    except Exception as e:
        logger.error("[ASR-NORM] Erreur fuzzy: %s", e)

    return word


def _apply_fuzzy_matching(text: str) -> str:
    """Applique le fuzzy matching mot par mot sur le texte."""
    words = text.split()
    corrected = []
    for word in words:
        # Séparer la ponctuation
        clean = word.strip(".,!?;:\"'")
        suffix = word[len(clean):]
        corrected_word = _fuzzy_correct_word(clean)
        corrected.append(corrected_word + suffix)
    return " ".join(corrected)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def normalize_asr_output(text: str) -> str:
    """Pipeline complet de normalisation post-ASR.

    Ordre :
    1. Corrections exactes multi-mots (JSON) — salutations, particules
    2. Corrections fusions NeMo — fusions syllabiques
    3. Fuzzy matching Levenshtein — mots isolés vs vocabulaire NLU

    Args:
        text: transcription brute de l'ASR.

    Returns:
        texte corrigé, prêt pour le NLU et la traduction.
    """
    if not text:
        return text

    original = text

    # Étape 1 : corrections exactes multi-mots
    text = _apply_exact_corrections(text)

    # Étape 2 : fusions NeMo
    text = _apply_nemo_fusions(text)

    # Étape 3 : fuzzy matching mot par mot
    text = _apply_fuzzy_matching(text)

    if text != original:
        logger.info("[ASR-NORM] '%s' → '%s'", original, text)

    return text
