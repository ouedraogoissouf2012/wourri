"""Traçabilité de la validation native des cinq réponses arachide (#51)."""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
VALIDATION_PATH = PROJECT_ROOT / "data" / "issue_51_native_validation_2026-08-02.json"
DRAFT_PATH = (
    PROJECT_ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_full_draft.json"
)
PRODUCTION_PATH = PROJECT_ROOT / "dictionnaires" / "corpus_ivr.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_five_choice_c_responses_are_recorded_exactly_in_v3_draft():
    validation = _load(VALIDATION_PATH)
    draft = _load(DRAFT_PATH)
    entries = {entry["id"]: entry for entry in draft["entries"]}

    assert validation["issue"] == 51
    assert validation["status"] == "validated"
    assert validation["selected_choice"] == "C"
    assert validation["summary"]["validated_total"] == 5
    assert len(validation["corrections"]) == 5

    for entry_id, expected_response in validation["corrections"].items():
        assert entries[entry_id]["reponse_bambara"] == expected_response
        assert entries[entry_id]["score_validation"] == 1.0


def test_validated_responses_follow_issue_51_form_constraints():
    responses = _load(VALIDATION_PATH)["corrections"].values()

    for response in responses:
        sentences = [
            part.strip() for part in re.split(r"[.!?]+", response) if part.strip()
        ]
        assert len(sentences) <= 3
        assert all(len(sentence.split()) <= 15 for sentence in sentences)
        assert "ti ga" in response.lower()
        assert "waati" not in response.lower()
        assert "karo" not in response.lower()
        assert "sugu" not in response.lower()


def test_terms_left_for_oral_confirmation_are_explicitly_confirmed():
    validation = _load(VALIDATION_PATH)

    # Aligné sur le PDF FINAL du validateur natif (#328 avait mergé une
    # PRÉ-version). Termes finaux attestés : « Tulu dilanyɔrɔw » (huileries),
    # « jibolisira » (canal d'écoulement / drainage), « fɔsifati » (phosphate).
    confirmed = validation["confirmed_terms"]
    assert confirmed["Tulu dilanyɔrɔw"] == "huileries"
    assert confirmed["jibolisira"] == "canal d'écoulement / drainage"
    assert confirmed["fɔsifati"] == "phosphate"
    assert "Tulu dilanyɔrɔw" in validation["corrections"]["arachide_vente_001"]
    assert "jibolisira" in validation["corrections"]["arachide_diagnostic_001"]
    assert "fɔsifati" in validation["corrections"]["arachide_engrais_001"]


def test_adr_0014_keeps_the_validated_slice_out_of_production():
    validation = _load(VALIDATION_PATH)
    production = _load(PRODUCTION_PATH)
    production_entries = {entry["id"]: entry for entry in production["entries"]}

    assert validation["production_policy"] == "archive_only_per_adr_0014"
    assert validation["target"] == "dictionnaires/archive/corpus_ivr_v3_full_draft.json"
    assert production["version"] == "2.4"
    assert all(
        production_entries[entry_id]["reponse_bambara"] != validated_response
        for entry_id, validated_response in validation["corrections"].items()
    )
