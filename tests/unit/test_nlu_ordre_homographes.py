"""Choix de la culture (première culture citée) et homographes français du NLU (ADR-0041).

Les entrées dioula sont reprises telles quelles des textes du dépôt
(corpus_ivr.json, bambara_phrases.json, mots-clés de nlu_concepts.json) : elles
ne servent qu'à mesurer le NLU, aucune n'est déclarée correcte (ADR-0014). Les
phrases françaises viennent des jeux de mesure de l'ADR-0041.
"""
import copy
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.chat.nlu_preprocessor import enrich_for_deepseek
from app.services.nlu.concept_extractor import ConceptExtractor
from app.services.nlu.intent_classifier import IntentClassifier
from app.services.nlu.nlu_service import NLUService

RACINE = Path(__file__).resolve().parents[2]
CONFIG_PATH = RACINE / "dictionnaires" / "nlu_concepts.json"
LOGGER_EXTRACTEUR = "app.services.nlu.concept_extractor"


@pytest.fixture(scope="module")
def nlu_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def extractor(nlu_config):
    return ConceptExtractor(nlu_config)


@pytest.fixture(scope="module")
def classifier(nlu_config):
    return IntentClassifier(nlu_config["intents"])


@pytest.fixture(scope="module")
def corpus():
    data = json.loads((RACINE / "dictionnaires" / "corpus_ivr.json").read_text(encoding="utf-8"))
    return {entree["id"]: entree for entree in data["entries"]}


@pytest.fixture(scope="module")
def phrases_bambara():
    data = json.loads((RACINE / "dictionnaires" / "bambara_phrases.json").read_text(encoding="utf-8"))
    return data["phrases"]


def _cultures(concepts: dict) -> list:
    return [c for c in concepts if c.startswith("CULTURE_")]


# ---- Ordre : mots entiers dans l'ordre du texte, puis partiels seuls ----


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("je cultive le riz et le cacao", ["CULTURE_RIZ", "CULTURE_CACAO"]),
        ("je cultive le cacao et le riz", ["CULTURE_CACAO", "CULTURE_RIZ"]),
        # Multi-mots cité après un mot seul, puis avant
        ("le riz puis le palmier à huile", ["CULTURE_RIZ", "CULTURE_PALMIER_HUILE"]),
        ("le palmier à huile puis le riz", ["CULTURE_PALMIER_HUILE", "CULTURE_RIZ"]),
    ],
)
def test_les_cultures_suivent_l_ordre_du_texte(extractor, phrase, attendu):
    assert _cultures(extractor.extract(phrase)) == attendu


def test_ordre_d_un_texte_dioula_du_corpus(extractor, corpus):
    """agrumes_conseil_001 : « lemuru » (agrumes) puis « dunbu » (igname), deux
    mots entiers, dans l'ordre du texte."""
    texte = corpus["agrumes_conseil_001"]["reponse_bambara"]
    assert _cultures(extractor.extract(texte)) == ["CULTURE_AGRUMES", "CULTURE_IGNAME"]


@pytest.mark.parametrize(
    ("phrase", "premiere"),
    [
        # « anacardiers » n'est vu que par le partiel « anacard »
        ("mes anacardiers et mon riz", "CULTURE_RIZ"),
        # « organique » et « gants » contiennent le partiel « gan » (gombo)
        ("Quel engrais organique pour le riz ?", "CULTURE_RIZ"),
        ("Des gants de caoutchouc suffisent-ils pour pulvériser l'herbicide sur le riz ?", "CULTURE_RIZ"),
    ],
)
def test_un_partiel_seul_passe_apres_les_mots_entiers(extractor, phrase, premiere):
    assert _cultures(extractor.extract(phrase))[0] == premiere


def test_un_partiel_dioula_cite_avant_ne_passe_pas_devant(extractor, corpus):
    """anacarde_validation_019 : le partiel « nɛrɛ » de « nɛrɛmanw » précède
    « sɔ̀mɔ » ; l'anacarde, mot entier, reste la culture retenue."""
    texte = corpus["anacarde_validation_019"]["reponse_bambara"]
    assert _cultures(extractor.extract(texte)) == ["CULTURE_ANACARDE", "CULTURE_NERE"]


