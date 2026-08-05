"""Traçabilité de la validation native des cultures igname (#52), manioc (#53)
et cacao (#54). Même contrat que le test arachide (#51) : les corrections
natives sont enregistrées exactement dans le draft v3 archivé, respectent les
contraintes de forme, et NE fuient JAMAIS en production (ADR-0014).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
DRAFT_PATH = (
    PROJECT_ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_full_draft.json"
)
PRODUCTION_PATH = PROJECT_ROOT / "dictionnaires" / "corpus_ivr.json"

# (issue, culture, nombre d'entrées validées par le formulaire natif)
CASES = [
    (52, "CULTURE_IGNAME", 8),
    (53, "CULTURE_MANIOC", 8),
    (54, "CULTURE_CACAO", 8),
]

# Termes bannis par les règles dioula CI du projet (formes maliennes / erronées).
# Formes maliennes sans sens alternatif attesté en dioula CI (toujours à éviter).
# `sugu`/`kosɛbɛ` retirés : attestés dans un sens valide par le lexique CI
# Mandenkan (sorte/espèce ; beaucoup). Règle WOURI conditionnelle au sens, pas
# au mot — et le natif fait autorité.
BANNED_TERMS = ["waati", "karo"]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validation_path(issue: int) -> Path:
    return PROJECT_ROOT / "data" / f"issue_{issue}_native_validation_2026-08-02.json"


@pytest.mark.parametrize("issue, culture, total", CASES)
def test_choice_c_responses_are_recorded_exactly_in_v3_draft(issue, culture, total):
    validation = _load(_validation_path(issue))
    draft = _load(DRAFT_PATH)
    entries = {entry["id"]: entry for entry in draft["entries"]}

    assert validation["issue"] == issue
    assert validation["status"] == "validated"
    assert validation["selected_choice"] == "C"
    assert validation["summary"]["culture"] == culture
    assert validation["summary"]["validated_total"] == total
    assert len(validation["corrections"]) == total

    for entry_id, expected_response in validation["corrections"].items():
        assert entries[entry_id]["reponse_bambara"] == expected_response
        assert entries[entry_id]["score_validation"] == 1.0


@pytest.mark.parametrize("issue, culture, total", CASES)
def test_validated_responses_follow_form_constraints(issue, culture, total):
    responses = _load(_validation_path(issue))["corrections"].values()

    for response in responses:
        sentences = [
            part.strip() for part in re.split(r"[.!?]+", response) if part.strip()
        ]
        assert len(sentences) <= 3
        assert all(len(sentence.split()) <= 15 for sentence in sentences)
        for banned in BANNED_TERMS:
            assert banned not in response.lower()


@pytest.mark.parametrize("issue, culture, total", CASES)
def test_adr_0014_keeps_the_validated_slice_out_of_production(issue, culture, total):
    validation = _load(_validation_path(issue))
    production = _load(PRODUCTION_PATH)
    production_entries = {entry["id"]: entry for entry in production["entries"]}

    assert validation["production_policy"] == "archive_only_per_adr_0014"
    assert validation["target"] == "dictionnaires/archive/corpus_ivr_v3_full_draft.json"
    assert production["version"] == "2.4"
    assert all(
        production_entries[entry_id]["reponse_bambara"] != validated_response
        for entry_id, validated_response in validation["corrections"].items()
    )


def test_manioc_formerly_pending_entries_now_validated():
    """Historique : le 1er PDF #53 ne couvrait que 8 des 11 entrées manioc ;
    les 3 restantes (conseil/saison/recolte) étaient listées comme
    `not_covered_pending_validation`. Elles ont depuis été validées nativement
    (lot final 2026-08-05b) → le manioc est désormais complet (100 %). Ce test
    verrouille cet aboutissement : les 3 entrées jadis en attente sont à 1.0.
    """
    validation = _load(_validation_path(53))
    draft = _load(DRAFT_PATH)
    entries = {entry["id"]: entry for entry in draft["entries"]}

    formerly_pending = validation["not_covered_pending_validation"]
    assert set(formerly_pending) == {
        "manioc_conseil_001",
        "manioc_saison_001",
        "manioc_recolte_001",
    }
    # Désormais validées nativement (lot final).
    for entry_id in formerly_pending:
        assert entries[entry_id]["score_validation"] == 1.0
