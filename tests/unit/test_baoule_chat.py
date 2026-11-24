"""Baoulé dans le chat (ADR-0045) : NLU baoulé → réponse native validée → repli honnête.

Mini-corpus factice fait de phrases de la dictée validée (aucun baoulé inventé) ; le
NLU baoulé y est construit avec quatre mots-clés, comme le produirait
scripts/baoule_nlu_build.py après validation dans l'atelier.
"""
import asyncio
import json
import threading
from pathlib import Path

import pytest

from app.models.schemas import ChatRequest, Language
from app.services import baoule_ivr
from app.services.chat import nlu_preprocessor
from app.services.chat.handlers import HANDLERS, BaouleHandler
from app.services.nlu import nlu_service
from app.services.nlu.baoule_text import prepare_bci, tokens_bci

ROOT = Path(__file__).resolve().parents[2]

CACAO_PLANTER = {
    "id": "bci-q0", "filiere": "CACAO",
    "question_bci": "Blɛ benin nun yɛ ɔ fata kɛ amun lua kakao waka ɔ ?",
    "question_fr": "Quand faut-il planter le cacaoyer ?",
    "reponse_bci": "Ɔ fata kɛ be di fie’n, kɛ nzue tɔlɛ blɛ’n bo i bo’n.",
    "reponse_fr": "Il faut planter en début de saison des pluies.",
    "intent": "QUESTION_SAISON_PLANTATION", "cultures": ["CULTURE_CACAO"],
}
MAIS_RECOLTER = {
    "id": "bci-q1", "filiere": "MAÏS",
    "question_bci": "Blɛ benin nun yɛ ɔ fata kɛ be kpɛ able’n niɔn ?",
    "question_fr": "Quand faut-il récolter le maïs ?",
    "reponse_bci": "Kɛ able’n ko yo kekle mɔ i nɲa’m be ko wu’n, yɛ be kpɛ able’n niɔn.",
    "reponse_fr": "On récolte quand les grains deviennent durs et les feuilles sèchent.",
    "intent": "QUESTION_RECOLTE", "cultures": ["CULTURE_MAIS"],
}
CORPUS = (CACAO_PLANTER, MAIS_RECOLTER)


@pytest.fixture
def nlu_bci():
    base = json.loads((ROOT / "dictionnaires" / "nlu_concepts.json").read_text(encoding="utf-8"))
    bci = {"concepts": {"CULTURE_CACAO": {"keywords": ["kakao"]}, "CULTURE_MAIS": {"keywords": ["able"]},
                        "ACTION_PLANTER": {"keywords": ["lua"]}, "ACTION_RECOLTER": {"keywords": ["kpɛ"]}}}
    return nlu_service.NLUService(config=nlu_service.build_bci_config(bci, base), min_confidence=0.0)


@pytest.fixture
def branche(monkeypatch, nlu_bci):
    """Branche le NLU baoulé de test et le mini-corpus, et capte les escalades."""
    monkeypatch.setattr(nlu_service, "get_nlu_service_bci", lambda: nlu_bci)
    monkeypatch.setattr(baoule_ivr, "entrees", lambda path=None: CORPUS)
    monkeypatch.setattr(baoule_ivr, "filieres", lambda: [e["filiere"] for e in CORPUS])
    escalades = []
    import app.services.chat.llm_guard as guard
    monkeypatch.setattr(guard, "escalate", lambda *a, **k: escalades.append((a, k)))
    return escalades


def test_mise_en_forme_bci():
    assert tokens_bci("Kakao’m be lùa ?") == ["kakao", "m", "be", "lua"]
    assert prepare_bci("W’a yo kpa") == "w a yo kpa"


def test_langue_baoule_acceptee_et_handler_enregistre():
    assert ChatRequest(message="x", language="baoule").language is Language.BAOULE
    assert isinstance(HANDLERS[Language.BAOULE], BaouleHandler)


def test_nlu_bci_reprend_les_intents_du_dioula(nlu_bci):
    res = nlu_bci.process(prepare_bci(CACAO_PLANTER["question_bci"]))
    assert "CULTURE_CACAO" in res.concepts and res.intent == "QUESTION_SAISON_PLANTATION"


def test_preprocess_baoule_sans_refus_hors_sujet(branche):
    nlu = nlu_preprocessor.preprocess_nlu("Mmo, a ti ?", None, Language.BAOULE)
    assert nlu.is_out_of_scope is False and nlu.message_for_deepseek == "Mmo, a ti ?"
    nlu = nlu_preprocessor.preprocess_nlu("x", MAIS_RECOLTER["question_bci"], Language.BAOULE)
    assert "CULTURE_MAIS" in nlu.concepts and nlu.intent == "QUESTION_RECOLTE"


