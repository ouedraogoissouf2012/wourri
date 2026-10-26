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


def test_corpus_prend_les_textes_corriges_et_coupe_l_audio_si_la_reponse_change():
    rows = [
        {"transcription": "Q0", "text_fr": "Quand planter ?", "file_name": "audio/q0.webm"},
        {"transcription": "R0", "text_fr": "En saison.", "file_name": "audio/r0.webm"},
        {"transcription": "Q1", "text_fr": "Comment récolter ?", "file_name": "audio/q1.webm"},
        {"transcription": "R1", "text_fr": "À maturité.", "file_name": "audio/r1.webm"},
    ]
    labels = [{"intent": "I", "concepts": [], "cultures_filiere": []}, {},
              {"intent": "I", "concepts": [], "cultures_filiere": []}, {}]
    pairs = [{"filiere": "F", "q": 0, "a": 1, "sim": 0.4, "method": "alignement"},
             {"filiere": "F", "q": 2, "a": 3, "sim": 0.4, "method": "alignement"}]
    paires = [
        {"status": "admin_accepted", "text_local": "Q0 corrigée", "text_fr": "Quand planter ?",
         "meta": {"external_id": "paire_qr:paire:0:1", "reponse_bci": "R0 corrigée", "reponse_fr": "En saison."}},
        {"status": "admin_accepted", "text_local": "Q1", "text_fr": "Comment récolter ?",
         "meta": {"external_id": "paire_qr:paire:2:3", "reponse_bci": " R1 ", "reponse_fr": "À maturité."}},
    ]
    textes = build.accepted_pairs(paires)
    assert build.accepted_pair_ids(paires) == {"paire:0:1", "paire:2:3"}
    e0, e1 = build.corpus_entries(rows, labels, pairs, lambda pid: pid in textes, textes)
    assert (e0["question_bci"], e0["reponse_bci"]) == ("Q0 corrigée", "R0 corrigée")
    assert e0["audio_reponse"] is None and e0["audio_a_reenregistrer"] is True
    # réponse inchangée (aux espaces près) : l'enregistrement de la dictée reste servi
    assert e1["reponse_bci"] == "R1" and e1["audio_reponse"] == "audio/r1.webm"
    assert "audio_a_reenregistrer" not in e1


def test_bruiter_reproductible_et_au_taux():
    texte = "ble benin nun ye o fata ke amun lua kakao waka" * 20
    a = build.bruiter(texte, 0.2, random.Random(1), "abɛɔ")
    b = build.bruiter(texte, 0.2, random.Random(1), "abɛɔ")
    assert a == b and a != texte
    assert build.bruiter(texte, 0.0, random.Random(1), "abɛɔ") == texte
