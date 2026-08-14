"""Contrats directs du NLU Bambara/Dioula fondés sur le lexique versionné."""
import json
from pathlib import Path

import pytest

from app.services.nlu.concept_extractor import ConceptExtractor
from app.services.nlu.intent_classifier import IntentClassifier


@pytest.fixture(scope="module")
def nlu_config():
    """Charge la même configuration que le service NLU de production."""
    config_path = (
        Path(__file__).resolve().parents[2]
        / "dictionnaires"
        / "nlu_concepts.json"
    )
    return json.loads(config_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def extractor(nlu_config):
    return ConceptExtractor(nlu_config)


@pytest.mark.parametrize(
    ("phrase", "expected_concept"),
    [
        ("n bɛ malo sɛnɛ", "CULTURE_RIZ"),
        ("n bɛ kaba sɛnɛ", "CULTURE_MAIS"),
        ("n bɛ nyɔ sɛnɛ", "CULTURE_MIL"),
        ("n bɛ tiga sɛnɛ", "CULTURE_ARACHIDE"),
        ("n bɛ ku sɛnɛ", "CULTURE_IGNAME"),
        ("n bɛ bananku sɛnɛ", "CULTURE_MANIOC"),
        ("n bɛ soso sɛnɛ", "CULTURE_HARICOT"),
        ("n bɛ kɔrɔni sɛnɛ", "CULTURE_COTON"),
        ("n bɛ bɛnɛ sɛnɛ", "CULTURE_SESAME"),
        ("n bɛ namasa sɛnɛ", "CULTURE_BANANE"),
        ("n bɛ tomati sɛnɛ", "CULTURE_TOMATE"),
        ("n bɛ jaba sɛnɛ", "CULTURE_OIGNON"),
        ("n bɛ woso sɛnɛ", "CULTURE_PATATE"),
        ("n bɛ gan sɛnɛ", "CULTURE_GOMBO"),
        ("n bɛ kakawo sɛnɛ", "CULTURE_CACAO"),
        ("n bɛ kafe sɛnɛ", "CULTURE_CAFE"),
        ("n bɛ anana sɛnɛ", "CULTURE_ANANAS"),
        ("n bɛ maŋoro sɛnɛ", "CULTURE_MANGUE"),
        ("n bɛ lemuru sɛnɛ", "CULTURE_AGRUMES"),
        ("n bɛ nɛrɛ sɛnɛ", "CULTURE_NERE"),
    ],
)
def test_concept_extractor_recognizes_20_known_bambara_phrases(
    extractor,
    phrase,
    expected_concept,
):
    """Chaque culture connue doit être extraite d'une phrase Bambara simple."""
    concepts = extractor.extract(phrase)

    assert expected_concept in concepts
    assert concepts[expected_concept] == 1.0
    assert "ACTION_PLANTER" in concepts


@pytest.mark.parametrize(
    ("concepts", "expected_intent"),
    [
        (
            {"CULTURE_RIZ": 1.0, "ACTION_PLANTER": 1.0},
            "QUESTION_SAISON_PLANTATION",
        ),
        (
            {"CULTURE_MAIS": 1.0, "PROBLEME_INSECTE": 1.0},
            "DIAGNOSTIC_PROBLEME",
        ),
        (
            {"CULTURE_RIZ": 1.0, "ACTION_RECOLTER": 1.0},
            "QUESTION_RECOLTE",
        ),
        (
            {"CULTURE_MAIS": 1.0, "ACTION_ARROSER": 1.0},
            "QUESTION_IRRIGATION",
        ),
        (
            {"CULTURE_RIZ": 1.0, "ENGRAIS_FERTILISANT": 1.0},
            "QUESTION_ENGRAIS",
        ),
        (
            {"CULTURE_MAIS": 1.0, "ACTION_STOCKER": 1.0},
            "QUESTION_STOCKAGE",
        ),
        (
            {"CULTURE_RIZ": 1.0, "ACTION_VENDRE": 1.0},
            "QUESTION_VENTE",
        ),
        ({"CULTURE_MAIS": 1.0}, "CONSEIL_PRODUCTION"),
        ({"SALUTATION": 1.0}, "SALUTATION_SEULE"),
        ({}, "HORS_SUJET"),
    ],
)
def test_intent_classifier_handles_10_agricultural_scenarios(
    nlu_config,
    concepts,
    expected_intent,
):
    """Riz, maïs et hors-sujet suivent les intentions métier configurées."""
    classifier = IntentClassifier(nlu_config["intents"])

    intent, confidence, _ = classifier.classify(concepts)

    assert intent == expected_intent
    assert 0.0 <= confidence <= 1.0


@pytest.mark.parametrize("phrase", ["sini sanji bɛna na wa", "sini"])
def test_concept_extractor_recognizes_temps_demain(extractor, phrase):
    """Issue #355 — 'sini' (demain) est reconnu comme concept temporel.

    'sini' est deja atteste dans corpus_ivr.json (arachide_saison_001).
    Concept de reconnaissance uniquement : aucune reponse dioula n'est
    generee a partir de ce concept sans validation native (ADR-0014).
    """
    concepts = extractor.extract(phrase)

    assert "TEMPS_DEMAIN" in concepts
