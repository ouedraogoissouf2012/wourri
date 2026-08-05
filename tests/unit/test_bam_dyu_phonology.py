"""Tests du filtre phonologique dioula CI ↔ bambara Mali (ADR-0020, refonte #90).

Vérifie :
1. Chaque règle phonologique isolée (gw↔g, l↔d, l↔j, r↔l intervoc, nin↔len).
2. Réversibilité : depuis chaque forme, on atteint l'autre.
3. Critère #90 : ≥90 % de conversions correctes sur 50 paires connues.
4. Le module ne fait AUCUNE substitution lexicale (sugu/filɛ/bon…) — ADR-0020.
5. Bornes : mots vides/courts, pas d'explosion combinatoire.
"""

from __future__ import annotations

import pytest

from app.services.language.bam_dyu_phonology import (
    phonological_variants,
    variants_for_text,
)

# ---------------------------------------------------------------------------
# 50 paires (dioula CI, bambara Mali) dérivées des 5 règles de l'issue #90.
# Chaque paire doit être mutuellement atteignable par phonological_variants.
# ---------------------------------------------------------------------------

# Règle 1 : gw- ↔ g- devant ɛ
PAIRS_GW_G = [
    ("gwɛlɛn", "gɛlɛn"),
    ("gwɛ", "gɛ"),
    ("gwɛn", "gɛn"),
    ("gwɛlɛ", "gɛlɛ"),
    ("gwɛrɛ", "gɛrɛ"),
]

# Règle 2 : l- ↔ d- initial
PAIRS_L_D = [
    ("lo", "do"),
    ("la", "da"),
    ("li", "di"),
    ("lon", "don"),
    ("laga", "daga"),
    ("lugu", "dugu"),
    ("laba", "daba"),
    ("lima", "dima"),
    ("lasa", "dasa"),
    ("lene", "dene"),
]

# Règle 3 : l- ↔ j- initial
PAIRS_L_J = [
    ("lɔ", "jɔ"),
    ("lɔn", "jɔn"),
    ("lala", "jala"),
    ("lele", "jele"),
    ("lɔgɔ", "jɔgɔ"),
    ("liri", "jiri"),
    ("lɔli", "jɔli"),
    ("lama", "jama"),
    ("lɔni", "jɔni"),
    ("liba", "jiba"),
]

# Règle 4 : -r- ↔ -l- intervocalique
PAIRS_R_L = [
    ("wuru", "wulu"),
    ("bara", "bala"),
    ("kara", "kala"),
    ("foro", "folo"),
    ("suru", "sulu"),
    ("firi", "fili"),
    ("nara", "nala"),
    ("muru", "mulu"),
    ("tara", "tala"),
    ("keru", "kelu"),
    ("boro", "bolo"),
    ("saraka", "salaka"),
    ("bere", "bele"),
    ("dara", "dala"),
    ("giri", "gili"),
]

# Règle 5 : -nin ↔ -len résultatif
PAIRS_NIN_LEN = [
    ("tigɛnin", "tigɛlen"),
    ("sɛnɛnin", "sɛnɛlen"),
    ("dununin", "dunulen"),
    ("banin", "balen"),
    ("kɛnin", "kɛlen"),
    ("tanin", "talen"),
    ("bɔnin", "bɔlen"),
    ("minin", "milen"),
    ("sanin", "salen"),
    ("wulinin", "wulilen"),
]

ALL_PAIRS = (
    PAIRS_GW_G + PAIRS_L_D + PAIRS_L_J + PAIRS_R_L + PAIRS_NIN_LEN
)


def test_exactly_50_pairs():
    """Le critère #90 est fixé à 50 mots testés."""
    assert len(ALL_PAIRS) == 50


@pytest.mark.parametrize("dyu, bam", ALL_PAIRS)
def test_dyu_reaches_bam(dyu, bam):
    """Depuis la forme dioula CI, la forme bambara Mali est atteignable."""
    assert bam in phonological_variants(dyu)


@pytest.mark.parametrize("dyu, bam", ALL_PAIRS)
def test_bam_reaches_dyu(dyu, bam):
    """Réversibilité : depuis la forme bambara Mali, la forme dioula est atteignable."""
    assert dyu in phonological_variants(bam)


def test_success_rate_at_least_90_percent():
    """Critère explicite SYNTHESE/#90 : ≥90 % de conversions correctes sur 50 paires.

    Une paire compte comme réussie si les deux sens sont atteignables.
    """
    ok = sum(
        1
        for dyu, bam in ALL_PAIRS
        if bam in phonological_variants(dyu) and dyu in phonological_variants(bam)
    )
    rate = ok / len(ALL_PAIRS)
    assert rate >= 0.90, f"Taux de conversion {rate:.0%} < 90 % ({ok}/{len(ALL_PAIRS)})"


# ---------------------------------------------------------------------------
# Le module ne fait AUCUNE substitution lexicale (garde-fou ADR-0020).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "word, forbidden",
    [
        ("sugu", "lɔgɔ"),   # marché — conditionnel au sens, hors périmètre
        ("filɛ", "lajɛ"),   # regarder
        ("bon", "so"),      # maison
        ("bamuso", "ba"),   # maman
        ("sɛnɛbaga", "sɛnɛkɛla"),  # agriculteur
    ],
)
def test_no_lexical_substitution(word, forbidden):
    """Les substitutions lexicales de #90 ne DOIVENT PAS être appliquées ici.

    Elles dépendent du sens et restent dans prevalidation_rules.py (ADR-0020).
    """
    assert forbidden not in phonological_variants(word)


def test_sugu_is_not_touched():
    """`sugu` (= sorte/espèce, valide en dioula CI) ne doit générer aucune
    variante lexicale — seulement d'éventuelles variantes phonologiques inertes.
    """
    variants = phonological_variants("sugu")
    assert "lɔgɔ" not in variants  # pas de substitution marché


# ---------------------------------------------------------------------------
# Bornes et robustesse.
# ---------------------------------------------------------------------------

def test_original_word_always_included():
    assert "wuru" in phonological_variants("wuru")


def test_empty_string():
    assert phonological_variants("") == set()


def test_single_char_word_returns_itself():
    assert phonological_variants("a") == {"a"}


def test_variant_count_is_bounded():
    """Pas d'explosion combinatoire : chaque règle appliquée une fois."""
    for dyu, _ in ALL_PAIRS:
        assert len(phonological_variants(dyu)) <= 8


def test_gw_g_only_before_epsilon():
    """La règle gw↔g ne s'applique QUE devant ɛ, pas devant d'autres voyelles."""
    # 'gulu' commence par g mais pas gɛ → aucune insertion de w parasite.
    assert "gwulu" not in phonological_variants("gulu")


def test_intervocalic_only():
    """r↔l ne s'applique qu'entre deux voyelles, pas en position initiale/finale."""
    # 'rani' : 'r' initial (pas intervocalique) → pas d'échange en tête.
    variants = phonological_variants("rani")
    assert "lani" not in variants


# ---------------------------------------------------------------------------
# variants_for_text : utilitaire d'intégration.
# ---------------------------------------------------------------------------

def test_variants_for_text_maps_transformable_words():
    result = variants_for_text("wuru bɛ")
    assert "wuru" in result
    assert "wulu" in result["wuru"]


def test_variants_for_text_skips_untransformable():
    """Un mot sans variante possible n'apparaît pas dans le résultat."""
    result = variants_for_text("aa")
    assert result == {}
