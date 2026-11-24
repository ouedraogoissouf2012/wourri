#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WOURI — Analyse des feedbacks négatifs

Lit data/feedback_negatif.jsonl et affiche :
  1. Les entrées corpus les plus rejetées (à réécrire en priorité), retrouvées depuis le
     TEXTE SERVI — et le nombre de votes dont l'entrée n'a pas pu être retrouvée
  2. Les intents sans couverture (source=ivr_fallback ou fallback_generic)
  3. Les cultures les plus souvent mal servies

Retrouver l'entrée (#644). Le moteur ne cherche plus l'entrée au moment du 👎 : cette
recherche, faite sans la question de l'agriculteur, pouvait désigner une autre entrée
que celle servie (#528 choisit par la question). Le journal garde le texte servi ;
une entrée est retrouvée si et seulement si UN SEUL « préfixe stable » (son texte avant
la 1re balise {{…}}) ouvre ce texte. Sinon : inconnue — hors saison (#509 C1, le texte
de l'entrée est remplacé par le conseil daté), corpus modifié depuis le vote, ou base
pas encore réimportée depuis le JSON. Jamais une entrée devinée. La colonne
`id_entree_corpus` des anciennes lignes est ignorée : calculée sans la question, elle
mettrait deux vérités dans le même classement.

Dépendances, maintenues par tests/unit/test_corpus_prefixes_stables.py :
  - le journal NÉGATIF tronque le texte à 200 caractères (app/routers/feedback.py) ; le
    journal général tronque à 120 et ne convient pas ;
  - les balises sont celles que try_ivr_exact efface du texte servi
    (app/services/chat/ivr_searcher.py).

Usage :
    python tools/analyze_feedback.py
    python tools/analyze_feedback.py --top 10
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

RACINE = Path(__file__).parent.parent
DATA_FILE = RACINE / "data" / "feedback_negatif.jsonl"
CORPUS_FILE = RACINE / "dictionnaires" / "corpus_ivr.json"
TRONCATURE_JOURNAL_NEGATIF = 200  # reponse_bambara[:200] du journal NÉGATIF (feedback.py)
BALISE = re.compile(r"\{\{[^}]+\}\}")  # même motif que le nettoyage de try_ivr_exact


def load_corpus() -> list[dict]:
    return json.loads(CORPUS_FILE.read_text(encoding="utf-8"))["entries"]


def prefixe_stable(reponse_bambara: str) -> str:
    """Le début du texte que le moteur sert tel quel : avant la 1re balise."""
    texte = reponse_bambara or ""
    balise = BALISE.search(texte)
    return (texte[:balise.start()] if balise else texte).strip()


def prefixes_du_corpus(entrees: list[dict]) -> dict[str, str]:
    return {e["id"]: prefixe_stable(e.get("reponse_bambara")) for e in entrees}


def retrouver_entree(texte_servi: str, prefixes: dict[str, str]) -> Optional[str]:
    """L'id de l'entrée dont le préfixe stable, et lui seul, ouvre le texte servi."""
    texte = (texte_servi or "").strip()
    candidates = [i for i, p in prefixes.items() if p and texte.startswith(p)]
    return candidates[0] if len(candidates) == 1 else None


def classer(feedbacks: list[dict], prefixes: dict[str, str]) -> tuple[Counter, int]:
    """(votes par entrée retrouvée, votes ivr_exact dont l'entrée reste inconnue)."""
    rejetees: Counter = Counter()
    non_retrouves = 0
    for fb in feedbacks:
        if fb.get("source") != "ivr_exact":
            continue  # seule une réponse IVR exacte est le texte d'une entrée du corpus
        entree = retrouver_entree(fb.get("reponse_bambara", ""), prefixes)
        if entree:
            rejetees[entree] += 1
        else:
            non_retrouves += 1
    return rejetees, non_retrouves


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

    # 1. Entrées corpus les plus rejetées, retrouvées depuis le texte servi (#644)
    entry_counter, non_retrouves = classer(feedbacks, prefixes_du_corpus(load_corpus()))
    print(f"\n🔴 Top {top} entrées corpus les plus rejetées (à réécrire) :")
    for entry_id, count in entry_counter.most_common(top):
        print(f"   {count}x  {entry_id}")
    if non_retrouves:
        print(f"   + {non_retrouves} vote(s) ivr_exact sans entrée retrouvée "
              "(hors saison, corpus modifié depuis le vote, ou base non réimportée)")

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
