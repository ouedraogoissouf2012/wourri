"""
C5 - Reporting feedback Wourri
Lit logs/feedback.jsonl et produit des stats par intent / culture / source.
Sortie : console + logs/rapport_feedback.json
"""
import json
import os
from collections import defaultdict
from datetime import datetime

FEEDBACK_LOG = os.path.join(os.path.dirname(__file__), "logs", "feedback.jsonl")
RAPPORT_PATH = os.path.join(os.path.dirname(__file__), "logs", "rapport_feedback.json")

INTENT_LABELS = {
    "CONSEIL_PRODUCTION":         "Conseil production",
    "QUESTION_SAISON_PLANTATION": "Saison plantation",
    "QUESTION_RECOLTE":           "Recolte",
    "QUESTION_IRRIGATION":        "Irrigation",
    "QUESTION_ENGRAIS":           "Engrais",
    "QUESTION_STOCKAGE":          "Stockage",
    "QUESTION_VENTE":             "Vente / prix",
    "DIAGNOSTIC_PROBLEME":        "Diagnostic maladie",
    "QUESTION_METEO":             "Meteo",
    "QUESTION_GENERALE":          "Conseil general",
}

CULTURE_LABELS = {
    "CULTURE_RIZ":      "Riz",
    "CULTURE_MAIS":     "Mais",
    "CULTURE_ARACHIDE": "Arachide",
    "CULTURE_MANIOC":   "Manioc",
    "CULTURE_IGNAME":   "Igname",
    "CULTURE_MIL":      "Mil",
    "CULTURE_SORGHO":   "Sorgho",
    "CULTURE_COTON":    "Coton",
    "CULTURE_TOMATE":   "Tomate",
    "CULTURE_CACAO":    "Cacao",
    "CULTURE_HARICOT":  "Haricot",
    "CULTURE_PATATE":   "Patate douce",
    "CULTURE_SESAME":   "Sesame",
    "CULTURE_CAFE":     "Cafe",
    "CULTURE_ANANAS":   "Ananas",
    "CULTURE_BANANE":   "Banane",
    "CULTURE_GOMBO":    "Gombo",
    "CULTURE_OIGNON":   "Oignon",
}


def charger_feedbacks():
    if not os.path.exists(FEEDBACK_LOG):
        return []
    lignes = []
    with open(FEEDBACK_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lignes.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return lignes


def analyser(feedbacks):
    total = len(feedbacks)
    if total == 0:
        return None

    positifs = [f for f in feedbacks if f.get("vote") == "positif"]
    negatifs = [f for f in feedbacks if f.get("vote") == "negatif"]

    # ── Par intent ───────────────────────────────────────────────────────────
    by_intent = defaultdict(lambda: {"positif": 0, "negatif": 0, "sources": defaultdict(int)})
    for f in feedbacks:
        intent = f.get("intent") or "INCONNU"
        vote   = f.get("vote", "inconnu")
        source = f.get("source", "unknown")
        by_intent[intent][vote] += 1
        by_intent[intent]["sources"][source] += 1

    # ── Par culture ──────────────────────────────────────────────────────────
    by_culture = defaultdict(lambda: {"positif": 0, "negatif": 0})
    for f in feedbacks:
        cultures = f.get("cultures") or ["*"]
        vote     = f.get("vote", "inconnu")
        for c in cultures:
            by_culture[c][vote] += 1

    # ── Par source ───────────────────────────────────────────────────────────
    by_source = defaultdict(lambda: {"positif": 0, "negatif": 0})
    for f in feedbacks:
        source = f.get("source", "unknown")
        vote   = f.get("vote", "inconnu")
        by_source[source][vote] += 1

    return {
        "genere_le": datetime.utcnow().isoformat(),
        "total_feedbacks": total,
        "total_positifs": len(positifs),
        "total_negatifs": len(negatifs),
        "taux_satisfaction": round(len(positifs) / total * 100, 1) if total else 0,
        "par_intent": {k: dict(v, sources=dict(v["sources"])) for k, v in by_intent.items()},
        "par_culture": {k: dict(v) for k, v in by_culture.items()},
        "par_source": {k: dict(v) for k, v in by_source.items()},
    }


def afficher(rapport):
    total = rapport["total_feedbacks"]
    pos   = rapport["total_positifs"]
    neg   = rapport["total_negatifs"]
    taux  = rapport["taux_satisfaction"]

    print("=" * 55)
    print("  RAPPORT C5 - Feedback Wourri")
    print(f"  Genere le : {rapport['genere_le'][:10]}")
    print("=" * 55)
    print(f"  Total feedbacks : {total}")
    print(f"  Positifs (+)    : {pos}")
    print(f"  Negatifs (-)    : {neg}")
    print(f"  Satisfaction    : {taux}%")

    # ── Par source ───────────────────────────────────────────────────────────
    print("\n--- Par source ---")
    for src, v in sorted(rapport["par_source"].items()):
        t = v["positif"] + v["negatif"]
        pct = round(v["positif"] / t * 100) if t else 0
        print(f"  {src:<20} : {t:>3} votes  {pct:>3}% OK")

    # ── Par intent ───────────────────────────────────────────────────────────
    print("\n--- Par intent (trie par taux negatif) ---")
    intents = []
    for intent, v in rapport["par_intent"].items():
        t = v["positif"] + v["negatif"]
        pct_neg = round(v["negatif"] / t * 100) if t else 0
        label = INTENT_LABELS.get(intent, intent)
        intents.append((pct_neg, t, label, intent))
    for pct_neg, t, label, intent in sorted(intents, reverse=True):
        flag = " <-- ATTENTION" if pct_neg >= 40 else ""
        print(f"  {label:<25} : {t:>3} votes  {pct_neg:>3}% negatif{flag}")

    # ── Par culture ──────────────────────────────────────────────────────────
    print("\n--- Par culture (trie par taux negatif) ---")
    cultures = []
    for cult, v in rapport["par_culture"].items():
        t = v["positif"] + v["negatif"]
        pct_neg = round(v["negatif"] / t * 100) if t else 0
        label = CULTURE_LABELS.get(cult, cult)
        cultures.append((pct_neg, t, label))
    for pct_neg, t, label in sorted(cultures, reverse=True):
        flag = " <-- ATTENTION" if pct_neg >= 40 else ""
        print(f"  {label:<20} : {t:>3} votes  {pct_neg:>3}% negatif{flag}")

    print("=" * 55)


def main():
    feedbacks = charger_feedbacks()

    if not feedbacks:
        print(f"Aucun feedback trouve dans : {FEEDBACK_LOG}")
        print("Le fichier sera cree automatiquement apres les premiers retours utilisateurs.")
        # Creer un rapport vide pour reference
        rapport_vide = {
            "genere_le": datetime.utcnow().isoformat(),
            "total_feedbacks": 0,
            "note": "Aucun feedback recu pour l'instant.",
        }
        os.makedirs(os.path.dirname(RAPPORT_PATH), exist_ok=True)
        with open(RAPPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(rapport_vide, f, ensure_ascii=False, indent=2)
        print(f"Rapport vide cree : {RAPPORT_PATH}")
        return

    rapport = analyser(feedbacks)
    afficher(rapport)

    os.makedirs(os.path.dirname(RAPPORT_PATH), exist_ok=True)
    with open(RAPPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print(f"\nRapport JSON sauvegarde : {RAPPORT_PATH}")


if __name__ == "__main__":
    main()
