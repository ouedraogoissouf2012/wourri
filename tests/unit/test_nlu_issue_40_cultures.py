"""Régressions NLU des cultures validées pour l'issue #40."""

import json
from pathlib import Path

import pytest

from app.services.nlu.concept_extractor import ConceptExtractor
from app.services.nlu.intent_classifier import IntentClassifier
from app.services.nlu.sentence_builder import CULTURE_LABELS, SentenceBuilder

CONFIG_PATH = Path(__file__).parents[2] / "dictionnaires" / "nlu_concepts.json"
CORPUS_PATH = Path(__file__).parents[2] / "dictionnaires" / "corpus_ivr.json"
AUDIT_PATH = Path(__file__).parents[2] / "data" / "issue_40_source_audit.json"
DRAFT_PATH = (
    Path(__file__).parents[2] / "data" / "issue_40_corpus_validation_draft.json"
)
VALIDATION_PATH = (
    Path(__file__).parents[2] / "data" / "issue_40_native_validation_2026-07-29.json"
)


@pytest.fixture(scope="module")
def nlu_components():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return (
        config,
        ConceptExtractor(config),
        IntentClassifier(config["intents"]),
        SentenceBuilder(),
    )


@pytest.mark.parametrize(
    ("text", "expected_concept", "expected_label"),
    (
        ("N bɛ sɔ̀mɔ sɛnɛ", "CULTURE_ANACARDE", "anacarde"),
        ("N bɛ sɔmɔ sɛnɛ", "CULTURE_ANACARDE", "anacarde"),
        ("Je veux planter des noix de cajou", "CULTURE_ANACARDE", "anacarde"),
        ("N bɛ ntèntulu sɛnɛ", "CULTURE_PALMIER_HUILE", "palmier à huile"),
        ("N bɛ ntentulu sɛnɛ", "CULTURE_PALMIER_HUILE", "palmier à huile"),
        (
            "Je veux planter du palmier à huile",
            "CULTURE_PALMIER_HUILE",
            "palmier à huile",
        ),
        ("N bɛ mana su sɛnɛ", "CULTURE_HEVEA", "hévéa"),
        ("N bɛ mána yiri sɛnɛ", "CULTURE_HEVEA", "hévéa"),
        ("Je veux planter de l'hévéa", "CULTURE_HEVEA", "hévéa"),
    ),
)
def test_validated_crop_terms_reach_sentence_builder(
    nlu_components,
    text: str,
    expected_concept: str,
    expected_label: str,
):
    _, extractor, classifier, builder = nlu_components

    concepts = extractor.extract(text)
    intent, confidence, matched_data = classifier.classify(concepts)
    sentence = builder.build(intent, concepts, matched_data)

    assert concepts[expected_concept] == 1.0
    assert intent == "QUESTION_SAISON_PLANTATION"
    assert confidence >= 0.2
    assert expected_label in sentence


def test_sentence_builder_labels_cover_every_configured_culture(nlu_components):
    config, _, _, _ = nlu_components
    configured = {name for name in config["concepts"] if name.startswith("CULTURE_")}

    assert configured <= set(CULTURE_LABELS)


def test_corpus_only_uses_configured_intents(nlu_components):
    config, _, _, _ = nlu_components
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    configured = {intent["name"] for intent in config["intents"]} | {"_FALLBACK"}
    used = {entry["intent"] for entry in corpus["entries"]}

    assert used <= configured


def test_native_validation_audit_matches_nlu_scope(nlu_components):
    config, _, _, _ = nlu_components
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    decisions = {item["concept"]: item["decision"] for item in audit["terms"]}

    assert decisions["CULTURE_ANACARDE"] == "accepted"
    assert decisions["CULTURE_PALMIER_HUILE"] == "accepted_exactly_as_native_validation"
    assert decisions["CULTURE_HEVEA"] == "accepted_synonyms"
    assert "CULTURE_ANACARDE" in config["concepts"]
    assert "CULTURE_PALMIER_HUILE" in config["concepts"]
    assert "CULTURE_HEVEA" in config["concepts"]


def test_35_native_validated_items_are_promoted_exactly():
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    items = draft["items"]
    counts = {
        culture: sum(item["culture"] == culture for item in items)
        for culture in ("CULTURE_ANACARDE", "CULTURE_PALMIER_HUILE")
    }
    production = {entry["id"]: entry for entry in corpus["entries"]}
    corrections = validation["corrections"]

    assert draft["status"] == "native_validation_completed"
    assert validation["status"] == "validated"
    assert validation["summary"]["validated_total"] == 35
    assert counts == {
        "CULTURE_ANACARDE": 20,
        "CULTURE_PALMIER_HUILE": 15,
    }
    assert all(item["status"] == "pending_native_validation" for item in items)
    assert corpus["version"] == "2.4"
    assert len(corpus["entries"]) == 197

    for item in items:
        promoted = production[item["id"]]
        expected_dioula = corrections.get(item["id"], item["dioula_draft"])
        assert promoted["intent"] == item["intent"]
        assert promoted["cultures"] == [item["culture"]]
        assert promoted["reponse_bambara"] == expected_dioula
        assert promoted["reponse_fr"] == item["french"]
        assert promoted["score_validation"] == 1.0
        assert promoted["source"] == item["source"]


def test_hevea_synonyms_are_nlu_only_until_responses_are_validated(nlu_components):
    config, extractor, _, _ = nlu_components
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    assert "CULTURE_HEVEA" in config["concepts"]
    assert extractor.extract("N bɛ mana su sɛnɛ")["CULTURE_HEVEA"] == 1.0
    assert extractor.extract("N bɛ mána yiri sɛnɛ")["CULTURE_HEVEA"] == 1.0
    assert not any(
        "CULTURE_HEVEA" in entry.get("cultures", [])
        for entry in corpus["entries"]
    )


def test_hevea_mana_su_does_not_match_mana_surunya(nlu_components):
    _, extractor, _, _ = nlu_components

    concepts = extractor.extract(
        "Samiya mana surunya, Bakari b'a ka foro labɛn."
    )

    assert "CULTURE_HEVEA" not in concepts
