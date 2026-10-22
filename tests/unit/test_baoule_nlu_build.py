"""Construction du NLU et du corpus baoulé (scripts/baoule_nlu_build.py, ADR-0045).

Vérifie que seules les décisions du locuteur dans l'atelier passent dans les fichiers
servis : mots-clés acceptés (texte corrigé compris), paires reliées par le sens
seulement si acceptées. Éléments factices au format de /tasks/validations.
"""
import random

from scripts import baoule_nlu_build as build


def _item(status, text_local, concept=None, ext=None):
    meta = {}
    if concept:
        meta["concept_nlu"] = concept
    if ext:
        meta["external_id"] = ext
    return {"status": status, "text_local": text_local, "meta": meta}


def test_mots_cles_acceptes_seulement_et_texte_corrige():
    reponse = {"entries": [
        _item("admin_accepted", "Kakao", "CULTURE_CACAO"),
        _item("admin_accepted", "kakaʼo", "CULTURE_CACAO"),   # corrigé par le locuteur
        _item("admin_rejected", "waka ɔ", "ACTION_PLANTER"),
        _item("bronze", "lua", "ACTION_PLANTER"),             # pas encore décidé
        _item("admin_accepted", "kakao", "CULTURE_CACAO"),    # doublon
    ]}
    assert build.keywords_from_validations(reponse) == {"CULTURE_CACAO": ["kakao", "kaka o"]}


def test_paires_acceptees_par_identifiant():
    paires = [_item("admin_accepted", "q", ext="paire_qr:paire:3:210"),
              _item("admin_rejected", "q", ext="paire_qr:paire:4:211")]
    assert build.accepted_pair_ids(paires) == {"paire:3:210"}


def test_corpus_garde_position_et_alignement_accepte():
    rows = [
        {"transcription": "Q0", "text_fr": "Quand planter ?", "file_name": "audio/q0.webm"},
        {"transcription": "Q1", "text_fr": "Comment récolter ?", "file_name": "audio/q1.webm"},
        {"transcription": "R0", "text_fr": "En saison.", "file_name": "audio/r0.webm"},
        {"transcription": "R1", "text_fr": "À maturité.", "file_name": "audio/r1.webm"},
    ]
    labels = [{"intent": "QUESTION_SAISON_PLANTATION", "concepts": [], "cultures_filiere": ["CULTURE_CACAO"]},
              {"intent": "QUESTION_RECOLTE", "concepts": ["CULTURE_CACAO"], "cultures_filiere": []},
              {}, {}]
    pairs = [{"filiere": "CACAO", "q": 0, "a": 2, "sim": 0.9, "method": "position"},
             {"filiere": "CACAO", "q": 1, "a": 3, "sim": 0.4, "method": "alignement"}]
    sans = build.corpus_entries(rows, labels, pairs, keep_alignement=lambda pid: False)
    assert [e["id"] for e in sans] == ["bci-q0"]
    avec = build.corpus_entries(rows, labels, pairs, keep_alignement=lambda pid: pid == "paire:1:3")
    assert [e["id"] for e in avec] == ["bci-q0", "bci-q1"]
    assert avec[0]["reponse_bci"] == "R0" and avec[0]["audio_reponse"] == "audio/r0.webm"
    assert avec[1]["cultures"] == ["CULTURE_CACAO"]  # culture du NLU si la filière n'en donne pas


def test_bruiter_reproductible_et_au_taux():
    texte = "ble benin nun ye o fata ke amun lua kakao waka" * 20
    a = build.bruiter(texte, 0.2, random.Random(1), "abɛɔ")
    b = build.bruiter(texte, 0.2, random.Random(1), "abɛɔ")
    assert a == b and a != texte
    assert build.bruiter(texte, 0.0, random.Random(1), "abɛɔ") == texte
