"""#644 : `tools/analyze_feedback.py` retrouve l'entrée rejetée depuis le TEXTE SERVI.

Avant, le moteur refaisait une recherche au moment du 👎 — sans la question de
l'agriculteur, donc sur « la première » entrée de la cellule intent × culture, qui n'est
pas forcément celle qu'il a reçue (#528 choisit par la question). L'id journalisé pouvait
désigner une autre réponse ; l'outil faisait réécrire une réponse jamais envoyée.
"""
import importlib.util
from pathlib import Path

_OUTIL = Path(__file__).resolve().parents[2] / "tools" / "analyze_feedback.py"
_spec = importlib.util.spec_from_file_location("analyze_feedback", _OUTIL)  # tools/ n'est pas un paquet
af = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(af)

PREFIXES = {"riz_001": "Aw ye malo sɛnɛ", "mais_001": "Aw ye kaba sɛnɛ"}


def test_le_prefixe_stable_s_arrete_a_la_premiere_balise():
    assert af.prefixe_stable("Sanji bɛna na {{METEO_CONTEXTUEL}} aw ye") == "Sanji bɛna na"
    assert af.prefixe_stable("  Aw ye malo sɛnɛ.  ") == "Aw ye malo sɛnɛ."


def test_un_texte_servi_ouvert_par_un_seul_prefixe_designe_son_entree():
    assert af.retrouver_entree("Aw ye malo sɛnɛ sisan. Conseil de saison ajouté.", PREFIXES) == "riz_001"


def test_un_texte_que_rien_n_ouvre_ne_designe_rien():
    # Hors saison (#509 C1), le texte de l'entrée est REMPLACÉ par le conseil daté.
    assert af.retrouver_entree("Sɛnɛ waati tɛmɛna.", PREFIXES) is None
    assert af.retrouver_entree("", PREFIXES) is None


def test_un_texte_ouvert_par_deux_prefixes_ne_designe_rien():
    ambigus = {"a": "Aw ye", "b": "Aw ye malo"}
    assert af.retrouver_entree("Aw ye malo sɛnɛ", ambigus) is None


def test_le_classement_vient_du_texte_et_declare_les_votes_non_retrouves():
    votes = [
        {"source": "ivr_exact", "reponse_bambara": "Aw ye malo sɛnɛ sisan."},
        {"source": "ivr_exact", "reponse_bambara": "Aw ye malo sɛnɛ. Conseil."},
        # Vieille ligne : son id, calculé sans la question, est IGNORÉ — sinon deux
        # vérités cohabiteraient dans le même classement.
        {"source": "ivr_exact", "reponse_bambara": "Aw ye malo sɛnɛ.", "id_entree_corpus": "mais_001"},
        {"source": "ivr_exact", "reponse_bambara": "Sɛnɛ waati tɛmɛna."},  # hors saison : inconnu
        {"source": "deepseek_open", "reponse_bambara": "Aw ye kaba sɛnɛ."},  # pas une réponse du corpus
    ]
    rejetees, non_retrouves = af.classer(votes, PREFIXES)
    assert dict(rejetees) == {"riz_001": 3}
    assert non_retrouves == 1
