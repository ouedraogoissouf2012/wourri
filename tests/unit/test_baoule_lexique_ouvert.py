"""Candidats mots-clés baoulé tirés du Wiktionnaire (scripts/baoule_lexique_ouvert.py, ADR-0045).

Entrées au format kaikki.org (mots repris du Wiktionnaire) ; le NLU français réel rattache
la définition au concept. Vérifie : rattachement, source citée, doublons et mots déjà
proposés au locuteur écartés.
"""
from pathlib import Path

from app.services.nlu.nlu_service import NLUService
from scripts import baoule_lexique_ouvert as lex

CONCEPTS = Path(__file__).resolve().parents[2] / "dictionnaires" / "nlu_concepts.json"


def _entree(mot, *gloses):
    return {"word": mot, "pos": "noun", "senses": [{"glosses": list(gloses)}]}


def test_definition_francaise_rattachee_au_concept_et_source_citee():
    nlu = NLUService(str(CONCEPTS), min_confidence=0.0)
    rows = [_entree("n'gatè", "Arachide"), _entree("ya", "Vendredi."), _entree("", "Cacao.")]
    cands = lex.depuis_wiktionnaire(rows, nlu)
    assert [(c["mot"], c["concept"]) for c in cands] == [("n'gatè", "CULTURE_ARACHIDE")]
    lot = lex.lot_atelier(cands, {"CULTURE_ARACHIDE": "arachide"})
    assert lot == [{"kind": "mot_cle", "id": "CULTURE_ARACHIDE:n gate", "text_local": "n'gatè",
                    "text_fr": "arachide", "concept_nlu": "CULTURE_ARACHIDE",
                    "notes": "source : Wiktionnaire (CC BY-SA 4.0) — Arachide"}]


def test_doublons_et_mots_deja_proposes_ecartes():
    cands = [{"mot": "kakao", "concept": "CULTURE_CACAO", "source": lex.WIKT, "sens": "Cacao."},
             {"mot": "mannda", "concept": "CULTURE_BANANE", "source": lex.WIKT, "sens": "Banane plantain."},
             {"mot": "Mannda", "concept": "CULTURE_BANANE", "source": lex.WIKT, "sens": "Banane."}]
    deja = [{"kind": "mot_cle", "text_local": "kakao", "concept_nlu": "CULTURE_CACAO"}]
    lot = lex.lot_atelier(cands, {}, deja)
    assert [e["text_local"] for e in lot] == ["mannda"]
