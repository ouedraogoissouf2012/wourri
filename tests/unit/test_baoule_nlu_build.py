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


def test_relecture_ecarte_les_mots_hors_concept_et_a_confirmer():
    # sens tirés de l'export de l'atelier : « amun » = « vous », rangé sous planter
    reponse = {"entries": [
        _item("admin_accepted", "lua", "ACTION_PLANTER", ext="mot_cle:ACTION_PLANTER:lua"),
        _item("admin_accepted", "amun", "ACTION_PLANTER", ext="mot_cle:ACTION_PLANTER:amun"),
        _item("admin_accepted", "gua", "ACTION_VENDRE", ext="mot_cle:ACTION_VENDRE:gua"),
        _item("admin_accepted", "kakao", "CULTURE_CACAO", ext="mot_cle:CULTURE_CACAO:kakao"),
    ]}
    relecture = {"mots": [
        {"external_id": "mot_cle:ACTION_PLANTER:amun", "decision": "hors_concept"},
        {"external_id": "mot_cle:ACTION_VENDRE:gua", "decision": "a_confirmer"},
        {"external_id": "mot_cle:CULTURE_CACAO:kakao", "decision": "garde"},
    ]}
    assert build.keywords_from_validations(reponse, relecture) == {
        "ACTION_PLANTER": ["lua"], "CULTURE_CACAO": ["kakao"]}
    assert build.keywords_from_validations(reponse)["ACTION_PLANTER"] == ["lua", "amun"]  # sans relecture


def test_fichier_de_relecture_du_depot_bien_forme():
    import json

    doc = json.loads((build.DICTIONNAIRES / "relecture_mots_cles_bci.json").read_text(encoding="utf-8"))
    assert set(doc["decisions_possibles"]) == {"hors_concept", "a_confirmer", "garde"}
    ids = [m["external_id"] for m in doc["mots"]]
    assert len(ids) == len(set(ids)) and all(i.startswith(f"mot_cle:{m['concept']}:") for i, m in zip(ids, doc["mots"]))
    assert {m["decision"] for m in doc["mots"]} <= set(doc["decisions_possibles"])


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


# --------------------------------------------- réponses corrigées puis réenregistrées
#
# Le locuteur corrige une réponse dans l'atelier, puis la réenregistre en dictée. La
# ligne du réenregistrement porte le texte corrigé — mais ce n'est PAS une réponse de
# plus à apparier : la compter comme telle donne plus de réponses que de questions dans
# la filière et l'appariement s'arrête (« alignement impossible »).


def _rows_une_paire(reponse_corrigee="R0 corrigée", fichier="audio/neuf.webm"):
    """Une filière : la question, la réponse d'origine, puis son réenregistrement."""
    return [
        {"transcription": "Q0", "text_fr": "Quand planter ?", "file_name": "audio/q0.webm"},
        {"transcription": "R0", "text_fr": "En saison.", "file_name": "audio/r0.webm"},
        {"transcription": reponse_corrigee, "text_fr": "En saison.", "file_name": fichier},
    ]


def _textes_une_paire(question="Q0", reponse="R0 corrigée", pid="paire:0:1"):
    return {pid: {"question_bci": question, "question_fr": "Quand planter ?",
                  "reponse_bci": reponse, "reponse_fr": "En saison."}}


def test_un_reenregistrement_est_mis_de_cote_avant_appariement():
    dictee, voix = build.separer_reenregistrements(_rows_une_paire(), _textes_une_paire())
    assert [r["transcription"] for r in dictee] == ["Q0", "R0"]
    assert voix == {"R0 corrigée": "audio/neuf.webm"}


def test_l_ordre_est_conserve_donc_les_identifiants_ne_bougent_pas():
    """Les réenregistrements arrivent en fin d'export : les retirer ne décale aucun
    indice, donc aucun `bci-q…` déjà servi ne change d'identité."""
    rows = _rows_une_paire() + [
        {"transcription": "Q1", "text_fr": "Comment récolter ?", "file_name": "audio/q1.webm"},
        {"transcription": "R1", "text_fr": "À maturité.", "file_name": "audio/r1.webm"},
    ]
    dictee, _ = build.separer_reenregistrements(rows, _textes_une_paire())
    assert dictee == [rows[0], rows[1], rows[3], rows[4]]


