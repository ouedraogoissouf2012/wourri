#!/usr/bin/env python3
"""
inject_phrases_ivr.py — Injecter les phrases attestees (dioula CI reelles)
dans corpus_ivr.json sous forme de champ 'phrases_attestees'.

Logique de correspondance :
  Une phrase du sentence bank est injectee dans une entree IVR si
  son concept correspond a l'intent OU a l'une des cultures de l'entree.

Aucune modification de reponse_bambara existant.
Nouvelle version : 1.8

Usage:
    python tools/inject_phrases_ivr.py
    python tools/inject_phrases_ivr.py --dry-run   # affiche sans modifier
    python tools/inject_phrases_ivr.py --min-score 2
"""

import json
import argparse
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
IVR_FILE    = BASE_DIR / "dictionnaires" / "corpus_ivr.json"
BANK_FILE   = BASE_DIR / "data" / "dioula_sentence_bank.json"
NEW_VERSION = "1.8"


def load_files():
    ivr  = json.load(open(IVR_FILE,  encoding="utf-8"))
    bank = json.load(open(BANK_FILE, encoding="utf-8"))
    return ivr, bank


def get_phrases_for_entry(entry, bank_by_concept, min_score=1):
    """
    Retourne les phrases attestees pertinentes pour une entree IVR.
    Cherche dans : intent + toutes les cultures de l'entree.
    """
    intent   = entry.get("intent", "")
    cultures = entry.get("cultures", [])
    # '*' = toutes cultures, on ignore pour le matching
    concepts_to_check = [intent] + [c for c in cultures if c != "*"]

    seen  = set()
    found = []
    for concept in concepts_to_check:
        for phrase in bank_by_concept.get(concept, []):
            if phrase["score"] < min_score:
                continue
            t = phrase["text"]
            if t not in seen:
                seen.add(t)
                found.append({
                    "text":    t,
                    "source":  phrase["source"],
                    "concept": concept,
                    "score":   phrase["score"]
                })

    # Trier par score puis longueur (phrases plus riches en premier)
    found.sort(key=lambda x: (-x["score"], -len(x["text"])))
    return found[:5]  # max 5 phrases par entree


def main():
    ap = argparse.ArgumentParser(description="Injection phrases attestees dans corpus_ivr.json")
    ap.add_argument("--dry-run",   action="store_true", help="Affiche sans modifier le fichier")
    ap.add_argument("--min-score", type=int, default=1, help="Score minimum de concepts NLU (defaut: 1)")
    args = ap.parse_args()

    ivr, bank = load_files()
    bank_by_concept = bank.get("sentences_by_concept", {})

    entries        = ivr.get("entries", [])
    total_injected = 0
    total_entries  = 0
    stats          = {}

    for entry in entries:
        phrases = get_phrases_for_entry(entry, bank_by_concept, args.min_score)
        if not phrases:
            continue

        eid = entry.get("id", "?")
        if not args.dry_run:
            entry["phrases_attestees"] = phrases
        else:
            print(f"\n  {eid}")
            for p in phrases:
                print(f"    [{p['score']}] {p['text']}  ({p['source']})")

        total_injected += len(phrases)
        total_entries  += 1
        concept_key = entry.get("intent", "UNKNOWN")
        stats[concept_key] = stats.get(concept_key, 0) + len(phrases)

    print(f"\nResultat : {total_phrases_in_bank(bank_by_concept)} phrases dans la banque")
    print(f"Injection : {total_injected} phrases dans {total_entries}/{len(entries)} entrees IVR\n")
    print("Par intent :")
    for intent, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {intent:<35s} {count:3d} phrases")

    if not args.dry_run:
        # Mise a jour version + note
        ivr["version"] = NEW_VERSION
        ivr[f"ajout_v{NEW_VERSION}"] = (
            f"2026-03-15 — Ajout champ 'phrases_attestees' sur {total_entries} entrees. "
            f"{total_injected} phrases CI Dioula reelles issues de {bank['total_sentences']} "
            f"phrases extraites de 30 transcriptions Access Agriculture. "
            f"Aucune modification de reponse_bambara."
        )

        with open(IVR_FILE, "w", encoding="utf-8") as f:
            json.dump(ivr, f, ensure_ascii=False, indent=2)
        print(f"\nSauvegarde : {IVR_FILE}  (v{NEW_VERSION})")
    else:
        print("\n[dry-run] Aucune modification effectuee.")


def total_phrases_in_bank(bank_by_concept):
    return sum(len(v) for v in bank_by_concept.values())


if __name__ == "__main__":
    main()
