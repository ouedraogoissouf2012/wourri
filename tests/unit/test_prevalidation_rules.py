"""Tests du noyau de prévalidation dioula CI (scripts/prevalidation_rules.py).

Couvre :
  * structure des tables (§3.1, §3.2, §3.3, §4.7) ;
  * `calculate_confidence` : formule, bornes des sous-scores, PLAFONDS (jamais
    au-dessus de 0.89, plafonds spécifiques de §6) ;
  * normalisation orthographique : n'agit QUE sur les mots de la table, jamais
    de regex générale (les voyelles longues légitimes sont préservées) ;
  * substitutions lexicales conditionnelles : appliquées seulement si le sens
    français lève l'ambiguïté ;
  * faux-amis : signalés, JAMAIS remplacés ;
  * validateur JSON : accepte le format §7, rejette les cas invalides.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Le module vit dans scripts/ (hors package). On l'ajoute au path comme le
# fait déjà conftest pour la racine projet.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import prevalidation_rules as pr  # noqa: E402


# ---------------------------------------------------------------------------
# Structure des tables
# ---------------------------------------------------------------------------


def test_lexical_substitutions_are_well_formed():
    seen_ids = set()
    for rule in pr.LEXICAL_SUBSTITUTIONS:
        assert rule.rule_id and rule.rule_id not in seen_ids
        seen_ids.add(rule.rule_id)
        assert rule.source_form
        assert rule.wouri_form
        assert isinstance(rule.conditional, bool)
        assert isinstance(rule.french_triggers, tuple)
        # Une règle conditionnelle DOIT fournir au moins un déclencheur FR,
        # sinon elle ne pourrait jamais s'appliquer de façon déterministe.
        if rule.conditional:
            assert rule.french_triggers, rule.rule_id
        else:
            assert rule.french_triggers == ()


def test_sugu_and_kosebe_are_conditional_not_absolute():
    """§3.1 : sugu et kosɛbɛ ne sont PAS bannis absolus, mais conditionnels."""
    by_form = {r.source_form: r for r in pr.LEXICAL_SUBSTITUTIONS}
    assert by_form["sugu"].conditional is True
    assert by_form["kosɛbɛ"].conditional is True
    # Les formes maliennes sans sens CI alternatif restent inconditionnelles.
    assert by_form["karo"].conditional is False
    assert by_form["waati"].conditional is False


def test_orthographic_map_targets_are_shorter_or_canonical():
    for bad, entry in pr.ORTHOGRAPHIC_MAP.items():
        assert entry["rule_id"]
        assert entry["target"]
        # La cible ne contient jamais de voyelle triplée résiduelle.
        assert not re.search(r"([aeiouɛɔ])\1{2,}", entry["target"], re.IGNORECASE)


def test_semantic_rejections_actions_are_valid():
    for rej in pr.SEMANTIC_REJECTIONS:
        assert rej.form
        assert rej.action in {"reject", "flag"}
        assert rej.attested_sense


def test_months_glossary_uses_ascii_french_keys():
    for fr, dyu in pr.MONTHS_GLOSSARY.items():
        assert fr == pr._strip_accents(fr).lower()
        assert dyu


# ---------------------------------------------------------------------------
# §6 — calculate_confidence : formule, bornes, plafonds
# ---------------------------------------------------------------------------


def test_confidence_perfect_scores_are_capped_at_089():
    """Même avec tous les sous-scores à 1, le score plafonne à 0.89."""
    score = pr.calculate_confidence(S=1, G=1, Y=1, O=1, A=1, E=1)
    assert score == 0.89


def test_confidence_never_exceeds_hard_cap_across_grid():
    grid = (0.0, 0.25, 0.5, 0.75, 1.0)
    for S in grid:
        for G in grid:
            for Y in grid:
                for O in grid:
                    for A in grid:
                        score = pr.calculate_confidence(S=S, G=G, Y=Y, O=O, A=A, E=1.0)
                        assert score <= pr.HARD_CAP


def test_confidence_matches_formula_before_cap():
    # Sous-scores bas pour rester sous le plafond et vérifier la formule exacte.
    S, G, E, Y, O, A = 0.5, 0.5, 0.5, 0.5, 0.5, 0.5
    expected = 0.25 * S + 0.20 * G + 0.15 * E + 0.15 * Y + 0.10 * O + 0.15 * A
    score = pr.calculate_confidence(S=S, G=G, Y=Y, O=O, A=A, E=E)
    assert score == pytest.approx(round(expected, 4))


def test_confidence_specific_caps_apply():
    high = dict(S=1, G=1, Y=1, O=1, A=1, E=1)

    assert pr.calculate_confidence(
        **high, caps=pr.ConfidenceCaps(unconfirmed_technical_term=True)
    ) == pytest.approx(0.74)
    assert pr.calculate_confidence(
        **high, caps=pr.ConfidenceCaps(source_contradiction=True)
    ) == pytest.approx(0.64)
    assert pr.calculate_confidence(
        **high, caps=pr.ConfidenceCaps(unverified_agronomy=True)
    ) == pytest.approx(0.59)
    assert pr.calculate_confidence(
        **high, caps=pr.ConfidenceCaps(pesticide_without_dosage=True)
    ) == pytest.approx(0.49)
    assert pr.calculate_confidence(
        **high, caps=pr.ConfidenceCaps(possible_contresens=True)
    ) == pytest.approx(0.39)


def test_confidence_most_constraining_cap_wins():
    high = dict(S=1, G=1, Y=1, O=1, A=1, E=1)
    score = pr.calculate_confidence(
        **high,
        caps=pr.ConfidenceCaps(
            unconfirmed_technical_term=True, possible_contresens=True
        ),
    )
    assert score == pytest.approx(0.39)


def test_confidence_rejects_out_of_range_subscore():
    with pytest.raises(ValueError):
        pr.calculate_confidence(S=1.5, G=1, Y=1, O=1, A=1)
    with pytest.raises(ValueError):
        pr.calculate_confidence(S=-0.1, G=1, Y=1, O=1, A=1)


# ---------------------------------------------------------------------------
# §3.2 — normalisation orthographique : table seulement, pas de regex générale
# ---------------------------------------------------------------------------


def test_orthographic_map_corrects_only_table_words():
    res = pr.apply_orthographic_map("Aw ye foroo labɛn")
    assert "foro" in res.text
    assert "foroo" not in res.text
    assert any("ORTH-FIELD-001" in r for r in res.applied_rules)


def test_orthographic_map_preserves_legitimate_long_vowels():
    """Les voyelles longues linguistiques ne sont JAMAIS touchées."""
    for legit in ("naani", "duuru", "wɔɔrɔ", "bɛɛ", "joona", "dɔɔni"):
        res = pr.apply_orthographic_map(f"a {legit} b")
        assert legit in res.text, legit
        assert res.applied_rules == []


def test_orthographic_map_is_case_aware_for_months():
    res = pr.apply_orthographic_map("Mɛɛɛ")
    assert res.text == "Mɛ"


def test_orthographic_map_does_not_touch_preserved_sigles():
    res = pr.apply_orthographic_map("NPK 15-15-15 don ANADER fɛ")
    assert "NPK" in res.text
    assert "ANADER" in res.text
    assert res.applied_rules == []


# ---------------------------------------------------------------------------
# §3.1 — substitutions lexicales conditionnelles
# ---------------------------------------------------------------------------


def test_conditional_substitution_applies_when_french_sense_is_clear():
    res = pr.apply_lexical_substitutions(
        "sugu la", french_reference="au marché du village"
    )
    assert "lɔgɔ" in res.text
    assert "sugu" not in res.text
    assert any("LEX-MARKET-001" in r for r in res.applied_rules)
    assert res.to_confirm == []


def test_conditional_substitution_deferred_when_sense_unclear():
    res = pr.apply_lexical_substitutions(
        "nyɔ sugu caman", french_reference="plusieurs sortes de mil"
    )
    # Pas de « marché » en français → on ne substitue PAS, on signale.
    assert "sugu" in res.text
    assert not any("LEX-MARKET-001" in r for r in res.applied_rules)
    assert any("sugu" in t for t in res.to_confirm)


def test_unconditional_substitution_always_applies():
    res = pr.apply_lexical_substitutions("karo fila", french_reference="deux mois")
    assert "kalo" in res.text
    assert "karo" not in res.text
    assert any("LEX-MONTH-001" in r for r in res.applied_rules)


# ---------------------------------------------------------------------------
# §3.3 — faux-amis : signalés, jamais remplacés
# ---------------------------------------------------------------------------


def test_semantic_alerts_flag_but_do_not_modify_text():
    text = "kulun bɛ foro la"
    alerts = pr.detect_semantic_alerts(text)
    forms = {a["form"] for a in alerts}
    assert "kulun" in forms
    reject = next(a for a in alerts if a["form"] == "kulun")
    assert reject["action"] == "reject"
    assert reject["attested_sense"] == "pirogue"


def test_semantic_alerts_empty_when_no_false_friend():
    assert pr.detect_semantic_alerts("nyɔ bɛ ji fɛ") == []


# ---------------------------------------------------------------------------
# §7.3 — validateur JSON
# ---------------------------------------------------------------------------


def _valid_proposition() -> dict:
    return {
        "entry_id": "mil_conseil_001",
        "french_reference": "Pour bien cultiver le mil…",
        "proposition_dioula_ci": "Aw ye nyɔ sɛnɛ.",
        "regles_appliquees": ["ORTH-FIELD-001:foroo→foro"],
        "termes_a_confirmer": ["da pour planter le mil"],
        "confiance": 0.74,
        "necessite_validation_native": True,
        "note_pour_le_natif": "Confirmer si tugun ou tunkun pour la butte.",
    }


def test_schema_accepts_valid_proposition():
    pr.validate_proposition(_valid_proposition())  # ne lève pas


def test_schema_rejects_confidence_above_089():
    bad = _valid_proposition()
    bad["confiance"] = 0.95
    with pytest.raises(pr.SchemaValidationError):
        pr.validate_proposition(bad)


def test_schema_rejects_native_validation_false():
    bad = _valid_proposition()
    bad["necessite_validation_native"] = False
    with pytest.raises(pr.SchemaValidationError):
        pr.validate_proposition(bad)


def test_schema_rejects_missing_required_field():
    bad = _valid_proposition()
    del bad["entry_id"]
    with pytest.raises(pr.SchemaValidationError):
        pr.validate_proposition(bad)


def test_schema_rejects_additional_property():
    bad = _valid_proposition()
    bad["extra"] = "nope"
    with pytest.raises(pr.SchemaValidationError):
        pr.validate_proposition(bad)


def test_schema_rejects_wrong_type():
    bad = _valid_proposition()
    bad["regles_appliquees"] = "should be a list"
    with pytest.raises(pr.SchemaValidationError):
        pr.validate_proposition(bad)


def test_schema_rejects_empty_string_field():
    bad = _valid_proposition()
    bad["proposition_dioula_ci"] = ""
    with pytest.raises(pr.SchemaValidationError):
        pr.validate_proposition(bad)
