"""Amorçage du NLU baoulé (scripts/baoule_nlu_bootstrap.py) sur des données factices.

Vérifie la méthode (découpage des mots, appariement question → réponse,
mots-clés candidats, config NLU), pas la qualité linguistique : les mots-clés
réels sont validés par un locuteur natif.
"""
import json
import zipfile
from pathlib import Path

import pytest

from scripts import baoule_nlu_bootstrap as boot

ROOT = Path(__file__).resolve().parents[2]


def test_tokens_bci_separe_apostrophes_et_retire_tons():
    assert boot.tokens_bci("Blɛ benin nun yɛ fie’n ka ɔ ?") == ["blɛ", "benin", "nun", "yɛ", "fie", "n", "ka", "ɔ"]
    assert boot.tokens_bci("W’a yo kpa, wʼa yó") == ["w", "a", "yo", "kpa", "w", "a", "yo"]
    assert boot.prepare_bci("Kakao’m be.") == "kakao m be"


def test_align_garde_l_ordre_et_saute_la_question_sans_reponse():
    questions = ["q0", "q1", "q2"]
    answers = ["r0", "r2"]
    table = {("q0", "r0"): 0.9, ("q1", "r2"): 0.6, ("q2", "r2"): 0.8}

    def similarity(qs, ans):
        return [[table.get((q, a), 0.0) for a in ans] for q in qs]

    assert boot.align(questions, answers, similarity) == [(0, 0, 0.9), (2, 1, 0.8)]
    with pytest.raises(ValueError):
        boot.align(["q0"], ["r0", "r1"], similarity)


def _rows():
    return [
        {"filiere": "CACAO", "transcription": "Blɛ benin yɛ be lua kakao ɔ ?", "text_fr": "Quand planter le cacao ?"},
        {"filiere": "CACAO", "transcription": "Wafa sɛ yɛ be kpɛ kakao ɔ ?", "text_fr": "Comment récolter le cacao ?"},
        {"filiere": "CACAO", "transcription": "Be lua i blɛ kpafuɛ’n.", "text_fr": "On le plante en saison."},
    ]


def test_pair_qa_par_filiere():
    def similarity(qs, ans):
        return [[1.0 if "planter" in q else 0.1 for _ in ans] for q in qs]

    pairs = boot.pair_qa(_rows(), similarity)
    assert [(p["q"], p["a"], p["method"]) for p in pairs] == [(0, 2, "alignement"), (1, None, "alignement")]


def test_keyword_candidates_support_et_precision():
    texts = ["be lua kakao", "amun lua kakao waka", "be kpɛ kakao", "be lua avie"]
    concepts = [["ACTION_PLANTER", "CULTURE_CACAO"], ["ACTION_PLANTER", "CULTURE_CACAO"],
                ["CULTURE_CACAO"], ["ACTION_PLANTER", "CULTURE_RIZ"]]
    cands = boot.keyword_candidates(texts, concepts, min_support=2, min_precision=0.75)
    mots = {c: [g for g, *_ in v] for c, v in cands.items()}
    assert "lua" in mots["ACTION_PLANTER"]
    assert "kakao" in mots["CULTURE_CACAO"]
    assert "be" not in mots.get("CULTURE_CACAO", [])  # « be » est aussi dans la phrase sur le riz
    assert "CULTURE_RIZ" not in cands  # une seule phrase : support insuffisant


def test_build_config_reprend_les_intents_du_dioula_et_classe():
    base = json.loads((ROOT / "dictionnaires" / "nlu_concepts.json").read_text(encoding="utf-8"))
    cands = {"CULTURE_CACAO": [("kakao", 3, 3, 1.0)], "ACTION_PLANTER": [("lua", 3, 3, 1.0)]}
    config = boot.build_config(cands, base)
    assert config["intents"] == base["intents"]
    res = boot.nlu_from_config(config).process(boot.prepare_bci("Blɛ benin yɛ be lua kakao ɔ ?"))
    assert "CULTURE_CACAO" in res.concepts and res.intent == "QUESTION_SAISON_PLANTATION"


def test_atelier_entries_mots_cles_et_paires_reliees_par_le_sens():
    rows = _rows()
    cands = {"CULTURE_CACAO": [("kakao", 2, 2, 1.0)]}
    pairs = [{"filiere": "CACAO", "q": 0, "a": 2, "sim": 0.9, "method": "alignement"},
             {"filiere": "CACAO", "q": 1, "a": None, "sim": None, "method": "alignement"}]
    lot = boot.atelier_entries(cands, pairs, rows, {"CULTURE_CACAO": "cacao"})
    assert lot[0] == {"kind": "mot_cle", "id": "CULTURE_CACAO:kakao", "text_local": "kakao",
                      "text_fr": "cacao", "concept_nlu": "CULTURE_CACAO",
                      "notes": "vu dans 2 questions de la dictée"}
    assert [e["kind"] for e in lot] == ["mot_cle", "paire_qr"]  # question sans réponse : rien
    assert lot[1]["reponse_bci"] == rows[2]["transcription"]
    # une paire reliée par position n'est pas soumise à validation
    pos = [{**pairs[0], "method": "position"}]
    assert boot.atelier_entries({}, pos, rows, {}) == []


def test_read_export_zip(tmp_path):
    z = tmp_path / "dictee.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("metadata.csv", "file_name,transcription,language,filiere,text_fr\n"
                                   "audio/a.webm,Be lua kakao ɔ ?,bci,CACAO,Quand planter le cacao ?\n")
    rows = boot.read_export(z)
    assert rows[0]["transcription"] == "Be lua kakao ɔ ?" and boot.is_question(rows[0])
