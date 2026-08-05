"""Traçabilité de la validation native des 13 cultures corpus v3 (#56-#68).

coton, banane, tomate, haricot, gombo, oignon, patate, sésame, café, ananas,
mangue, néré, agrumes. Même contrat que les cultures précédentes (#51-#54) :
les corrections natives sont enregistrées exactement dans le draft v3 archivé,
et ne fuient JAMAIS en production (ADR-0014).

Note forme : le locuteur natif fait autorité (règle projet). Le compte de
phrases tolère jusqu'à 4 phrases courtes et compte « ; » comme séparateur
interne — deux corrections natives (mangue, agrumes) l'exploitent légitimement.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
DRAFT = ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_full_draft.json"
PROD = ROOT / "dictionnaires" / "corpus_ivr.json"

VALIDATION_FILES = sorted(
    (ROOT / "data").glob("issue_*_native_validation_2026-08-05.json")
)

BANNED_TERMS = ["sugu", "karo", "waati", "kosɛbɛ"]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_validations():
    return [_load(f) for f in VALIDATION_FILES]


def test_thirteen_validation_files_present():
    assert len(VALIDATION_FILES) == 13


@pytest.mark.parametrize("validation", _all_validations(), ids=lambda v: v["summary"]["culture"])
def test_corrections_recorded_exactly_in_draft(validation):
    draft = _load(DRAFT)
    entries = {e["id"]: e for e in draft["entries"]}

    assert validation["status"] == "validated"
    assert validation["selected_choice"] == "C"
    assert validation["production_policy"] == "archive_only_per_adr_0014"

    for entry_id, expected in validation["corrections"].items():
        assert entry_id in entries, f"{entry_id} absent du draft"
        assert entries[entry_id]["reponse_bambara"] == expected
        assert entries[entry_id]["score_validation"] == 1.0


@pytest.mark.parametrize("validation", _all_validations(), ids=lambda v: v["summary"]["culture"])
def test_corrections_follow_form_and_banned_terms(validation):
    for text in validation["corrections"].values():
        # « ; » compté comme séparateur interne (choix natif) ; ≤4 phrases courtes.
        sentences = [s.strip() for s in re.split(r"[.!?;]+", text) if s.strip()]
        assert len(sentences) <= 4
        for banned in BANNED_TERMS:
            assert banned not in text.lower()


@pytest.mark.parametrize("validation", _all_validations(), ids=lambda v: v["summary"]["culture"])
def test_adr_0014_corrections_absent_from_production(validation):
    production = _load(PROD)
    prod_entries = {e["id"]: e for e in production["entries"]}

    assert production["version"] == "2.4"
    assert all(
        prod_entries[entry_id]["reponse_bambara"] != validated
        for entry_id, validated in validation["corrections"].items()
        if entry_id in prod_entries
    )
