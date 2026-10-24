"""Modèle de langue baoulé pour le décodage CTC d'Omnilingual (#474, ADR-0044, révision du 2026-10-24).

Le CTC du 1B écrit lettre par lettre (décodage « glouton ») et colle ou coupe des mots
(« nansran » pour « naan sran »). Une recherche en faisceau (pyctcdecode) guidée par un modèle
de langue de MOTS corrige une partie de ces erreurs. Le modèle est un trigramme Kneser-Ney
interpolé écrit ici en Python, aux conventions du modèle KenLM de pyctcdecode : testable sans
GPU ni compilation (KenLM demanderait de compiler lmplz sur la machine louée).

Corpus : textes baoulé du registre des sources, normalisés comme les cibles d'entraînement
(`dictee_to_parquet.normalize_text`). Deux règles :
- aucune phrase du test : toute ligne qui en contient une est retirée et comptée (fuite) ;
- pas la Bible (décision du valideur du 2026-10-24 : mot à mot seulement).
α (poids du modèle) et β (bonus par mot) sont choisis sur `dev`, jamais sur `test`.

Vocabulaire du tokenizer omniASR (char_tokenizer) : 0 = blanc CTC (recette : `blank_label=0`),
1–3 = <pad> </s> <unk>, 4 = espace, le reste = un caractère par symbole.

Ce module est recopié tel quel dans les notebooks GPU (cellule %%writefile) :
`python finetune/colab/sync_smoke_test_notebook.py` le resynchronise, un test le vérifie.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import dictee_to_parquet as d2p

BLANC, ESPACE = 0, 4
SPECIAUX = {1, 2, 3}
DISCOUNT = 0.75
UNK_LOG10 = -7.0  # mot inconnu du corpus ; pyctcdecode ajoute en plus son unk_score_offset


def preparer_corpus(textes, phrases_test, min_mots=2) -> tuple[list[str], dict]:
    """Lignes normalisées, sans aucune ligne contenant une phrase du test (avec les comptes)."""
    tests = sorted({d2p.normalize_text(p) for p in phrases_test} - {""}, key=len, reverse=True)
    fuite = re.compile(r"(?<!\S)(?:" + "|".join(re.escape(t) for t in tests) + r")(?!\S)") if tests else None
    lignes, n_fuites = [], 0
    for texte in textes:
        for morceau in re.split(r"[.!?;\n]+", texte or ""):
            ligne = d2p.normalize_text(morceau)
            if len(ligne.split()) < min_mots:
                continue
            if fuite is not None and fuite.search(ligne):
                n_fuites += 1
                continue
            lignes.append(ligne)
    return lignes, {"lignes": len(lignes), "fuites_retirees": n_fuites,
                    "mots": sum(len(l.split()) for l in lignes)}


SEUIL_BAOULE = 0.6


def filtrer_baoule(lignes, reference, seuil=SEUIL_BAOULE) -> tuple[list[str], int]:
    """Garde les lignes dont au moins `seuil` des mots sont dans `reference` (vocabulaire des textes
    natifs fiables : Common Voice, dictée, Zenodo, SMOL). Mesuré le 2026-10-24 sur le corpus web :
    la répartition est bimodale ; sous 50 % ce sont des pages anglaises (annonces, annuaires), du
    français et d'autres langues ivoiriennes étiquetées baoulé ; au-dessus de 60 %, du baoulé."""
    gardees = [l for l in lignes if sum(w in reference for w in l.split()) >= seuil * len(l.split())]
    return gardees, len(lignes) - len(gardees)


class Trigramme:
    """Trigramme Kneser-Ney interpolé (log10, comme KenLM). <s> et </s> bornent chaque ligne."""

    def __init__(self, lignes, min_trigramme=1):
        c3 = Counter()
        for ligne in lignes:
            mots = ["<s>", "<s>"] + ligne.split() + ["</s>"]
            for i in range(2, len(mots)):
                c3[tuple(mots[i - 2:i + 1])] += 1
        self.c3 = {k: v for k, v in c3.items() if v >= min_trigramme}
        self.ctx3, self.types3, self.cont2 = Counter(), Counter(), Counter()
        for (u, v, w), n in self.c3.items():
            self.ctx3[(u, v)] += n          # c(u, v, ·)
            self.types3[(u, v)] += 1        # N1+(u, v, ·)
            self.cont2[(v, w)] += 1         # N1+(·, v, w)
        self.ctx2, self.types2, self.cont1 = Counter(), Counter(), Counter()
        for (v, w), n in self.cont2.items():
            self.ctx2[v] += n               # N1+(·, v, ·)
            self.types2[v] += 1             # N1+(v, ·) parmi les continuations
            self.cont1[w] += 1              # N1+(·, w)
        self.total1 = sum(self.cont1.values())
        self.vocab = set(self.cont1) - {"<s>", "</s>"}

    def p1(self, w) -> float:
        n = self.cont1.get(w, 0)
        return n / self.total1 if n else 0.0

    def p2(self, v, w) -> float:
        base = self.p1(w)
        tot = self.ctx2.get(v, 0)
        if not tot:
            return base
        return max(self.cont2.get((v, w), 0) - DISCOUNT, 0) / tot + DISCOUNT * self.types2[v] / tot * base

    def p3(self, u, v, w) -> float:
        base = self.p2(v, w)
        tot = self.ctx3.get((u, v), 0)
        if not tot:
            return base
        return max(self.c3.get((u, v, w), 0) - DISCOUNT, 0) / tot + DISCOUNT * self.types3[(u, v)] / tot * base

    def log10(self, contexte, w) -> float:
        p = self.p3(contexte[0], contexte[1], w)
        return math.log10(p) if p > 0 else UNK_LOG10