def test_chercher_cadre_par_la_culture_et_tolere_les_fautes():
    # question de la dictée transcrite avec des fautes (tons, voyelles, apostrophes)
    t = baoule_ivr.chercher("ble benin nun ye o fata ke be kpe able n nion", "QUESTION_RECOLTE",
                            {"CULTURE_MAIS": 1.0}, corpus=CORPUS)
    assert t is not None and t.entry["id"] == "bci-q1"
    # culture comprise mais phrase sans rapport : repli plutôt qu'une réponse à côté
    assert baoule_ivr.chercher("mmo a ti", None, {"CULTURE_MAIS": 1.0}, corpus=CORPUS) is None


def test_chercher_ambigu_renvoie_rien():
    jumeau = {**CACAO_PLANTER, "id": "bci-q9", "reponse_bci": "autre"}
    t = baoule_ivr.chercher(CACAO_PLANTER["question_bci"], None, {}, corpus=(CACAO_PLANTER, jumeau))
    assert t is None  # deux questions identiques : on ne choisit pas au hasard


@pytest.mark.asyncio
async def test_handler_sert_la_reponse_native(branche):
    nlu = nlu_preprocessor.preprocess_nlu(CACAO_PLANTER["question_bci"], None, Language.BAOULE)
    nlu.message_original = CACAO_PLANTER["question_bci"]
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    assert r.response_local == CACAO_PLANTER["reponse_bci"]
    assert r.response == CACAO_PLANTER["reponse_fr"]
    assert r.language == "baoule" and r.meta["source"] == "ivr_bci" and r.meta["corpus_id"] == "bci-q0"
    assert branche == []  # réponse validée : rien à escalader


@pytest.mark.asyncio
async def test_handler_audio_voix_du_locuteur(branche, monkeypatch):
    from app.config import settings

    corpus = ({**CACAO_PLANTER, "audio_reponse": "audio/e10c94c3aa11.webm"}, MAIS_RECOLTER)
    monkeypatch.setattr(baoule_ivr, "entrees", lambda path=None: corpus)
    monkeypatch.setattr(settings, "bci_audio_base_url", "https://voix.example/audio/")
    nlu = nlu_preprocessor.preprocess_nlu(CACAO_PLANTER["question_bci"], None, Language.BAOULE)
    nlu.message_original = CACAO_PLANTER["question_bci"]
    r = await BaouleHandler().process(nlu, None, "Bouaké", True, Language.BAOULE, "u1")
    assert r.audio_url == "https://voix.example/audio/e10c94c3aa11.ogg"
    assert r.audio_language == "Baoulé"
    # sans base configurée, ou si l'appelant ne veut pas d'audio : pas d'URL
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    assert r.audio_url is None
    monkeypatch.setattr(settings, "bci_audio_base_url", "")
    r = await BaouleHandler().process(nlu, None, "Bouaké", True, Language.BAOULE, "u1")
    assert r.audio_url is None


@pytest.mark.asyncio
async def test_handler_repli_honnete_et_escalade(branche):
    nlu = nlu_preprocessor.preprocess_nlu("Mmo, a ti ?", None, Language.BAOULE)
    nlu.message_original = "Mmo, a ti ?"
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    assert r.response_local is None and r.meta["source"] == "bci_hors_corpus"
    # Le repli parle de LA QUESTION, pas de la langue : un paysan ne doit pas
    # conclure que le baoule ne marche pas (constate en production le 02/11).
    assert "Je n'ai pas compris ta question" in r.response
    assert "baoulé" not in r.response
    assert "cacao" in r.response and "maïs" in r.response  # sujets tirés du corpus
    assert len(branche) == 1


