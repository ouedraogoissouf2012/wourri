#!/usr/bin/env python3
"""
extract_sentence_bank.py — Extraire les phrases dioula agricoles depuis les
archives vocab.json et les organiser par concept NLU.

Usage:
    python tools/extract_sentence_bank.py
    python tools/extract_sentence_bank.py --transcription mon_texte.txt
    python tools/extract_sentence_bank.py --min-score 2

Sortie: data/dioula_sentence_bank.json
"""

import json
import re
import argparse
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
NLU_FILE  = BASE_DIR / "dictionnaires" / "nlu_concepts.json"
VOCAB_DIR = BASE_DIR / "data" / "validation_sources"
OUTPUT    = BASE_DIR / "data" / "dioula_sentence_bank.json"

# Mots trop courts ou trop génériques à ignorer même s'ils sont dans le NLU
SKIP_KEYWORDS = {"a", "o", "i", "n", "ka", "ko", "ni", "ye", "bi", "la", "ma",
                 "wa", "da", "di", "do", "na", "mi", "wi", "to", "bo", "jo",
                 "aide", "aider", "savoir", "apprendre", "conseil", "conseils",
                 "information", "informer", "paysan", "fermier", "cultivateur",
                 "agriculteur", "planteur", "bonjour", "bonsoir", "salut",
                 "hello", "oui", "non", "merci"}


# ---------------------------------------------------------------------------
# Chargement NLU
# ---------------------------------------------------------------------------

def load_nlu_keywords(nlu_file):
    """Retourne (kw→[concepts], concept→[kws])."""
    with open(nlu_file, encoding="utf-8") as f:
        nlu = json.load(f)

    kw_to_concepts  = defaultdict(list)
    concept_to_keys = {}

    for cname, cdata in nlu.get("concepts", {}).items():
        all_keys = cdata.get("keywords", []) + cdata.get("partial", [])
        concept_to_keys[cname] = all_keys
        for kw in all_keys:
            kw = kw.lower().strip()
            if len(kw) < 3 or kw in SKIP_KEYWORDS:
                continue
            kw_to_concepts[kw].append(cname)

    return kw_to_concepts, concept_to_keys


# ---------------------------------------------------------------------------
# Scoring d'une phrase
# ---------------------------------------------------------------------------

def score_sentence(sentence, kw_to_concepts):
    """Retourne (score, [concepts], [keywords_trouvés])."""
    s = sentence.lower()
    matched_concepts = set()
    matched_kws = []

    for kw, concepts in kw_to_concepts.items():
        # Correspondance sous-chaîne pour mots > 4 chars, mot entier sinon
        if len(kw) > 4:
            found = kw in s
        else:
            found = bool(re.search(r'(?<!\w)' + re.escape(kw) + r'(?!\w)', s))

        if found:
            matched_concepts.update(concepts)
            matched_kws.append(kw)

    return len(matched_concepts), sorted(matched_concepts), sorted(set(matched_kws))


# ---------------------------------------------------------------------------
# Extraction depuis les archives vocab.json
# ---------------------------------------------------------------------------

# Regex: phrases entre guillemets simples d'au moins 10 chars
_QUOTE_RE = re.compile(r"'([^']{10,}?)'")
# Préfixes français à exclure
_FR_PREFIXES = ("le ", "la ", "les ", "un ", "une ", "des ", "pour ", "dans ",
                "ce ", "si ", "de ", "du ", "au ", "aux ", "en ", "il ", "elle ",
                "ils ", "elles ", "on ", "nous ", "vous ", "que ", "qui ",
                "quand ", "comment ", "parce ", "=", "source:", "note:", "video",
                "contexte:", "proverbe", "arbre ", "graines ", "maladie ", "terme ",
                "attention:", "rejeté", "confirmé", "ajouté", "déjà ")

# Mots français fréquents qui trahissent une gloss
_FR_WORDS = {"le", "la", "les", "un", "une", "des", "est", "sont", "avec",
             "pour", "dans", "sur", "par", "qui", "que", "quand", "comment",
             "arbre", "culture", "maladie", "terme", "graines", "fruit",
             "condiment", "engrais", "village", "champ", "eau", "sol"}


def _is_bambara(text):
    t = text.lower().strip()
    # Rejeter les artéfacts techniques/méta
    if t.startswith(("=", "(", "action_", "culture_", "probleme_", "role_")):
        return False
    # Rejeter si contient des slash (définitions fr/fr)
    if "/" in t and len(t) < 40:
        return False
    # Rejeter si commence par un préfixe français/technique
    if any(t.startswith(p) for p in _FR_PREFIXES):
        return False
    # Rejeter si contient trop de mots français courants (> 30% des tokens)
    tokens = t.split()
    if not tokens:
        return False
    fr_count = sum(1 for tok in tokens if tok.rstrip(".,;:") in _FR_WORDS)
    return fr_count / len(tokens) < 0.3