def test_les_scores_ne_changent_pas(extractor):
    """1.0 pour un mot entier, 0.7 pour un partiel seul."""
    concepts = extractor.extract("mes anacardiers et mon riz")
    assert list(concepts.items()) == [("CULTURE_RIZ", 1.0), ("CULTURE_ANACARDE", 0.7)]


def test_egalite_de_position_departagee_par_l_ordre_du_json():
    """Deux concepts au même mot : l'ordre de nlu_concepts.json, pas l'alphabet."""
    config = {"concepts": {"CULTURE_B": {"keywords": ["riz"]}, "CULTURE_A": {"keywords": ["riz"]}}}
    assert list(ConceptExtractor(config).extract("du riz")) == ["CULTURE_B", "CULTURE_A"]


def test_culture_concept_et_prefixe_designent_la_premiere_culture_citee(extractor, classifier):
    concepts = extractor.extract("je cultive le cacao et le riz : quel engrais mettre ?")
    assert _cultures(concepts) == ["CULTURE_CACAO", "CULTURE_RIZ"]
    _, _, donnees = classifier.classify(concepts)

    assert donnees["culture_concept"] == "CULTURE_CACAO"
    assert enrich_for_deepseek("phrase", concepts).startswith("[Paysan cultive: cacao]")


def test_le_resultat_ne_depend_pas_de_pythonhashseed(corpus):
    """Garde-fou contre le retour d'un set : mêmes concepts, même ordre et même
    culture_concept quelle que soit la graine de hachage."""
    textes = [
        "je cultive le cacao et le riz, le maïs et le manioc",
        "mais comment faire pour mon manioc et mes anacardiers",
        corpus["agrumes_conseil_001"]["reponse_bambara"],
        corpus["anacarde_validation_019"]["reponse_bambara"],
    ]
    code = (
        "import json, sys\n"
        "from app.services.nlu.concept_extractor import ConceptExtractor\n"
        "from app.services.nlu.intent_classifier import IntentClassifier\n"
        "cfg = json.load(open(sys.argv[1], encoding='utf-8'))\n"
        "ex, cl = ConceptExtractor(cfg), IntentClassifier(cfg['intents'])\n"
        "out = []\n"
        "for t in json.loads(sys.stdin.read()):\n"
        "    c = ex.extract(t)\n"
        "    out.append([list(c), cl.classify(c)[2].get('culture_concept')])\n"
        "print(json.dumps(out))\n"
    )
    sorties = set()
    for graine in ("0", "1", "2", "3", "4"):
        env = dict(os.environ, PYTHONHASHSEED=graine, PYTHONIOENCODING="utf-8")
        resultat = subprocess.run(
            [sys.executable, "-c", code, str(CONFIG_PATH)],
            input=json.dumps(textes), capture_output=True, text=True,
            encoding="utf-8", env=env, cwd=RACINE, check=True,
        )
        sorties.add(resultat.stdout)
    assert len(sorties) == 1


# ---- Homographes : retirés à côté d'une autre culture, gardés seuls ----


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("mais comment faire pour mon manioc", ["CULTURE_MANIOC"]),
        ("Mais comment faire pour mon manioc ?", ["CULTURE_MANIOC"]),
        # Pronom accolé par un trait d'union : pas un déterminant
        ("Mon voisin m'a dit : arrose-le mais pas trop. C'est valable pour le manioc ?", ["CULTURE_MANIOC"]),
        # « le » puis « pas » : la conjonction, même sans trait d'union (vocal)
        ("il m a dit traite le mais pas en plein soleil c est pour mon cacao", ["CULTURE_CACAO"]),
        # « un » n'est pas un mot avant sûr de « mais »
        ("j en ai planté un mais il est mort mon cacaoyer", ["CULTURE_CACAO"]),
        ("j'ai fini de semer le riz", ["CULTURE_RIZ"]),
        ("Loué et béni soit Dieu, ma récolte de cacao est bonne.", ["CULTURE_CACAO"]),
        ("les mil francs ke tu ma dit pr lengrais du riz c pas assez", ["CULTURE_RIZ"]),
    ],
)
def test_homographe_douteux_retire_a_cote_d_une_autre_culture(extractor, phrase, attendu):
    assert _cultures(extractor.extract(phrase)) == attendu


