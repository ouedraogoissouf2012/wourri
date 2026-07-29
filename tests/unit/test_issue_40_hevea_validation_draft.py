"""Contrats du brouillon hévéa de l'issue #40."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
DRAFT_PATH = ROOT / "data" / "issue_40_hevea_validation_draft.json"
AUDIT_PATH = ROOT / "data" / "issue_40_source_audit.json"
CORPUS_PATH = ROOT / "dictionnaires" / "corpus_ivr.json"
NLU_PATH = ROOT / "dictionnaires" / "nlu_concepts.json"

ALLOWED_INTENTS = {
    "CONSEIL_PRODUCTION",
    "QUESTION_SAISON_PLANTATION",
    "QUESTION_RECOLTE",
    "QUESTION_ENGRAIS",
    "QUESTION_STOCKAGE",
    "QUESTION_VENTE",
    "DIAGNOSTIC_PROBLEME",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_hevea_draft_has_15_unique_source_backed_items():
    draft = load_json(DRAFT_PATH)
    items = draft["items"]
    source_codes = draft["source_codes"]

    assert draft["status"] == "pending_native_validation"
    assert draft["culture"] == "CULTURE_HEVEA"
    assert len(items) == 15
    assert len({item["id"] for item in items}) == 15
    assert all(item["culture"] == "CULTURE_HEVEA" for item in items)
    assert all(item["intent"] in ALLOWED_INTENTS for item in items)
    assert all(item["source"] in source_codes for item in items)
    assert all(
        1 <= item["source_page"] <= source_codes[item["source"]]["pages"]
        for item in items
    )
    assert all(item["status"] == "pending_native_validation" for item in items)
    assert all(item["french"].strip() for item in items)
    assert all(item["dioula_draft"].strip() for item in items)


def test_both_validated_hevea_synonyms_are_used_in_drafts():
    draft = load_json(DRAFT_PATH)
    combined = " ".join(item["dioula_draft"] for item in draft["items"])

    assert draft["validated_crop_terms"] == ["mana su", "mána yiri"]
    assert "mana su" in combined
    assert "mána yiri" in combined


def test_unvalidated_hevea_drafts_are_not_in_production_corpus():
    draft = load_json(DRAFT_PATH)
    corpus = load_json(CORPUS_PATH)
    production_ids = {entry["id"] for entry in corpus["entries"]}

    assert corpus["version"] == draft["production_state"]["corpus_version"]
    assert len(corpus["entries"]) == draft["production_state"]["corpus_entry_count"]
    assert not production_ids.intersection(item["id"] for item in draft["items"])
    assert not any(
        "CULTURE_HEVEA" in entry.get("cultures", [])
        for entry in corpus["entries"]
    )


def test_hevea_nlu_concept_contains_exact_validated_synonyms():
    draft = load_json(DRAFT_PATH)
    nlu = load_json(NLU_PATH)
    keywords = nlu["concepts"]["CULTURE_HEVEA"]["keywords"]

    assert all(term in keywords for term in draft["validated_crop_terms"])


def test_source_audit_exposes_pending_hevea_validation_artifacts():
    audit = load_json(AUDIT_PATH)
    validation = audit["hevea_response_validation"]

    assert validation["draft_file"] == DRAFT_PATH.relative_to(ROOT).as_posix()
    assert validation["draft_count"] == 15
    assert validation["status"] == "pending_native_validation"
    assert validation["production_promotion"] == (
        "forbidden_until_native_validation"
    )