def extract_from_archives(vocab_dir, kw_to_concepts, min_score=1):
    bank = defaultdict(list)
    total_files = 0

    for vf in sorted(Path(vocab_dir).glob("*_vocab.json")):
        try:
            data = json.load(open(vf, encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠  {vf.name}: {e}")
            continue

        video_id = data.get("video_id", vf.stem.split("_")[2] if "_" in vf.stem else vf.stem)
        items = data.get("candidates_analyzed", []) + data.get("already_in_nlu", [])
        added = 0

        for item in items:
            for sent in _QUOTE_RE.findall(item.get("note", "")):
                sent = sent.strip()
                if not sent or not _is_bambara(sent):
                    continue
                score, concepts, kws = score_sentence(sent, kw_to_concepts)
                if score < min_score:
                    continue
                for c in concepts:
                    existing = {e["text"] for e in bank[c]}
                    if sent not in existing:
                        bank[c].append({"text": sent, "source": f"video_{video_id}",
                                        "keywords": kws, "score": score})
                        added += 1

        if added:
            print(f"  + {vf.name:55s} {added:3d} phrases")
        total_files += 1

    print(f"  -> {total_files} archives lues")
    return bank


# ---------------------------------------------------------------------------
# Extraction depuis une transcription brute
# ---------------------------------------------------------------------------

def extract_from_transcription(text, kw_to_concepts, source_label="input", min_score=1):
    bank = defaultdict(list)

    # Découpé par timestamps [MM:SS]
    segments = re.split(r'\[\d+:\d+\]', text)

    for seg in segments:
        seg = seg.strip()
        if len(seg) < 20:
            continue

        # Découper sur espaces multiples (pauses naturelles dans l'ASR)
        chunks = re.split(r'\s{3,}', seg)
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 15:
                continue
            score, concepts, kws = score_sentence(chunk, kw_to_concepts)
            if score < min_score:
                continue
            for c in concepts:
                existing = {e["text"] for e in bank[c]}
                if chunk not in existing:
                    bank[c].append({"text": chunk, "source": source_label,
                                    "keywords": kws, "score": score})
    return bank


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

def merge(b1, b2):
    merged = defaultdict(list, {k: list(v) for k, v in b1.items()})
    for concept, sents in b2.items():
        existing = {e["text"] for e in merged[concept]}
        for s in sents:
            if s["text"] not in existing:
                merged[concept].append(s)
                existing.add(s["text"])
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Banque de phrases dioula agricoles")
    ap.add_argument("--transcription", default=None,
                    help="Fichier texte de transcription à analyser en supplément")
    ap.add_argument("--min-score", type=int, default=1,
                    help="Nombre minimum de concepts NLU par phrase (défaut: 1)")
    ap.add_argument("--output", default=str(OUTPUT))
    args = ap.parse_args()

    print("Wourri -- Extraction de phrases dioula agricoles")
    print(f"    NLU      : {NLU_FILE}")
    print(f"    Archives : {VOCAB_DIR}")
    print(f"    Score min: {args.min_score}")
    print()

    kw_to_concepts, _ = load_nlu_keywords(NLU_FILE)
    print(f"NLU: {len(kw_to_concepts)} mots-cles actifs dans {len(_)} concepts\n")

    print("Extraction depuis archives vocab.json...")
    bank = extract_from_archives(VOCAB_DIR, kw_to_concepts, args.min_score)
    print()

    if args.transcription:
        print(f"Extraction depuis: {args.transcription}")
        with open(args.transcription, encoding="utf-8") as f:
            text = f.read()
        label = Path(args.transcription).stem
        trans_bank = extract_from_transcription(text, kw_to_concepts, label, args.min_score)
        bank = merge(bank, trans_bank)
        added = sum(len(v) for v in trans_bank.values())
        print(f"    → {added} phrases supplémentaires\n")

    # Trier par score décroissant dans chaque concept
    for c in bank:
        bank[c].sort(key=lambda x: x["score"], reverse=True)

    total = sum(len(v) for v in bank.values())
    print(f"Resultat : {total} phrases dans {len(bank)} concepts\n")
    for c, sents in sorted(bank.items(), key=lambda x: -len(x[1])):
        print(f"  {c:<35s} {len(sents):3d} phrases")

    out = {
        "description": "Banque de phrases dioula CI extraites des transcriptions Access Agriculture",
        "version": "1.0",
        "date_generated": "2026-03-15",
        "total_sentences": total,
        "min_score_used": args.min_score,
        "usage": (
            "Utiliser pour enrichir corpus_ivr.json et améliorer la naturalité "
            "des réponses du bot en CI Dioula. Ajouter --transcription <fichier.txt> "
            "pour traiter une nouvelle transcription."
        ),
        "sentences_by_concept": {k: v for k, v in
                                  sorted(bank.items(), key=lambda x: -len(x[1]))}
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\nSauvegarde : {args.output}")


if __name__ == "__main__":
    main()