@pytest.mark.asyncio
async def test_recherche_ne_bloque_pas_la_boucle(branche, monkeypatch):
    """#622 : pendant que la recherche tourne, la boucle avance.

    Poignée de main, pas chronomètre : une autre tâche de la boucle attend que la
    recherche ait COMMENCÉ, puis lève le signal que la recherche attend. Appelée en
    ligne, la recherche bloque la boucle, la tâche ne peut plus tourner et l'attente
    expire ; déportée, la tâche la libère. Le test garde cette propriété quel que soit
    le nombre d'`await` qui précèdent la recherche dans `process`.

    La scrutation est bornée et le signal toujours levé : si la recherche n'était
    jamais appelée, le test échouerait sur la réponse au lieu de pendre.
    """
    commencee, signal = threading.Event(), threading.Event()

    def recherche_qui_attend(*args, **kwargs):
        commencee.set()
        assert signal.wait(timeout=2), "la boucle est restée bloquée pendant la recherche"
        return baoule_ivr.Trouvaille(CACAO_PLANTER, 0.9, 0.9)

    monkeypatch.setattr(baoule_ivr, "chercher", recherche_qui_attend)

    async def autre_requete():
        # Borne dure en temps, pas en tours : sous Windows, sleep(0.001) dure ~15 ms.
        boucle = asyncio.get_running_loop()
        echeance = boucle.time() + 2
        while not commencee.is_set() and boucle.time() < echeance:
            await asyncio.sleep(0.001)
        signal.set()

    nlu = nlu_preprocessor.preprocess_nlu(CACAO_PLANTER["question_bci"], None, Language.BAOULE)
    nlu.message_original = CACAO_PLANTER["question_bci"]
    autre = asyncio.create_task(autre_requete())
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    await autre
    assert r.response_local == CACAO_PLANTER["reponse_bci"]


@pytest.mark.asyncio
async def test_recherche_deportee_avec_les_memes_arguments(branche, monkeypatch):
    """#622 : la recherche tourne hors du fil de la boucle, appelée exactement comme avant."""
    appels = []

    def recherche(*args, **kwargs):
        appels.append((args, kwargs, threading.get_ident()))
        return None

    monkeypatch.setattr(baoule_ivr, "chercher", recherche)
    nlu = nlu_preprocessor.preprocess_nlu("Mmo, a ti ?", None, Language.BAOULE)
    nlu.message_original = "Mmo, a ti ?"
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    assert len(appels) == 1
    args, kwargs, fil = appels[0]
    assert args == (nlu.message_original, nlu.intent, nlu.concepts) and kwargs == {}
    assert fil != threading.get_ident()
    assert r.meta["source"] == "bci_hors_corpus"


@pytest.mark.asyncio
async def test_le_repli_ne_charge_pas_le_corpus_et_sort_de_la_boucle(branche, monkeypatch):
    """#623 (piège relevé sous #622) : le repli n'a besoin que des filières. Il ne relit pas
    tout le corpus, et sa requête en base tourne hors de la boucle, comme la recherche."""
    fils = []

    def filieres():
        fils.append(threading.get_ident())
        return ["CACAO", "MAÏS"]

    def entrees_interdites(*args, **kwargs):
        raise AssertionError("le repli ne doit pas charger le corpus")

    monkeypatch.setattr(baoule_ivr, "chercher", lambda *a, **k: None)
    monkeypatch.setattr(baoule_ivr, "entrees", entrees_interdites)
    monkeypatch.setattr(baoule_ivr, "filieres", filieres)
    nlu = nlu_preprocessor.preprocess_nlu("Mmo, a ti ?", None, Language.BAOULE)
    nlu.message_original = "Mmo, a ti ?"
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    assert r.response == "Je n'ai pas compris ta question. Je peux t'aider sur : cacao, maïs."
    assert len(fils) == 1 and fils[0] != threading.get_ident()


def test_base_injoignable_rien_n_est_servi_et_le_journal_dit_pourquoi(monkeypatch, caplog):
    """D4 (#623) : base tombée -> aucune réponse du corpus, le repli habituel est servi (texte
    inchangé), mais le journal dit que c'est la base, pas la question."""
    def base_tombee():
        raise ConnectionRefusedError("connexion refusée")

    monkeypatch.setattr("app.db.engine.get_engine", base_tombee)
    with caplog.at_level("ERROR", logger="app.services.baoule_ivr"):
        assert baoule_ivr.entrees() == ()
        assert baoule_ivr.filieres() == []
        assert baoule_ivr.chercher(CACAO_PLANTER["question_bci"], None, {}) is None
    messages = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert messages and all("[BCI-DB]" in m and "base" in m and "ConnectionRefusedError" in m
                            for m in messages)


@pytest.mark.asyncio
async def test_base_injoignable_le_repli_servi_ne_change_pas(monkeypatch):
    monkeypatch.setattr("app.db.engine.get_engine", lambda: (_ for _ in ()).throw(OSError("down")))
    import app.services.chat.llm_guard as guard
    monkeypatch.setattr(guard, "escalate", lambda *a, **k: None)
    nlu = nlu_preprocessor.preprocess_nlu(CACAO_PLANTER["question_bci"], None, Language.BAOULE)
    nlu.message_original = CACAO_PLANTER["question_bci"]
    r = await BaouleHandler().process(nlu, None, "Bouaké", False, Language.BAOULE, "u1")
    assert r.meta["source"] == "bci_hors_corpus"
    assert r.response == "Je n'ai pas compris ta question."
