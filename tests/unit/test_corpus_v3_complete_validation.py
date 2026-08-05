"""Contrat final : le draft v3 est intégralement validé nativement (162/162).

Ce test verrouille l'aboutissement de la validation native dioula CI :
toutes les entrées du draft v3 archivé ont score_validation == 1.0, et les
corrections du lot final (#40/#49/#51/#53/#55 + système) y sont enregistrées
exactement. Conforme ADR-0014 : le draft reste archivé, la prod (v2.4) intacte.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
DRAFT = ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_full_draft.json"
PROD = ROOT / "dictionnaires" / "corpus_ivr.json"

FINAL_VALIDATION_FILES = sorted(
    (ROOT / "data").glob("issue_*_native_validation_2026-08-05b.json")
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_draft_v3_is_fully_native_validated():
    """Aboutissement : 100% des entrées du draft v3 ont score 1.0."""
    draft = _load(DRAFT)
    entries = [e for e in draft["entries"] if isinstance(e, dict)]
    validated = [e for e in entries if e.get("score_validation") == 1.0]
    assert len(validated) == len(entries), (
        f"{len(entries) - len(validated)} entrées non validées : "
        f"{[e['id'] for e in entries if e.get('score_validation') != 1.0]}"
    )


def test_six_final_validation_files_present():
    assert len(FINAL_VALIDATION_FILES) == 6


@pytest.mark.parametrize(
    "validation",
    [_load(f) for f in FINAL_VALIDATION_FILES],
    ids=lambda v: str(v["summary"]["culture"]),
)
def test_final_corrections_recorded_exactly_in_draft(validation):
    draft = _load(DRAFT)
    entries = {e["id"]: e for e in draft["entries"]}

    assert validation["status"] == "validated"
    assert validation["production_policy"] == "archive_only_per_adr_0014"

    for entry_id, expected in validation["corrections"].items():
        assert entry_id in entries, f"{entry_id} absent du draft"
        assert entries[entry_id]["reponse_bambara"] == expected
        assert entries[entry_id]["score_validation"] == 1.0


@pytest.mark.parametrize(
    "validation",
    [_load(f) for f in FINAL_VALIDATION_FILES],
    ids=lambda v: str(v["summary"]["culture"]),
)
def test_final_corrections_absent_from_production(validation):
    """ADR-0014 : rien du draft ne fuit en prod tant que la promotion n'est
    pas décidée (staging + E2E + rollback restent requis)."""
    production = _load(PROD)
    prod_entries = {e["id"]: e for e in production["entries"]}

    assert production["version"] == "2.4"
    assert all(
        prod_entries[entry_id]["reponse_bambara"] != validated
        for entry_id, validated in validation["corrections"].items()
        if entry_id in prod_entries
    )


def test_system_placeholders_preserved():
    """Les messages système conservent leurs placeholders {{METEO_*}}."""
    systeme = next(
        _load(f) for f in FINAL_VALIDATION_FILES
        if str(_load(f)["summary"]["culture"]) == "CULTURE_SYSTEME"
    )
    for entry_id in (
        "salutation_matin_001",
        "salutation_midi_001",
        "salutation_soir_001",
        "salutation_nuit_001",
    ):
        assert "{{METEO_CONTEXTUEL}}" in systeme["corrections"][entry_id]