@pytest.mark.parametrize(
    ("phrase", "premiere"),
    [
        ("mes jeunes mais ont besoin d engrais organique ?", "CULTURE_MAIS"),
        ("mes jeunes mais jaunissent avec l'arrosage automatique", "CULTURE_MAIS"),
        ("c'est fatigant mes jeunes mais ne poussent pas", "CULTURE_MAIS"),
        ("prix mil a kabadougou cette semaine ?", "CULTURE_MIL"),
    ],
)
def test_un_faux_partiel_ne_fait_pas_retirer_un_homographe(extractor, phrase, premiere):
    """Un partiel ne suffit pas à retirer un homographe douteux, et passe après
    lui : « organique » (gombo), « automatique » (tomate), « fatigant »
    (arachide, gombo) et « Kabadougou » (maïs) sont de faux partiels."""
    assert _cultures(extractor.extract(phrase))[0] == premiere


def test_limite_connue_un_partiel_ne_fait_pas_retirer_un_homographe(extractor):
    """Contrepartie assumée (ADR-0041) : à côté d'une culture vue seulement par
    un partiel (« lanacarde », élision sans apostrophe), la conjonction reste lue
    comme le maïs, cité en premier."""
    assert _cultures(extractor.extract("mais oui g deja traité lanacarde 2 fois")) == [
        "CULTURE_MAIS", "CULTURE_ANACARDE",
    ]


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("je suis venu le 12 mais mon riz n'a pas levé", ["CULTURE_RIZ"]),
        ("sac dengrais pr 30 mil cest cher pr mon cacao", ["CULTURE_CACAO"]),
    ],
)
def test_un_nombre_est_le_mot_avant(extractor, phrase, attendu):
    """Le mot avant « mais » est « 12 », pas le déterminant « le » ; celui avant
    « mil » est « 30 », pas la préposition « pr »."""
    assert _cultures(extractor.extract(phrase)) == attendu


@pytest.fixture(scope="module")
def service():
    return NLUService(str(CONFIG_PATH), min_confidence=0.2)


@pytest.mark.parametrize(
    ("phrase", "premiere"),
    [
        ("ani sogoma mais comment faire pour mon manioc", "CULTURE_MANIOC"),
        ("tile bɛ mais comment faire pour mon cacao", "CULTURE_CACAO"),
        ("Mon cacao est beau mais la chaleur me fait peur.", "CULTURE_CACAO"),
        ("mon manioc va bien mais le vent a cassé des tiges kesk je fais", "CULTURE_MANIOC"),
        ("prix mil a kabadougou cette semaine ?", "CULTURE_MIL"),
    ],
)
def test_la_regle_des_homographes_ne_change_pas_l_intent(nlu_config, phrases_bambara, service, phrase, premiere):
    """L'intent est celui que donne le dictionnaire sans la section
    « homographes » : retirer la culture douteuse changeait sinon le barème, et
    « ani sogoma mais … » recevait une salutation, « Mon cacao est beau mais la
    chaleur … » la météo. Seule la culture retenue change.
    « ani sogoma » et « tile bɛ » sont des phrases de bambara_phrases.json."""
    assert {"ani sogoma", "tile bɛ"} <= {p["bam"] for p in phrases_bambara}
    sans_regle = copy.deepcopy(nlu_config)
    del sans_regle["homographes"]
    concepts_sans_regle = ConceptExtractor(sans_regle).extract(phrase)
    attendu, _, _ = IntentClassifier(nlu_config["intents"]).classify(concepts_sans_regle)

    resultat = service.process(phrase)

    assert resultat.intent == attendu
    assert _cultures(resultat.concepts)[0] == premiere


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("je cultive du riz et du mais", ["CULTURE_RIZ", "CULTURE_MAIS"]),
        ("engrais pour mais et pour riz", ["CULTURE_MAIS", "CULTURE_RIZ"]),
        # Forme sûre : le tréma, même en tête de phrase
        ("Maïs : quand semer, avant ou après le riz ?", ["CULTURE_MAIS", "CULTURE_RIZ"]),
        # Mot après sûr : « mais et niebe »
        ("on peut associer mais et niebe ?", ["CULTURE_MAIS", "CULTURE_HARICOT"]),
        ("je cultive le mil et le riz", ["CULTURE_MIL", "CULTURE_RIZ"]),
        ("le prix du caoutchouc et du cacao", ["CULTURE_HEVEA", "CULTURE_CACAO"]),
    ],
)
def test_homographe_en_contexte_sur_garde_a_cote_d_une_autre_culture(extractor, phrase, attendu):
    assert _cultures(extractor.extract(phrase)) == attendu


