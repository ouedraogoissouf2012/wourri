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
    assert decisions["CULTURE_HEVEA"] == "not_implemented"
    assert "CULTURE_ANACARDE" in config["concepts"]
    assert "CULTURE_PALMIER_HUILE" in config["concepts"]
    assert "CULTURE_HEVEA" not in config["concepts"]


def test_corpus_drafts_stay_out_of_production_until_native_validation():
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    items = draft["items"]
    counts = {
        culture: sum(item["culture"] == culture for item in items)
        for culture in ("CULTURE_ANACARDE", "CULTURE_PALMIER_HUILE")
    }
    production_ids = {entry["id"] for entry in corpus["entries"]}

    assert draft["status"] == "pending_native_validation"
    assert counts == {
        "CULTURE_ANACARDE": 20,
        "CULTURE_PALMIER_HUILE": 15,
    }
    assert all(item["status"] == "pending_native_validation" for item in items)
    assert production_ids.isdisjoint(item["id"] for item in items)


def test_hevea_remains_deferred(nlu_components):
    config, extractor, _, _ = nlu_components

    assert "CULTURE_HEVEA" not in config["concepts"]
    assert not any(
        name.startswith("CULTURE_HEVEA")
        for name in extractor.extract("Je veux planter de l'hévéa")
    )
