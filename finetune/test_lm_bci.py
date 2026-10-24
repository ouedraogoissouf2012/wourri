"""Modèle de langue baoulé pour le décodage CTC (finetune/lm_bci.py, #474).

Données synthétiques : mots factices et matrices de log-probabilités construites à la main.
On vérifie l'absence de fuite du test vers le corpus, un trigramme Kneser-Ney normalisé, les
formules de pyctcdecode, et qu'une recherche guidée par le modèle de langue sépare un mot collé
que le décodage glouton laisse collé.
"""
import math

import numpy as np
import pytest

import lm_bci as lm

pytest.importorskip("pyctcdecode")


def test_corpus_normalise_et_retire_toute_ligne_du_test():
    textes = ["Naan sran ɔ ba. Kpa tɔ yo!", "Mi kɔ fie — Naan Sran ɔ ba wa ?", "un", "Kɔ fie kpa"]
    lignes, stats = lm.preparer_corpus(textes, phrases_test=["naan sran ɔ ba"])
    assert lignes == ["kpa tɔ yo", "kɔ fie kpa"]  # « un » : moins de 2 mots
    assert stats == {"lignes": 2, "fuites_retirees": 2, "mots": 6}
    # une phrase du test n'est retirée qu'en mots entiers
    assert lm.preparer_corpus(["naan sranɛ ɔ bao kpa"], ["naan sran ɔ ba"])[1]["fuites_retirees"] == 0


def test_filtre_garde_le_baoule_et_ecarte_le_reste():
    reference = {"naan", "sran", "ɔ", "ba", "kpa", "be", "yo"}
    lignes = ["naan sran ɔ ba", "be yo kpa california", "land line verizon inc", "ɔ ba wʋ plɩ"]
    gardees, retirees = lm.filtrer_baoule(lignes, reference)
    assert gardees == ["naan sran ɔ ba", "be yo kpa california"] and retirees == 2  # 3/4 ≥ 60 %, 2/4 < 60 %


def test_trigramme_kneser_ney_somme_a_un_et_repli():
    t = lm.Trigramme(["naan sran ba", "naan sran kɔ", "sran kɔ fie", "kpa fie"])
    mots = sorted(t.vocab) + ["</s>"]
    for ctx in [("naan", "sran"), ("<s>", "<s>"), ("inconnu", "kpa")]:
        assert math.isclose(sum(t.p3(ctx[0], ctx[1], w) for w in mots), 1.0, rel_tol=1e-9)
    assert t.log10(("naan", "sran"), "ba") > t.log10(("naan", "sran"), "fie")
    assert t.log10(("naan", "sran"), "jamaisvu") == lm.UNK_LOG10


def test_modele_pyctcdecode_memes_formules():
    t = lm.Trigramme(["naan sran ba"])
    m = lm.modele_pyctcdecode(t, alpha=0.5, beta=1.0)
    s, etat = m.score(m.get_start_state(), "naan")
    assert etat == ("<s>", "naan")
    assert math.isclose(s, 0.5 * t.log10(("<s>", "<s>"), "naan") * math.log(10) + 1.0)
    fin, _ = m.score(("naan", "sran"), "ba", is_last_word=True)
    attendu = 0.5 * (t.log10(("naan", "sran"), "ba") + t.log10(("sran", "ba"), "</s>")) * math.log(10) + 1.0
    assert math.isclose(fin, attendu)
    assert m.score_partial_token("na") == 0 and m.score_partial_token("xq") == -10.0


def test_colonnes_blanc_espace_puis_alphabet():
    pieces = ["<s>", "<pad>", "</s>", "<unk>", " ", "ዘ", "a", "n", "ɛ", "Z"]
    ids, labels = lm.colonnes(pieces, alphabet={"a", "n", "ɛ"})
    assert ids == [0, 4, 6, 7, 8] and labels == ["", " ", "a", "n", "ɛ"]


LABELS = ["", " ", "a", "n", "s", "r"]


def _matrice(trames):
    """Une trame = {étiquette: probabilité} ; le reste de la masse va au blanc."""
    m = np.full((len(trames), len(LABELS)), 1e-6)
    for i, t in enumerate(trames):
        for lab, p in t.items():
            m[i, LABELS.index(lab)] = p
        m[i, 0] += max(0.0, 1.0 - m[i].sum())
    return np.log(m / m.sum(axis=1, keepdims=True))


def test_glouton_fusionne_repetitions_et_blancs():
    m = _matrice([{"n": .9}, {"n": .9}, {"a": .9}, {}, {"a": .9}, {"n": .9}])
    assert lm.glouton(m, LABELS) == "naan"


def test_le_modele_de_langue_separe_un_mot_colle():
    # « naan » puis une trame hésitante (espace 0,45 / blanc 0,55) puis « sran »
    trames = [{"n": .9}, {"a": .9}, {}, {"a": .9}, {"n": .9}, {" ": .45},
              {"s": .9}, {"r": .9}, {"a": .9}, {"n": .9}]
    m = _matrice(trames)
    assert lm.glouton(m, LABELS) == "naansran"
    t = lm.Trigramme(["naan sran ba", "naan sran kɔ", "sran naan"] * 5)
    dec = lm.decodeur(LABELS, lm.modele_pyctcdecode(t, alpha=0.5, beta=1.0))
    assert dec.decode(m, beam_width=16) == "naan sran"


def test_regler_choisit_sur_le_cer():
    trames = [{"n": .9}, {"a": .9}, {}, {"a": .9}, {"n": .9}, {" ": .45},
              {"s": .9}, {"r": .9}, {"a": .9}, {"n": .9}]
    t = lm.Trigramme(["naan sran ba", "naan sran kɔ"] * 5)

    def score(refs, hyps):
        err = sum(r != h for r, h in zip(refs, hyps)) / len(refs)
        return {"cer": err, "wer": err}

    res = lm.regler([_matrice(trames)], ["naan sran"], LABELS, t, alphas=[0.2, 0.5], betas=[-5.0, 1.0],
                    score=score, beam=16)
    assert len(res["essais"]) == 4
    assert res["meilleur"] == min(res["essais"], key=lambda e: (e["cer"], e["wer"])) and res["meilleur"]["cer"] == 0


def test_mesure_assemble_deux_candidats_sans_fuite_ni_bruit():
    import mesure_lm_bci as mes

    natifs = ["Naan sran ɔ ba.", "Be yo kpa naan.", "Kpa tɔ yo ɔ ba."]
    web = ["naan sran kpa yo ɔ ba be", "land line verizon california inc", "kpa tɔ yo ɔ ba"]
    cand, stats = mes.corpus(natifs, web, phrases_exclues=["kpa tɔ yo ɔ ba"])
    assert cand["natif"] == ["naan sran ɔ ba", "be yo kpa naan"]
    assert cand["complet"] == cand["natif"] + ["naan sran kpa yo ɔ ba be"]
    assert stats["natif"]["fuites_retirees"] == 1 and stats["web"]["fuites_retirees"] == 1
    assert stats["web"]["ecartees_non_baoule"] == 1 and stats["web"]["gardees"] == 1
