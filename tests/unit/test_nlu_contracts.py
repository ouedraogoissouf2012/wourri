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


@pytest.mark.parametrize(
    "phrase",
    ["vas t'il pleuvoir demain", "il va pleuvoir", "est-ce qu'il pleut"],
)
def test_concept_extractor_recognizes_pleuvoir_fr(extractor, phrase):
    """Bug prod 2026-09 : le VERBE 'pleuvoir/pleut' (FR) doit être reconnu comme
    concept pluie — seul le nom 'pluie' l'était, d'où un HORS_SUJET sur 'pleuvoir'."""
    concepts = extractor.extract(phrase)

    assert "TEMPS_SAISON_PLUIE" in concepts


def test_intent_pleuvoir_demain_is_meteo_not_hors_sujet(nlu_config):
    """'pleuvoir demain' → QUESTION_METEO_AGRICOLE (prévision J+1), plus HORS_SUJET."""
    classifier = IntentClassifier(nlu_config["intents"])

    intent, confidence, _ = classifier.classify(
        {"TEMPS_SAISON_PLUIE": 1.0, "TEMPS_DEMAIN": 1.0}
    )

    assert intent == "QUESTION_METEO_AGRICOLE"
    assert 0.0 <= confidence <= 1.0


def test_intent_pure_meteo_is_not_hors_sujet(nlu_config):
    """Cohérence : QUESTION_METEO_AGRICOLE accepte TEMPS_METEO → une question météo
    pure (température/vent) ne doit plus tomber en HORS_SUJET (garde `_has_agricultural`)."""
    classifier = IntentClassifier(nlu_config["intents"])

    intent, _, _ = classifier.classify({"TEMPS_METEO": 1.0})

    assert intent == "QUESTION_METEO_AGRICOLE"


def test_pleuvoir_demain_bout_en_bout(extractor, nlu_config):
    """Reproduction exacte du bug prod : 'vas t'il pleuvoir demain' ne doit plus
    être classé HORS_SUJET, et TEMPS_DEMAIN doit rester présent (→ prévision J+1)."""
    concepts = extractor.extract("vas t'il pleuvoir demain")
    classifier = IntentClassifier(nlu_config["intents"])

    intent, _, _ = classifier.classify(concepts)

    assert intent == "QUESTION_METEO_AGRICOLE"
    assert "TEMPS_DEMAIN" in concepts


@pytest.mark.parametrize(
    "phrase",
    ["quelle est la date du jour", "on est quel jour", "quelle date sommes-nous"],
)
def test_intent_question_date(extractor, nlu_config, phrase):
    """Une demande de date → QUESTION_DATE (plus HORS_SUJET) — bug prod :
    en BOTH le bot refusait, en FR DeepSeek inventait une date fausse."""
    concepts = extractor.extract(phrase)
    classifier = IntentClassifier(nlu_config["intents"])

    intent, _, _ = classifier.classify(concepts)

    assert intent == "QUESTION_DATE"


@pytest.mark.parametrize(
    "phrase",
    [
        "quelle est la meilleure culture à faire maintenant",
        "quelle culture pour ma zone",
        "quoi cultiver ici",
        "que cultiver dans ma région",
    ],
)
def test_intent_question_culture_zone(extractor, nlu_config, phrase):
    """« quelle culture / quoi cultiver dans ma zone » → QUESTION_CULTURE_ZONE
    (plus HORS_SUJET) — bug prod #543 : en mode both la question tombait en refus
    (démo SODEXAM)."""
    concepts = extractor.extract(phrase)
    classifier = IntentClassifier(nlu_config["intents"])

    intent, _, _ = classifier.classify(concepts)

    assert "DEMANDE_CULTURE_ZONE" in concepts
    assert intent == "QUESTION_CULTURE_ZONE"


@pytest.mark.parametrize(
    "phrase",
    ["j'aime la culture générale et la musique", "la culture ivoirienne est riche"],
)
def test_culture_zone_pas_de_faux_positif(extractor, nlu_config, phrase):
    """Garde anti-faux-positif (#543) : le mot générique « culture » (société) ne
    doit PAS déclencher DEMANDE_CULTURE_ZONE — les clés sont multi-mots
    (« quelle culture », « quoi cultiver », …)."""
    concepts = extractor.extract(phrase)
    classifier = IntentClassifier(nlu_config["intents"])

    intent, _, _ = classifier.classify(concepts)

    assert "DEMANDE_CULTURE_ZONE" not in concepts
    assert intent != "QUESTION_CULTURE_ZONE"


@pytest.mark.parametrize(
    "phrase",
    [
        "est ce que les pluies vont continuer jusqu'en novembre",
        "est ce que les pluies continueront jusqu a fin octobre",
        "il pleuvra jusque decembre",
        "la pluie va durer le mois prochain",
        "il va pleuvoir cette saison",
    ],
)
def test_horizon_lointain_detecte(extractor, phrase):
    """#553 — une question météo portant sur un mois/une saison doit être
    reconnue comme HORIZON LOINTAIN : le service ne connaît que l'instant et J+1,
    donc elle sera escaladée au lieu de recevoir la météo du jour (constaté en
    prod le 2026-10-05 : « jusqu'en novembre » → météo d'aujourd'hui)."""
    assert "TEMPS_HORIZON_LOINTAIN" in extractor.extract(phrase)


