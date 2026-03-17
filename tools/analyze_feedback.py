#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WOURI — Analyse des feedbacks négatifs

Lit data/feedback_negatif.jsonl et affiche :
  1. Les entrées corpus les plus rejetées (à réécrire en priorité)
  2. Les intents sans couverture (source=ivr_fallback ou fallback_generic)
  3. Les cultures les plus souvent mal servies

Usage :
    python tools/analyze_feedback.py
    python tools/analyze_feedback.py --top 10
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "feedback_negatif.jsonl"


def load_feedbacks() -> list[dict]:
    if not DATA_FILE.exists():
        print(f"[INFO] Aucun feedback négatif enregistré ({DATA_FILE})")
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def analyze(top: int = 5):
    feedbacks = load_feedbacks()
    if not feedbacks:
        return

    print(f"\n{'='*55}")
    print(f"  ANALYSE FEEDBACKS NÉGATIFS — {len(feedbacks)} entrées")
    print(f"{'='*55}")

    # 1. Entrées corpus les plus rejetées
    entry_counter = Counter(
        fb["id_entree_corpus"]
        for fb in feedbacks
        if fb.get("id_entree_corpus")
    )
    print(f"\n🔴 Top {top} entrées corpus les plus rejetées (à réécrire) :")
    for entry_id, count in entry_counter.most_common(top):
        print(f"   {count}x  {entry_id}")

    # 2. Intents non couverts (fallback)
    fallback_intents = Counter(
        fb["intent"]
        for fb in feedbacks
        if fb.get("source") in ("ivr_fallback", "fallback_generic")
        and fb.get("intent")
    )
    print(f"\n🟠 Intents non couverts dans le corpus (fallback) :")
    for intent, count in fallback_intents.most_common(top):
        print(f"   {count}x  {intent}")

    # 3. Cultures mal servies
    culture_counter: Counter = Counter()
    for fb in feedbacks:
        for c in fb.get("cultures", []):
            culture_counter[c] += 1
    print(f"\n🟡 Cultures les plus souvent mal servies :")
    for culture, count in culture_counter.most_common(top):
        print(f"   {count}x  {culture}")

    # 4. Résumé par source
    source_counter = Counter(fb.get("source", "?") for fb in feedbacks)
    print(f"\n📊 Répartition par source :")
    for src, count in source_counter.most_common():
        print(f"   {src}: {count}")

    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    top = 5
    if "--top" in sys.argv:
        idx = sys.argv.index("--top")
        if idx + 1 < len(sys.argv):
            top = int(sys.argv[idx + 1])
    analyze(top=top)
