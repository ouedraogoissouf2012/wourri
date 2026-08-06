"""WOURI — variantes phonologiques dioula CI ↔ bambara Mali (ADR-0020).

Périmètre volontairement RÉDUIT (ADR-0020, refonte de l'issue #90) : ce module
n'implémente QUE les 5 règles phonologiques déterministes et réversibles listées
par #90. Il n'applique AUCUNE substitution lexicale (sugu/filɛ/bon…) ni grammaticale :
- les substitutions lexicales dépendent du SENS et restent dans
  `scripts/prevalidation_rules.py` (conditionnelles, validées nativement) ;
- les transformations grammaticales exigent un analyseur syntaxique inexistant.

Usage voulu (ADR-0020 §Décision) : ce module ne RÉÉCRIT PAS le texte servi à
l'utilisateur. Il génère des VARIANTES d'un mot pour aider le matching post-ASR
(`asr_normalizer.py`) quand les modèles ASR — entraînés surtout sur bambara Mali —
produisent une forme malienne d'un mot dioula (ou l'inverse). Le NLU/corpus peut
alors matcher une variante sans que l'on corrompe la phrase.

Les 5 règles (source : issue #90, SYNTHESE §2.6, An Ka Taa / Vydrin 2020) :

    | Dioula CI | Bambara Mali | Contexte              | Exemple          |
    |-----------|--------------|-----------------------|------------------|
    | gw-       | g-           | devant ɛ (initial)    | gwɛlɛn ↔ gɛlɛn   |
    | l-        | d-           | initial               | lo ↔ do, la ↔ da |
    | l-        | j-           | initial               | lɔ ↔ jɔ          |
    | -r-       | -l-          | intervocalique        | wuru ↔ wulu      |
    | -nin      | -len         | suffixe résultatif    | (participial)    |

Chaque règle est bidirectionnelle : on énumère les DEUX sens et on renvoie
l'ensemble des formes atteignables. `phonological_variants(mot)` inclut toujours
le mot d'origine. Le nombre de variantes est borné (application d'une règle par
position, sans récursion combinatoire) pour rester déterministe et rapide.
"""

from __future__ import annotations

import re

# Les 7 voyelles du bambara/dioula (a, e, ɛ, i, o, ɔ, u). Sert à détecter le
# contexte « intervocalique » et « devant ɛ ». Source : phonologie mandingue
# standard (Vydrin 2020), cohérent avec asr_normalizer._VOWELS.
_VOWELS = frozenset("aeɛiouɔ")

# Longueur minimale d'un mot pour tenter des variantes. En dessous, le risque
# de produire un homographe non pertinent l'emporte sur le gain de matching.
_MIN_WORD_LEN = 2


def _initial_consonant_swaps(word: str) -> set[str]:
    """Règles 2 et 3 : consonne initiale l ↔ d et l ↔ j.

    Dioula CI initial `l-` correspond à `d-` ou `j-` en bambara Mali
    (lo↔do, la↔da, lɔ↔jɔ). Réversible : on énumère les deux sens.
    """
    out: set[str] = set()
    if not word:
        return out
    first, rest = word[0], word[1:]
    # dioula → bambara
    if first == "l":
        out.add("d" + rest)
        out.add("j" + rest)
    # bambara → dioula
    elif first in ("d", "j"):
        out.add("l" + rest)
    return out


def _gw_g_swaps(word: str) -> set[str]:
    """Règle 1 : gw- ↔ g- devant ɛ (initial).

    Dioula CI `gwɛ...` correspond au bambara Mali `gɛ...` (gwɛlɛn↔gɛlɛn).
    Le contexte « devant ɛ » est vérifié explicitement pour ne pas toucher
    d'autres `g`/`gw`.
    """
    out: set[str] = set()
    # dioula gwɛ- → bambara gɛ-
    if word.startswith("gwɛ"):
        out.add("g" + word[2:])  # retire le 'w' : gwɛ... → gɛ...
    # bambara gɛ- → dioula gwɛ-
    elif word.startswith("gɛ"):
        out.add("gw" + word[1:])  # insère le 'w' : gɛ... → gwɛ...
    return out


def _intervocalic_r_l_swaps(word: str) -> set[str]:
    """Règle 4 : -r- ↔ -l- intervocalique (wuru ↔ wulu).

    On échange chaque `r`/`l` situé entre deux voyelles, une position à la
    fois (pas de produit cartésien), ce qui suffit au matching et reste borné.
    """
    out: set[str] = set()
    for i in range(1, len(word) - 1):
        c = word[i]
        if c not in ("r", "l"):
            continue
        if word[i - 1] in _VOWELS and word[i + 1] in _VOWELS:
            swapped = "l" if c == "r" else "r"
            out.add(word[:i] + swapped + word[i + 1 :])
    return out


def _resultative_suffix_swaps(word: str) -> set[str]:
    """Règle 5 : suffixe résultatif -nin ↔ -len (participial).

    Dioula CI `-nin` correspond au bambara Mali `-len`. On ne touche qu'à la
    fin du mot et on garde une racine non vide.
    """
    out: set[str] = set()
    if word.endswith("nin") and len(word) > 3:
        out.add(word[:-3] + "len")
    elif word.endswith("len") and len(word) > 3:
        out.add(word[:-3] + "nin")
    return out


def phonological_variants(word: str) -> set[str]:
    """Renvoie l'ensemble des variantes phonologiques dioula↔bambara d'un mot.

    Inclut toujours le mot d'origine. Applique les 5 règles ADR-0020, chacune
    une fois (pas de composition récursive : le but est le matching, pas la
    génération exhaustive). Casse préservée par le NLU en aval (matching sur
    formes minuscules), donc on travaille sur le mot tel quel.

    Args:
        word: un mot (sans espaces). Les chaînes vides/courtes renvoient {word}.

    Returns:
        set contenant `word` et ses variantes phonologiques.
    """
    if not word or len(word) < _MIN_WORD_LEN:
        return {word} if word else set()

    variants: set[str] = {word}
    variants |= _initial_consonant_swaps(word)
    variants |= _gw_g_swaps(word)
    variants |= _intervocalic_r_l_swaps(word)
    variants |= _resultative_suffix_swaps(word)
    return variants


# Découpe un texte en tokens (mots) en gardant les séparateurs pour ne PAS
# altérer la ponctuation ni les espaces à la reconstruction éventuelle.
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def variants_for_text(text: str) -> dict[str, set[str]]:
    """Mappe chaque mot d'un texte vers ses variantes phonologiques.

    Utilitaire pour l'intégration ASR : le normalizer peut, pour un mot non
    reconnu, tester ses variantes phonologiques comme candidats de matching.
    Ne renvoie que les mots ayant AU MOINS une variante autre qu'eux-mêmes,
    pour éviter de charger l'appelant avec des singletons inutiles.

    Args:
        text: texte libre (une transcription ASR par exemple).

    Returns:
        dict {mot: variantes} restreint aux mots réellement transformables.
    """
    result: dict[str, set[str]] = {}
    for match in _TOKEN_RE.finditer(text.lower()):
        word = match.group(0)
        if word in result:
            continue
        variants = phonological_variants(word)
        if len(variants) > 1:
            result[word] = variants
    return result
