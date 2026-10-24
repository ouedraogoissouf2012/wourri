"""Validation multi-sources des mots baoulé (scripts/baoule_validation_mots.py, ADR-0046).

Méthode du dioula (vote pondéré sur 20, 8 = validé, 5–7 = locuteur) avec ses deux
garde-fous : une source vide arrête tout (constat C10), et les attestations seules ne
valident jamais un sens. Données synthétiques : les mots « baoulé » sont factices.
"""
import json

import pytest

from scripts import baoule_sources as src
from scripts import baoule_validation_mots as val


def test_dictionnaire_glose_article_et_pluriel_et_source_vide():
    d = src.Dictionnaire("dico", 3, [("Le zorbe.", "zuka"), ("zorbes", "zukas"), ("une longue définition du mot", "x")])
    assert d.proposer("zorbe") == {"zuka": "zuka", "zukas": "zukas"}
    assert d.proposer("autre") == {}
    with pytest.raises(src.SourceVide):
        src.Dictionnaire("vide", 3, [])


def test_nasale_initiale_gardee_et_determinant_separe():
    assert src.toks_bci("n’zue") == ["nzue"]
    assert src.toks_bci("nzue’n") == ["nzue", "n"]


def test_cooccurrence_mot_surrepresente_et_graphie_sans_determinant():
    phrases = [("le zorbe pousse", "kpa Zuka’n tɔ"), ("mon zorbe", "Zuka’n mi"),
               ("la pluie", "kpa tɔ"), ("la nuit", "kpa yo"), ("le vent", "kpa fa")]
    props = src.Cooccurrence("dictee", 3, phrases).proposer("zorbe")
    assert props["zuka"] == "Zuka" and "kpa" not in props  # le déterminant « n » est filtré par voter()
    assert src.Cooccurrence("dictee", 3, phrases, min_lignes=3).proposer("zorbe") == {}


def test_attestation_compte_seulement_les_candidats():
    a = src.Attestation("web", ["zuka tɔ zuka", "yo"], min_occ=2)
    a.compter({"zuka", "tɔ"})
    assert a.atteste("zuka") and not a.atteste("tɔ") and not a.atteste("yo")
    with pytest.raises(src.SourceVide):
        src.Attestation("web", ["", "  "])


def test_mots_outils_mesures_et_formes_utiles():
    textes = ["be ka zuka tɔ. be yo fa lɛ. be mi sa kɔ."] * 3
    outils = val.mots_outils(textes, seuil=0.5)
    assert outils == {"be"}
    assert val.forme_utile("zuka", outils) and val.forme_utile("zuka tɔ", outils)
    assert not val.forme_utile("be", outils) and not val.forme_utile("zuka be", outils)
    assert not val.forme_utile("12", outils) and not val.forme_utile("n", outils)


@pytest.mark.parametrize("sources, decision", [
    ({"wiktionnaire", "gatitos", "common_voice", "zenodo", "web"}, "valide"),  # 2 sens dont 1 fort, 3+2+3 = 8
    ({"wiktionnaire", "gatitos", "common_voice", "web"}, "locuteur"),     # 7 : un point de moins
    ({"gatitos", "panlex", "common_voice", "zenodo", "smol", "web"}, "locuteur"),  # 8 mais aucune source forte
    ({"dictee", "common_voice", "zenodo"}, "locuteur"),                   # 5, un seul sens
    ({"bible", "common_voice", "zenodo", "smol", "web"}, "ecarte"),       # la Bible seule ne suffit pas
    ({"common_voice", "zenodo", "smol", "web"}, "ecarte"),                # attestations seules
])
def test_decider_attestations_ne_valident_jamais_un_sens(sources, decision):
    assert val.decider(sources)[2] == decision


def test_mots_francais_vocabulaire_des_donnees_et_homographes_exclus():
    concept = {"label_fr": "zorbe / plante (sorte)", "keywords": ["zorbes", "malo", "mais", "planter"]}
    vocab = {"zorbes", "mais", "planter", "plante"}
    assert val.mots_francais(concept, vocab, homographes={"mais"}) == ["zorbe", "plante", "sorte", "zorbes", "planter"]


def test_voter_et_lot_atelier_au_format_de_l_amorcage():
    wikt = src.Dictionnaire("wiktionnaire", 3, [("zorbe", "zuka"), ("zorbe", "tɔ")])
    gat = src.Dictionnaire("gatitos", 2, [("zorbe", "zuka")])
    cv = src.Attestation("common_voice", ["zuka", "tɔ"])
    web = src.Attestation("web", ["zuka zuka zuka"], min_occ=3)
    for a in (cv, web):
        a.compter({"zuka", "tɔ"})
    cands = val.voter(["zorbe"], [wikt, gat], [cv, web])
    assert [(c["forme"], c["score"], c["decision"]) for c in cands] == [("zuka", 7, "locuteur"), ("tɔ", 4, "ecarte")]
    rapport = {"concepts": {"CULTURE_ZORBE": {"candidats": cands}}}
    assert val.lot_atelier(rapport, {"CULTURE_ZORBE": "zorbe"}) == [{
        "kind": "mot_cle", "id": "CULTURE_ZORBE:zuka", "text_local": "zuka", "text_fr": "zorbe",
        "concept_nlu": "CULTURE_ZORBE", "notes": "multi-sources 7/20 : common_voice, gatitos, web, wiktionnaire"}]
    deja = [{"kind": "mot_cle", "concept_nlu": "CULTURE_ZORBE", "text_local": "Zuka"}]
    assert val.lot_atelier(rapport, {}, deja) == []  # déjà proposé au locuteur


def test_bible_alignee_par_reference_et_validations_acceptees_seulement(tmp_path):
    def xml(path, versets):
        corps = "".join(f'<verse number="{v}">{t}</verse>' for v, t in versets)
        path.write_text(f'<bible><book number="1"><chapter number="1">{corps}</chapter></book></bible>', encoding="utf-8")
    xml(tmp_path / "fr.xml", [(1, "au début"), (2, "la lumière")])
    xml(tmp_path / "bci.xml", [(2, "kpa tɔ"), (3, "yo")])
    assert list(src.bible_alignee(tmp_path / "fr.xml", tmp_path / "bci.xml")) == [("la lumière", "kpa tɔ")]
    v = tmp_path / "val.json"
    v.write_text(json.dumps({"entries": [{"status": "admin_accepted", "text_fr": "zorbe", "text_local": "zuka"},
                                         {"status": "admin_rejected", "text_fr": "zorbe", "text_local": "tɔ"}]}),
                 encoding="utf-8")
    assert list(src.validations_locuteur(v)) == [("zorbe", "zuka")]