def modele_pyctcdecode(trigramme, alpha, beta, unk_score_offset=-10.0):
    """Modèle de langue pour pyctcdecode : mêmes formules que son modèle KenLM (score_boundary)."""
    from pyctcdecode.language_model import AVG_TOKEN_LEN, LOG_BASE_CHANGE_FACTOR, AbstractLanguageModel, CharTrie

    class ModeleBci(AbstractLanguageModel):
        def __init__(self):
            self.alpha, self.beta, self.unk_score_offset = alpha, beta, unk_score_offset
            self._trie = CharTrie.fromkeys(trigramme.vocab)

        @property
        def order(self) -> int:
            return 3

        def get_start_state(self):
            return ("<s>", "<s>")

        def score_partial_token(self, partial_token: str) -> float:
            unk = self.unk_score_offset * int(self._trie.has_node(partial_token) == 0)
            return unk * len(partial_token) / AVG_TOKEN_LEN if len(partial_token) > AVG_TOKEN_LEN else unk

        def score(self, prev_state, word, is_last_word=False):
            s = trigramme.log10(prev_state, word)
            if word not in trigramme.vocab:
                s += self.unk_score_offset
            etat = (prev_state[1], word)
            if is_last_word:
                s += trigramme.log10(etat, "</s>")
            return self.alpha * s * LOG_BASE_CHANGE_FACTOR + self.beta, etat

    return ModeleBci()


def alphabet_de(textes) -> set[str]:
    """Caractères des textes normalisés (cibles d'entraînement et corpus)."""
    return {c for t in textes for c in d2p.normalize_text(t) if not c.isspace()}


def colonnes(pieces, alphabet) -> tuple[list[int], list[str]]:
    """Symboles gardés pour décoder (blanc d'abord, espace, caractères de l'alphabet baoulé)
    et leurs étiquettes pyctcdecode. Les autres colonnes (milliers de caractères d'autres
    écritures) sont retirées APRÈS le log-softmax : la masse perdue est négligeable."""
    ids = [BLANC, ESPACE] + [i for i, p in enumerate(pieces)
                             if i not in SPECIAUX | {BLANC, ESPACE} and p in alphabet]
    return ids, ["" if i == BLANC else " " if i == ESPACE else pieces[i] for i in ids]


def glouton(matrice, labels) -> str:
    """Décodage CTC glouton sur la matrice réduite (même règle que le pipeline Omnilingual)."""
    out, prec = [], None
    for i in matrice.argmax(axis=1):
        if i != prec and labels[i] != "":
            out.append(labels[i])
        prec = i
    return re.sub(r"\s+", " ", "".join(out)).strip()


def brancher(pipeline, ids, labels, decodeur=None, capture=None, beam=64):
    """Remplace le décodage glouton du pipeline : log-probas réduites aux colonnes `ids`, puis
    recherche en faisceau si `decodeur`, sinon glouton. `capture` (liste) reçoit les matrices."""
    import torch
    from fairseq2.nn import BatchLayout

    index = torch.tensor(ids)

    def appliquer(batch):
        layout = BatchLayout(batch.source_seqs.shape, seq_lens=batch.source_seq_lens, device=batch.source_seqs.device)
        logits, bl_out = pipeline.model(batch.source_seqs, layout)
        lp = torch.log_softmax(logits.float(), dim=-1)[..., index.to(logits.device)].cpu().numpy()
        textes = []
        for i in range(lp.shape[0]):
            m = lp[i, : int(bl_out.seq_lens[i])]
            if capture is not None:
                capture.append(m)
            textes.append(decodeur.decode(m, beam_width=beam) if decodeur else glouton(m, labels))
        return textes

    pipeline._apply_model_wav2vec2asr = appliquer
    return pipeline


def decodeur(labels, modele):
    from pyctcdecode.alphabet import Alphabet
    from pyctcdecode.decoder import BeamSearchDecoderCTC

    return BeamSearchDecoderCTC(Alphabet.build_alphabet(labels), modele)


def decoder_tout(dec, matrices, beam=64, processus=0) -> list[str]:
    """Décode toutes les matrices ; `processus` > 0 : en parallèle (Linux). Le pool est créé APRÈS
    le décodeur : pyctcdecode le retrouve par fork, sans copier le modèle de langue."""
    if processus <= 0:
        return [dec.decode(m, beam_width=beam) for m in matrices]
    import multiprocessing

    with multiprocessing.get_context("fork").Pool(processus) as pool:
        return dec.decode_batch(pool, matrices, beam_width=beam)


def regler(matrices, refs, labels, trigramme, alphas, betas, score, beam=64, processus=0) -> dict:
    """Meilleur (α, β) par CER sur ces clips (dev). `score(refs, hyps)` = protocole 0003."""
    essais = []
    for a in alphas:
        for b in betas:
            hyps = decoder_tout(decodeur(labels, modele_pyctcdecode(trigramme, a, b)), matrices, beam, processus)
            r = score(refs, hyps)
            essais.append({"alpha": a, "beta": b, "cer": r["cer"], "wer": r["wer"]})
    return {"meilleur": min(essais, key=lambda e: (e["cer"], e["wer"])), "essais": essais}
