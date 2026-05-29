"""
Tests des corrections STT Whisper (issue #228 + suite ADR-0005).

Couvre :
    - `_apply_corrections` helper (word boundary `\\b` apres issue #228)
    - `correct_agricultural_terms` wrapper
    - `correct_city_names` wrapper
    - Absence de faux positifs sur du francais courant
"""
from __future__ import annotations

import pytest

from app.services.stt_whisper import (
    _apply_corrections,
    correct_agricultural_terms,
    correct_city_names,
)


# ─────────────────────────────────────────────────────────────────────
# Helper _apply_corrections — word boundary actif (issue #228)
# ─────────────────────────────────────────────────────────────────────


def test_apply_corrections_text_vide_retourne_vide():
    assert _apply_corrections("", {"foo": "bar"}, "test") == ""


def test_apply_corrections_corrections_vides_retourne_inchange():
    assert _apply_corrections("hello world", {}, "test") == "hello world"


def test_apply_corrections_case_insensitive():
    assert _apply_corrections("ABIJEAN va bien", {"abijean": "Abidjan"}, "ville") == "Abidjan va bien"


def test_apply_corrections_word_boundary_pas_de_substring_match():
    # Sans `\b`, "ment" matcherait dans "vraiment" → "vraiMan"
    # Avec `\b`, seul "ment" isole peut matcher.
    result = _apply_corrections("vraiment important", {"ment": "Man"}, "test")
    assert result == "vraiment important", "Substring match doit etre bloque par word boundary"


def test_apply_corrections_word_boundary_match_isole_ok():
    # "ment" isole (entre 2 word boundaries) doit toujours matcher.
    result = _apply_corrections("je vais ment quelque part", {"ment": "Man"}, "test")
    assert "Man" in result


# ─────────────────────────────────────────────────────────────────────
# correct_city_names — absence de faux positifs (issue #228)
# ─────────────────────────────────────────────────────────────────────


# Phrases francaises courantes qui declenchaient AVANT le fix #228
# des faux positifs vers "Man" (ville Cote d'Ivoire).
@pytest.mark.parametrize(
    "phrase",
    [
        "Je vais vraiment a Bouake",       # "vraiment" contient "ment"
        "Comment vas-tu",                  # "Comment" contient "ment"
        "Mont Blanc est belle",            # "Mont" matchait directement
        "Tu mens beaucoup",                # "mens" matchait directement
        "Il mene une vie tranquille",      # "mene" matchait directement (variante "mène")
        "Donne-moi la main droite",        # "main" matchait directement
        "C'est une jolie manne",           # "manne" matchait directement
        "Je m'appele Mont-Tremblant",      # cas compose, "Mont" interne
        "Maintenant je sais",              # "main" en prefixe — word boundary doit bloquer
        "Element important",               # "ment" en suffixe — word boundary doit bloquer
    ],
)
def test_correct_city_names_pas_de_faux_positif(phrase: str):
    """Apres #228, ces phrases ne doivent jamais etre transformees vers 'Man'."""
    result = correct_city_names(phrase)
    # Heuristique simple : on ne doit pas voir apparaitre "Man" en CamelCase
    # qui ne serait pas deja present dans la phrase d'entree.
    if "Man" in phrase:
        # Si Man etait deja dans l'entree, on tolere (cas rare)
        return
    assert "Man" not in result, f"FAUX POSITIF: {phrase!r} -> {result!r}"


# ─────────────────────────────────────────────────────────────────────
# correct_city_names — corrections legitimes preservees
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_text,expected_substring",
    [
        ("abijean est grande", "Abidjan"),
        ("bouake est belle", "Bouaké"),
        ("yamoussoukros est la capitale", "Yamoussoukro"),
        ("korogho est au nord", "Korhogo"),
    ],
)
def test_correct_city_names_corrections_legitimes(input_text: str, expected_substring: str):
    """Les corrections classiques de villes doivent toujours fonctionner."""
    assert expected_substring in correct_city_names(input_text)


# ─────────────────────────────────────────────────────────────────────
# correct_agricultural_terms — sanity check (non touche par #228)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_text,expected_substring",
    [
        ("Je plante du pegole", "période"),
        ("Le paname est mur", "banane"),
        ("Le manioque pousse bien", "manioc"),
        ("J'aime le kakao", "cacao"),
    ],
)
def test_correct_agricultural_terms_corrections_courantes(
    input_text: str, expected_substring: str
):
    """Sanity check : le wrapper agricultural marche toujours apres le fix."""
    assert expected_substring in correct_agricultural_terms(input_text)


# ─────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────


def test_correct_city_names_texte_vide():
    assert correct_city_names("") == ""


def test_correct_agricultural_terms_texte_vide():
    assert correct_agricultural_terms("") == ""


def test_correct_city_names_aucune_correction_necessaire():
    txt = "Hello world, this is a normal text without typos"
    assert correct_city_names(txt) == txt
