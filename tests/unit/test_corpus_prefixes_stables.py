"""Invariant du corpus (#644) : chaque réponse servie se ramène à SON entrée.

`tools/analyze_feedback.py` retrouve l'entrée rejetée par 👎 depuis le texte servi, tel
que le journal NÉGATIF le garde : `reponse_bambara[:200]` (`app/routers/feedback.py`) —
le journal général, lui, tronque à 120 et ne convient pas. C'est vrai pour le corpus
d'AUJOURD'HUI (197 préfixes stables distincts, le plus long à 150 caractères) ; ces
tests le maintiennent vrai : une entrée ajoutée demain qui le casse fait rougir la CI.

Le dernier test passe chaque entrée par le VRAI `try_ivr_exact` (recherche simulée) : si la
syntaxe des balises ou le nettoyage du texte servi change, l'outil ne retrouvera plus les
entrées — et ce test le dira, au lieu d'un « inconnu » silencieux partout.
"""
import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.schemas import Language
from app.services.chat import ivr_searcher
from app.services.chat.nlu_preprocessor import NLUResult

_OUTIL = Path(__file__).resolve().parents[2] / "tools" / "analyze_feedback.py"
_spec = importlib.util.spec_from_file_location("analyze_feedback", _OUTIL)
af = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(af)

ENTREES = af.load_corpus()
PREFIXES = af.prefixes_du_corpus(ENTREES)


def test_chaque_prefixe_stable_est_non_vide_et_tient_dans_la_troncature_du_journal_negatif():
    hors = {i: len(p) for i, p in PREFIXES.items() if not p or len(p) > af.TRONCATURE_JOURNAL_NEGATIF}
    assert not hors, (
        f"préfixe stable vide ou plus long que {af.TRONCATURE_JOURNAL_NEGATIF} caractères "
        f"(troncature du journal négatif, app/routers/feedback.py) : {hors}"
    )


def test_aucun_prefixe_stable_n_ouvre_celui_d_une_autre_entree():
    conflits = sorted((a, b) for a, pa in PREFIXES.items() for b, pb in PREFIXES.items()
                      if a != b and pb.startswith(pa))
    assert not conflits, (
        "ces entrées ne se distinguent plus par leur début : un 👎 sur l'une ne pourrait plus "
        f"être attribué — rendre leur début distinct (avant toute balise {{{{…}}}}) : {conflits}"
    )


def _servir(entree: dict, conseil) -> str:
    culture = (entree["cultures"] or ["*"])[0]
    concepts = {culture: 1.0} if culture.startswith(("CULTURE_", "ANIMAL_")) else {}
    nlu = NLUResult(message_for_deepseek="question", intent=entree["intent"], concepts=concepts)
    trouvee = {k: entree[k] for k in ("id", "intent", "reponse_bambara", "reponse_fr")}
    trouvee["cultures"] = culture
    with patch("app.services.corpus_service.chercher_reponse_ivr", return_value=trouvee), \
            patch("app.services.corpus_service.get_phrases_for_intent", return_value=[]), \
            patch.object(ivr_searcher, "get_conseil_saisonnier", return_value=conseil):
        servi = asyncio.run(ivr_searcher.try_ivr_exact(nlu, "Bouaké", None, False, Language.BOTH))
    return servi.response_dioula[:af.TRONCATURE_JOURNAL_NEGATIF]


@pytest.mark.parametrize("conseil", [
    None,
    {"phase": "en_saison", "bambara": "Sisan ye sɛnɛ waati ye.", "fr": "C'est la saison."},
], ids=["sans_conseil", "conseil_ajoute"])
def test_le_texte_reellement_servi_ramene_a_son_entree(conseil):
    perdues = [e["id"] for e in ENTREES if af.retrouver_entree(_servir(e, conseil), PREFIXES) != e["id"]]
    assert not perdues, f"réponses servies que l'outil ne ramène pas à leur entrée : {perdues}"


def test_hors_saison_le_texte_servi_ne_designe_aucune_entree():
    """#509 C1 : hors saison, le conseil daté REMPLACE le texte de l'entrée. L'outil doit
    répondre « inconnu », jamais une autre entrée."""
    conseil = {"phase": "plantation_passe", "bambara": "Sɛnɛ waati tɛmɛna.", "fr": "Saison passée."}
    designees = {e["id"]: af.retrouver_entree(_servir(e, conseil), PREFIXES) for e in ENTREES}
    assert not {i: d for i, d in designees.items() if d is not None}
