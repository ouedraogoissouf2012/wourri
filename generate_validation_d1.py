"""
D1 — Export validation locuteur natif
Génère un CSV et un Markdown à partir de corpus_ivr.json
pour validation humaine des 144 phrases bambara.
"""
import json
import csv
import os
from datetime import datetime

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "dictionnaires", "corpus_ivr.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "validation_d1")
os.makedirs(OUT_DIR, exist_ok=True)

CSV_PATH  = os.path.join(OUT_DIR, "validation_phrases.csv")
MD_PATH   = os.path.join(OUT_DIR, "validation_phrases.md")

# Noms lisibles pour intents
INTENT_LABELS = {
    "CONSEIL_PRODUCTION":       "Conseil production",
    "QUESTION_SAISON_PLANTATION": "Saison plantation",
    "QUESTION_RECOLTE":         "Récolte",
    "QUESTION_IRRIGATION":      "Irrigation / eau",
    "QUESTION_ENGRAIS":         "Engrais",
    "QUESTION_STOCKAGE":        "Stockage",
    "QUESTION_VENTE":           "Vente / prix",
    "DIAGNOSTIC_PROBLEME":      "Diagnostic maladie",
    "QUESTION_METEO":           "Météo",
    "QUESTION_GENERALE":        "Conseil général",
}

# Noms lisibles pour cultures
CULTURE_LABELS = {
    "CULTURE_RIZ":      "Riz",
    "CULTURE_MAIS":     "Maïs",
    "CULTURE_ARACHIDE": "Arachide",
    "CULTURE_MANIOC":   "Manioc",
    "CULTURE_IGNAME":   "Igname",
    "CULTURE_MIL":      "Mil",
    "CULTURE_SORGHO":   "Sorgho",
    "CULTURE_COTON":    "Coton",
    "CULTURE_TOMATE":   "Tomate",
    "CULTURE_CACAO":    "Cacao",
    "CULTURE_HARICOT":  "Haricot / niébé",
    "CULTURE_PATATE":   "Patate douce",
    "CULTURE_SESAME":   "Sésame",
    "CULTURE_CAFE":     "Café",
    "CULTURE_ANANAS":   "Ananas",
    "CULTURE_BANANE":   "Banane",
    "CULTURE_GOMBO":    "Gombo",
    "CULTURE_OIGNON":   "Oignon",
    "ANIMAL_POULET":    "Élevage poulet",
    "ANIMAL_BOVIN":     "Élevage bovin",
    "*":                "Toutes cultures",
}


def fmt_cultures(cultures):
    return " / ".join(CULTURE_LABELS.get(c, c) for c in cultures)


def fmt_conditions(conditions):
    if not conditions:
        return ""
    return ", ".join(conditions)


def main():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    entries = data["entries"]
    version = data.get("version", "?")
    total   = len(entries)
    print(f"Corpus v{version} — {total} entrées chargées")

    # ── CSV ──────────────────────────────────────────────────────────────────
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "N°", "ID", "Intent", "Culture(s)", "Conditions",
            "Phrase bambara (à valider)", "Référence français",
            "Score initial", "Validation (OK/KO)", "Correction bambara", "Commentaire"
        ])
        for i, e in enumerate(entries, 1):
            writer.writerow([
                i,
                e["id"],
                INTENT_LABELS.get(e["intent"], e["intent"]),
                fmt_cultures(e["cultures"]),
                fmt_conditions(e.get("conditions", [])),
                e["reponse_bambara"],
                e["reponse_fr"],
                e.get("score_validation", ""),
                "",   # Validation OK/KO — à remplir
                "",   # Correction bambara — à remplir si KO
                "",   # Commentaire libre
            ])
    print(f"CSV  -> {CSV_PATH}")

    # ── MARKDOWN ─────────────────────────────────────────────────────────────
    # Grouper par culture pour faciliter la lecture
    from collections import defaultdict
    by_culture = defaultdict(list)
    for e in entries:
        key = fmt_cultures(e["cultures"])
        by_culture[key].append(e)

    lines = []
    lines.append(f"# Validation D1 — Corpus IVR Wourri v{version}")
    lines.append(f"\n**Date export :** {datetime.today().strftime('%d/%m/%Y')}  ")
    lines.append(f"**Total phrases :** {total}  ")
    lines.append("**Instructions :** Pour chaque phrase bambara, indiquer ✅ (correct) ou ❌ + correction.\n")
    lines.append("---\n")

    for culture_name, ents in sorted(by_culture.items()):
        lines.append(f"\n## {culture_name} ({len(ents)} phrases)\n")
        for i, e in enumerate(ents, 1):
            intent_label = INTENT_LABELS.get(e["intent"], e["intent"])
            cond = fmt_conditions(e.get("conditions", []))
            cond_str = f" _{cond}_" if cond else ""
            lines.append(f"### {i}. {intent_label}{cond_str}")
            lines.append(f"**Français :** {e['reponse_fr']}  ")
            lines.append(f"**Bambara :** {e['reponse_bambara']}  ")
            lines.append(f"**Validation :** ✅ / ❌  ")
            lines.append(f"**Correction :**  ")
            lines.append(f"**Commentaire :**  \n")

    lines.append("---")
    lines.append(f"*Corpus IVR Wourri — généré le {datetime.today().strftime('%d/%m/%Y')}*")

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"MD   -> {MD_PATH}")

    # ── Résumé par culture ────────────────────────────────────────────────────
    print("\n--- Repartition par culture ---")
    for culture_name, ents in sorted(by_culture.items()):
        print(f"  {culture_name:<20} : {len(ents):>3} phrases")
    print(f"\n  TOTAL : {total} phrases pretes pour validation")


if __name__ == "__main__":
    main()
