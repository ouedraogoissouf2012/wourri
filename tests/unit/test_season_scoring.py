"""Tests du module métier partagé `app.services.corpus.season_scoring`.

Ce module centralise la logique saison + scoring auparavant DUPLIQUÉE verbatim
entre le backend Chroma (vdb_service._best_result) et pgvector
(corpus_service._best_result_pg). Ces tests verrouillent le comportement EXACT
d'origine (zéro régression) : mêmes mois de saison, mêmes poids, même gestion
des conditions vides (Chroma stocke les conditions en CSV → `"".split(",")`
produit `[""]`, pgvector produit `[]` ; les deux doivent donner « neutre »).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.corpus import season_scoring as ss


# ---------------------------------------------------------------------------
# get_current_season : calendrier agricole CI (mars-juin + sep-oct = pluie)
# ---------------------------------------------------------------------------

RAINY = "saison_pluie"
DRY = "saison_seche"


@pytest.mark.parametrize(
    "month, expected",
    [
        (1, DRY), (2, DRY),
        (3, RAINY), (4, RAINY), (5, RAINY), (6, RAINY),
        (7, DRY), (8, DRY),
        (9, RAINY), (10, RAINY),
        (11, DRY), (12, DRY),
    ],
)
def test_season_for_each_month(month, expected):
    assert ss.get_current_season(datetime(2026, month, 15)) == expected


def test_season_constants_values():
    """Les noms de saison exposés sont exactement ceux utilisés en base."""
    assert ss.SEASON_RAINY == RAINY
    assert ss.SEASON_DRY == DRY
    assert ss.RAINY_MONTHS == frozenset({3, 4, 5, 6, 9, 10})


def test_scoring_weights_values():
    """Poids figés = valeurs historiques des 2 backends (vdb_service/corpus_service)."""
    assert ss.SEASON_MATCH_BONUS == 0.15
    assert ss.SEASON_MISMATCH_PENALTY == 0.05
    assert ss.EXPLICIT_CONDITION_BONUS == 0.05
    assert ss.DEFAULT_VALIDATION_SCORE == 0.5


# ---------------------------------------------------------------------------
# score_entry : reproduction exacte de la logique d'origine
# ---------------------------------------------------------------------------

def test_no_conditions_is_neutral_pgvector_style():
    """Entrée sans contrainte (pgvector : []) → score inchangé (neutre)."""
    score = ss.score_entry(0.8, entry_conditions=[], query_conditions=[], season=RAINY)
    assert score == pytest.approx(0.8)


def test_no_conditions_is_neutral_chroma_style():
    """Entrée sans contrainte (Chroma : `"".split(",")` == ['']) → neutre.

    C'est le cas piège : la chaîne vide ne doit PAS être comptée comme une
    condition saisonnière absente qui déclencherait la pénalité.
    """
    score = ss.score_entry(0.8, entry_conditions=[""], query_conditions=[], season=RAINY)
    assert score == pytest.approx(0.8)


def test_season_match_bonus():
    score = ss.score_entry(
        0.7, entry_conditions=["saison_pluie"], query_conditions=[], season=RAINY
    )
    assert score == pytest.approx(0.7 + 0.15)


def test_season_mismatch_penalty():
    """L'entrée a une contrainte saisonnière qui ne matche pas → pénalité."""
    score = ss.score_entry(
        0.7, entry_conditions=["saison_seche"], query_conditions=[], season=RAINY
    )
    assert score == pytest.approx(0.7 - 0.05)


def test_explicit_condition_bonus():
    score = ss.score_entry(
        0.6,
        entry_conditions=["irrigation"],
        query_conditions=["irrigation"],
        season=RAINY,
    )
    # pas de contrainte saisonnière dans l'entrée → neutre côté saison,
    # +0.05 pour la condition explicite matchée
    assert score == pytest.approx(0.6 + 0.05)


def test_season_and_explicit_condition_combine():
    score = ss.score_entry(
        0.5,
        entry_conditions=["saison_pluie", "irrigation"],
        query_conditions=["irrigation"],
        season=RAINY,
    )
    assert score == pytest.approx(0.5 + 0.15 + 0.05)


def test_multiple_explicit_conditions():
    score = ss.score_entry(
        0.5,
        entry_conditions=["irrigation", "engrais"],
        query_conditions=["irrigation", "engrais"],
        season=RAINY,
    )
    assert score == pytest.approx(0.5 + 0.05 + 0.05)


def test_query_condition_not_in_entry_no_bonus():
    score = ss.score_entry(
        0.5,
        entry_conditions=["irrigation"],
        query_conditions=["engrais"],
        season=RAINY,
    )
    assert score == pytest.approx(0.5)


def test_empty_query_condition_ignored():
    """Une condition de requête vide ('') ne doit jamais donner de bonus."""
    score = ss.score_entry(
        0.5,
        entry_conditions=[""],
        query_conditions=[""],
        season=RAINY,
    )
    assert score == pytest.approx(0.5)


def test_mismatch_penalty_only_when_seasonal_constraint_present():
    """Pénalité UNIQUEMENT si l'entrée porte une contrainte saisonnière.

    Entrée = ['irrigation'] (aucune saison) + season=RAINY → neutre, pas -0.05.
    """
    score = ss.score_entry(
        0.9, entry_conditions=["irrigation"], query_conditions=[], season=DRY
    )
    assert score == pytest.approx(0.9)
