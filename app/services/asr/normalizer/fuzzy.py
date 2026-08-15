"""Étape 3 : fuzzy matching Levenshtein sur le vocabulaire NLU."""
import logging
from typing import Optional

from app.services.asr.normalizer.data import _NLU_VOCAB, _NLU_VOCAB_LIST

logger = logging.getLogger(__name__)


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


def _phonological_variant_in_vocab(word_lower: str) -> Optional[str]:
    """Cherche une variante phonologique dioula↔bambara présente dans le vocab NLU.

    ADR-0020 : applique les 5 règles phonologiques déterministes (gw↔g, l↔d,
    l↔j, r↔l intervoc, nin↔len) et retourne la première variante — autre que le
    mot lui-même — qui est un mot NLU connu. Aucune substitution lexicale n'est
    faite ici (celles-ci restent conditionnelles au sens, hors de ce module).

    Limite connue : cette étape n'est atteinte QUE pour un mot hors vocab (les
    mots déjà connus font early-return dans _fuzzy_correct_word). Deux mots NLU
    sont phonologiquement voisins (wolo=poulet ↔ woro=porc/cola) ; comme les deux
    sont dans le vocab, aucun n'est jamais réécrit vers l'autre par cette voie.
    Le risque résiduel (un mot ASR hors vocab dont une variante tombe sur l'un
    d'eux) est ≤ à celui du fuzzy Levenshtein existant, plus permissif.

    Retourne None si aucune variante n'est dans le vocabulaire.
    """
    try:
        from app.services.language import phonological_variants
    except ImportError:
        return None
    for variant in phonological_variants(word_lower):
        if variant != word_lower and variant in _NLU_VOCAB:
            return variant
    return None


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

    phon_match = _phonological_variant_in_vocab(word_lower)
    if phon_match:
        logger.info("[ASR-NORM] Variante phonologique: '%s' → '%s'", word, phon_match)
        return phon_match

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
                if (dist < best_distance) or (dist == best_distance and cons < best_consonant_changes):
                    best_distance = dist
                    best_consonant_changes = cons
                    best_match = candidate

        if best_match:
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
        clean = word.strip(".,!?;:\"'")
        suffix = word[len(clean):]
        corrected_word = _fuzzy_correct_word(clean)
        corrected.append(corrected_word + suffix)
    return " ".join(corrected)