def test_la_reponse_d_origine_n_est_jamais_prise_pour_un_reenregistrement():
    """Quand le locuteur n'a corrigé que la question, la réponse acceptée est mot pour
    mot celle de la dictée. Mettre sa ligne de côté la ferait disparaître du corpus :
    la ligne d'origine est reconnue par son indice, inscrit dans l'identifiant de paire."""
    rows = _rows_une_paire()[:2]
    textes = _textes_une_paire(question="Q0 corrigée", reponse="R0")
    dictee, voix = build.separer_reenregistrements(rows, textes)
    assert dictee == rows and voix == {}


def test_une_question_n_est_jamais_mise_de_cote():
    rows = [{"transcription": "R0 corrigée", "text_fr": "Est-ce la saison ?", "file_name": "audio/x.webm"}]
    rows += _rows_une_paire()[:2]
    dictee, voix = build.separer_reenregistrements(rows, _textes_une_paire(pid="paire:1:2"))
    assert dictee == rows and voix == {}


def test_un_identifiant_de_paire_inattendu_ne_bloque_pas_la_construction():
    dictee, voix = build.separer_reenregistrements(
        _rows_une_paire(), {"inattendu": {"reponse_bci": "R0 corrigée"}})
    assert [r["transcription"] for r in dictee] == ["Q0", "R0"]
    assert voix == {"R0 corrigée": "audio/neuf.webm"}


def test_une_reponse_vide_ou_absente_ne_met_rien_de_cote():
    for reponse in ("", "   ", None):
        dictee, voix = build.separer_reenregistrements(
            _rows_une_paire(), {"paire:0:1": {"reponse_bci": reponse}})
        assert len(dictee) == 3 and voix == {}


# ----------------------------------------------- la voix du réenregistrement est servie

_LABELS = [{"intent": "QUESTION_SAISON_PLANTATION", "concepts": [], "cultures_filiere": ["CULTURE_CACAO"]}, {}]
_PAIRS = [{"filiere": "CACAO", "q": 0, "a": 1, "sim": 0.4, "method": "alignement"}]


def test_une_reponse_corrigee_retrouve_la_voix_du_reenregistrement():
    """Le cœur du correctif : sans la table des réenregistrements, le travail du
    locuteur restait invisible — la réponse était servie en texte seul."""
    rows = _rows_une_paire()[:2]
    textes = _textes_une_paire()
    entree, = build.corpus_entries(rows, _LABELS, _PAIRS, lambda pid: pid in textes, textes,
                                   {"R0 corrigée": "audio/neuf.webm"})
    assert entree["reponse_bci"] == "R0 corrigée"
    assert entree["audio_reponse"] == "audio/neuf.webm"
    assert "audio_a_reenregistrer" not in entree


def test_une_reponse_corrigee_sans_reenregistrement_reste_a_refaire():
    """Le repli existant ne change pas : pas de voix inventée, et la réponse part dans
    la liste à rendre au locuteur."""
    rows = _rows_une_paire()[:2]
    textes = _textes_une_paire()
    entree, = build.corpus_entries(rows, _LABELS, _PAIRS, lambda pid: pid in textes, textes,
                                   {"une autre réponse": "audio/pas-la-bonne.webm"})
    assert entree["audio_reponse"] is None and entree["audio_a_reenregistrer"] is True


def test_une_reponse_inchangee_garde_la_voix_de_la_dictee():
    """La table des réenregistrements ne doit pas détourner une réponse non corrigée."""
    rows = _rows_une_paire()[:2]
    textes = _textes_une_paire(reponse=" R0 ")
    entree, = build.corpus_entries(rows, _LABELS, _PAIRS, lambda pid: pid in textes, textes,
                                   {"R0": "audio/jamais.webm"})
    assert entree["audio_reponse"] == "audio/r0.webm"
    assert "audio_a_reenregistrer" not in entree