@pytest.mark.parametrize(
    "phrase",
    [
        "il va pleuvoir demain",
        "quel temps fait il aujourd hui",
        "quand semer l arachide",
        "je veux semer le mais en novembre",
    ],
)
def test_horizon_lointain_pas_de_faux_positif(extractor, phrase):
    """Garde : ni « demain », ni le temps du jour, ni une question de CALENDRIER
    (« semer en novembre ») ne doivent être pris pour un horizon lointain — d'où
    l'absence volontaire de noms de mois dans les mots-clés."""
    assert "TEMPS_HORIZON_LOINTAIN" not in extractor.extract(phrase)


def test_quel_temps_fait_il_est_une_question_meteo(extractor, nlu_config):
    """#553 — « quel temps fait-il » tombait en HORS_SUJET (le mot « temps »
    n'était pas un mot-clé) et partait donc au LLM."""
    concepts = extractor.extract("quel temps fait il aujourd hui")
    intent, _, _ = IntentClassifier(nlu_config["intents"]).classify(concepts)
    assert intent == "QUESTION_METEO_AGRICOLE"


@pytest.mark.parametrize(
    ("phrase", "culture"),
    [
        ("Quelle distance laisser entre les palmiers à huile ?", "CULTURE_PALMIER_HUILE"),
        ("mes palmiers sont malades", "CULTURE_PALMIER_HUILE"),
        ("Quel mois pour semer les arachides ?", "CULTURE_ARACHIDE"),
        ("mes manguiers ne donnent pas de fruits", "CULTURE_MANGUE"),
        ("comment entretenir mes bananiers", "CULTURE_BANANE"),
        ("quand planter les plantains", "CULTURE_BANANE"),
        ("mes orangers jaunissent", "CULTURE_AGRUMES"),
        ("mes cotonniers sont attaqués", "CULTURE_COTON"),
        ("quand semer les niébés", "CULTURE_HARICOT"),
    ],
)
def test_pluriels_et_arbres_des_cultures(extractor, phrase, culture):
    """Un pluriel ou un nom d'arbre masquait la culture (« palmiers à huile »,
    « manguiers »…) : la question partait en HORS_SUJET alors que le corpus
    avait la réponse."""
    assert culture in extractor.extract(phrase)


def test_palmiers_a_huile_n_est_plus_hors_sujet(extractor, nlu_config):
    concepts = extractor.extract("Quelle distance laisser entre les palmiers à huile ?")
    intent, _, _ = IntentClassifier(nlu_config["intents"]).classify(concepts)
    assert intent != "HORS_SUJET"


def test_orange_money_n_est_pas_un_agrume(extractor):
    """« orange » n'est volontairement pas un mot-clé (Orange Money) ; seuls
    « oranger(s) » et « citron(nier)s » désignent les agrumes."""
    assert "CULTURE_AGRUMES" not in extractor.extract("j'ai envoyé l'argent par orange money")


# ---- Réponses du locuteur natif utilisateur (2026-10-07) ----


def _classer(extractor, nlu_config, phrase):
    concepts = extractor.extract(phrase)
    intent, _, _ = IntentClassifier(nlu_config["intents"]).classify(concepts)
    return intent, concepts


@pytest.mark.parametrize("phrase", ["sɔsɔ", "soso", "n bɛ sɔsɔ sɛnɛ"])
def test_haricot_se_dit_soso(extractor, phrase):
    """Haricot se dit « sɔsɔ ». Seule la variante sans ɔ « soso » était connue,
    et strip_tones ne ramène pas ɔ à o."""
    assert "CULTURE_HARICOT" in extractor.extract(phrase)


@pytest.mark.parametrize("phrase", ["kɔrɔ", "koro", "n kɔrɔ i ni ce"])
def test_koro_n_est_plus_le_haricot(extractor, phrase):
    """kɔrɔ/koro retirés de CULTURE_HARICOT : « n kɔrɔ i ni ce » (mon aîné,
    bonjour) recevait un conseil sur le haricot."""
    assert "CULTURE_HARICOT" not in extractor.extract(phrase)


def test_salutation_a_l_aine_reste_une_salutation(extractor, nlu_config):
    intent, _ = _classer(extractor, nlu_config, "n kɔrɔ i ni ce")
    assert intent == "SALUTATION_SEULE"


def test_so_maison_n_est_plus_planter(extractor, nlu_config):
    """« so » retiré d'ACTION_PLANTER : so = maison ; « i ni ce n bɛ so »
    (bonjour, je suis à la maison) demandait de quelle culture on parlait."""
    intent, concepts = _classer(extractor, nlu_config, "i ni ce n bɛ so")
    assert "ACTION_PLANTER" not in concepts
    assert intent == "SALUTATION_SEULE"


def test_malo_dan_est_planter_le_riz(extractor, nlu_config):
    intent, concepts = _classer(extractor, nlu_config, "malo dan")
    assert {"ACTION_PLANTER", "CULTURE_RIZ"} <= set(concepts)
    assert intent == "QUESTION_SAISON_PLANTATION"


def test_dan_seul_n_est_pas_encore_un_mot_cle(extractor):
    """« dan » seul (planter) attend la confirmation de ses autres emplois :
    c'est aussi une faute de frappe courante pour « dans »."""
    assert "ACTION_PLANTER" not in extractor.extract("il y a des chenilles dan mon champ")


def test_waati_ko_est_la_meteo(extractor, nlu_config):
    """« waati ko » = météo, conditions du temps ; « waati » seul (temps,
    moment, période) reste une notion de période, pas la météo."""
    intent, concepts = _classer(extractor, nlu_config, "waati ko")
    assert "TEMPS_METEO" in concepts
    assert intent == "QUESTION_METEO_AGRICOLE"
    assert "TEMPS_METEO" not in extractor.extract("waati")