@pytest.mark.parametrize(
    ("phrase", "culture"),
    [
        ("caoutchouc a encore baisse ?", "CULTURE_HEVEA"),
        ("kilo caoutchouc cest combien a soubre ?", "CULTURE_HEVEA"),
        ("mes jeunes mais jaunissent kesk je fais", "CULTURE_MAIS"),
        # Réponse d'un mot à « De quelle culture parles-tu ? »
        ("mil", "CULTURE_MIL"),
        ("quand semer mais ?", "CULTURE_MAIS"),
    ],
)
def test_homographe_seul_garde_jamais_de_refus(extractor, classifier, phrase, culture):
    """Une culture vue seulement par un homographe douteux est gardée quand la
    phrase ne cite aucune autre culture : jamais de refus hors-sujet."""
    concepts = extractor.extract(phrase)
    intent, _, donnees = classifier.classify(concepts)

    assert _cultures(concepts) == [culture]
    assert intent != "HORS_SUJET"
    assert donnees["culture_concept"] == culture


def test_question_de_prix_reste_dans_la_famille_vente(extractor, classifier):
    """Garde ADR-0039 : sans culture, « prix mais » sortirait de QUESTION_VENTE
    et le LLM répondrait sur un prix."""
    intent, _, donnees = classifier.classify(extractor.extract("prix mais aujourdhui a bouake ?"))

    assert intent == "QUESTION_VENTE"
    assert donnees["culture_concept"] == "CULTURE_MAIS"


def test_limite_connue_homographe_seul_sans_culture_reste_une_culture(extractor):
    """Limite assumée (ADR-0041) : sans autre culture, la conjonction reste lue
    comme le maïs, comme avant. La retirer ferait de « mes jeunes mais
    jaunissent » un refus hors-sujet."""
    assert _cultures(extractor.extract("j'ai planté mais rien ne pousse")) == ["CULTURE_MAIS"]


def test_salutation_reconnue_avant_mais_n_est_pas_un_determinant(extractor, nlu_config, phrases_bambara):
    """« i ni ce » (mot-clé SALUTATION de nlu_concepts.json, phrase « Merci » de
    bambara_phrases.json) suivi de « mais » et d'une phrase dioula du dépôt
    (« Je veux cultiver du riz ») : le « ce » de la salutation ne fait pas du
    « mais » un maïs."""
    salutation = "i ni ce"
    assert salutation in nlu_config["concepts"]["SALUTATION"]["keywords"]
    assert any(p["bam"] == salutation for p in phrases_bambara)
    riz = next(p["bam"] for p in phrases_bambara
               if p["fr"] == "Je veux cultiver du riz" and p["source"] == "manuel")

    assert _cultures(extractor.extract(f"{salutation} mais {riz}")) == ["CULTURE_RIZ"]


def test_fini_dioula_retire_a_cote_d_une_autre_culture(extractor, corpus):
    """igname_stockage_001 : « Ku ma fini ka ji don » (reponse_fr : « Ne les lavez
    pas ») ne donne plus le mil à côté de l'igname. Changement de reconnaissance
    d'un mot-clé dioula, à valider nativement (ADR-0014, ADR-0041)."""
    entree = corpus["igname_stockage_001"]
    assert "lavez" in entree["reponse_fr"]
    assert _cultures(extractor.extract(entree["reponse_bambara"])) == ["CULTURE_IGNAME"]


# ---- Section « homographes » : validation au chargement ----


def test_la_section_livree_est_valide_et_active(nlu_config, caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_EXTRACTEUR):
        extracteur = ConceptExtractor(nlu_config)

    assert not caplog.records
    assert _cultures(extracteur.extract("mais comment faire pour mon manioc")) == ["CULTURE_MANIOC"]


def _avec_homographes(nlu_config, section):
    config = copy.deepcopy(nlu_config)
    config["homographes"] = section
    return config


@pytest.mark.parametrize(
    "section",
    [
        {"mots": []},
        # « mais » n'est pas un mot-clé du riz
        {"mots": {"mais": {"concept": "CULTURE_RIZ"}}},
        # Faute de frappe dans un nom de champ
        {"mots": {"mais": {"concept": "CULTURE_MAIS", "mots_avant_sur": ["le"]}}},
        # Mauvais type
        {"mots": {"mais": {"concept": "CULTURE_MAIS", "mots_avant_surs": "le"}}},
        # Champ texte qui n'est pas un texte
        {"mots": {"mais": {"concept": "CULTURE_MAIS", "note": 3}}},
        # Entrée de deux mots : elle ne correspondrait jamais à un mot du texte
        {"mots": {"mais": {"concept": "CULTURE_MAIS", "mots_avant_surs": ["champ de"]}}},
        # Même forme normalisée déclarée deux fois : la seconde remplaçait la première
        {"mots": {"mais": {"concept": "CULTURE_MAIS"}, "maïs": {"concept": "CULTURE_MAIS"}}},
    ],
)
def test_section_invalide_desactive_la_regle_pas_le_nlu(nlu_config, caplog, section):
    """Comportement choisi : l'erreur est signalée en ERROR et la règle est
    désactivée (chaque homographe compte comme culture, comme avant la section) ;
    le NLU, lui, reste disponible."""
    with caplog.at_level(logging.ERROR, logger=LOGGER_EXTRACTEUR):
        extracteur = ConceptExtractor(_avec_homographes(nlu_config, section))

    assert any("homographes" in r.getMessage() for r in caplog.records)
    concepts = extracteur.extract("mais comment faire pour mon manioc")
    assert set(_cultures(concepts)) == {"CULTURE_MAIS", "CULTURE_MANIOC"}


def test_homographe_contenant_un_partiel_de_sa_culture_refuse(caplog):
    """L'étape des partiels trouverait le mot quand même : la règle serait contournée."""
    config = {
        "concepts": {"CULTURE_RIZ": {"keywords": ["riz", "rizière"], "partial": ["riz"]}},
        "homographes": {"mots": {"rizière": {"concept": "CULTURE_RIZ"}}},
    }
    with caplog.at_level(logging.ERROR, logger=LOGGER_EXTRACTEUR):
        ConceptExtractor(config)

    assert any("partiel" in r.getMessage() for r in caplog.records)


def test_nlu_service_reste_disponible_avec_une_section_invalide(nlu_config, tmp_path, caplog):
    chemin = tmp_path / "nlu_concepts.json"
    config = _avec_homographes(nlu_config, {"mots": {"mais": {"concept": "CULTURE_RIZ"}}})
    chemin.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger=LOGGER_EXTRACTEUR):
        service = NLUService(str(chemin), min_confidence=0.2)

    assert caplog.records
    assert service.process("je veux semer le riz").intent == "QUESTION_SAISON_PLANTATION"
