"""
WOURI - Pipeline de collecte et génération du dictionnaire
Orchestre: Collecte -> Normalisation -> Dédoublonnage -> Catégorisation -> Export JSON

Usage:
  python -m tools.pipeline                    # Toutes les sources
  python -m tools.pipeline --source bamadaba  # Une seule source
  python -m tools.pipeline --source csv       # Juste le CSV manuel
"""
import json
import os
import sys
from datetime import datetime
from collections import defaultdict

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.collectors.bamadaba_collector import BamadabaCollector
from tools.collectors.huggingface_collector import HuggingFaceCollector
from tools.collectors.csv_collector import CSVCollector
from tools.collectors.base_collector import CollectedEntry, CollectedPhrase


# Patterns grammaticaux Bambara -> Français
PATTERNS_BAM_FR = {
    "ne bɛ fɛ ka": "Je veux",
    "ne bɛ fɛ": "Je veux",
    "i bɛ fɛ ka": "Tu veux",
    "a bɛ fɛ ka": "Il/Elle veut",
    "an bɛ fɛ ka": "Nous voulons",
    "aw bɛ fɛ ka": "Vous voulez",
    "u bɛ fɛ ka": "Ils/Elles veulent",
    "ne bɛ se ka": "Je peux",
    "i bɛ se ka": "Tu peux",
    "ne bɛ ka": "Je fais",
    "ne tɛ": "Je ne... pas",
    "i tɛ": "Tu ne... pas",
    "ne ye": "J'ai",
    "i ye": "Tu as",
    "a ye": "Il/Elle a",
    "mun ye": "Qu'est-ce que",
    "mun bɛ": "Qu'y a-t-il",
    "cogo di": "Comment",
    "ka malo sɛnɛ": "cultiver du riz",
    "ka kaba sɛnɛ": "cultiver du maïs",
    "ka tiga sɛnɛ": "cultiver des arachides",
    "ka ɲɔ sɛnɛ": "cultiver du mil",
    "ka foro sɛnɛ": "cultiver un champ",
}

# Patterns grammaticaux Français -> Bambara
PATTERNS_FR_BAM = {
    "je veux": "ne bɛ fɛ ka",
    "tu veux": "i bɛ fɛ ka",
    "il veut": "a bɛ fɛ ka",
    "je peux": "ne bɛ se ka",
    "je fais": "ne bɛ ka",
    "je ne": "ne tɛ",
    "qu'est-ce que": "mun ye",
    "cultiver du riz": "ka malo sɛnɛ",
    "cultiver du maïs": "ka kaba sɛnɛ",
    "cultiver des arachides": "ka tiga sɛnɛ",
}


def deduplicate_entries(entries: list[CollectedEntry]) -> list[CollectedEntry]:
    """Dédoublonne les entrées en fusionnant les traductions"""
    merged: dict[str, CollectedEntry] = {}

    for entry in entries:
        key = entry.word.lower().strip()
        if key not in merged:
            merged[key] = entry
        else:
            existing = merged[key]
            # Fusionner les traductions
            for t in entry.translations_fr:
                if t and t not in existing.translations_fr:
                    existing.translations_fr.append(t)
            # Fusionner les variantes
            for v in entry.variants:
                if v and v not in existing.variants:
                    existing.variants.append(v)
            # Fusionner les exemples
            for e in entry.examples:
                if e and e not in existing.examples:
                    existing.examples.append(e)
            # Garder la catégorie la plus spécifique
            if entry.category and (not existing.category or existing.category == "general"):
                existing.category = entry.category
            # Garder le POS si manquant
            if entry.part_of_speech and not existing.part_of_speech:
                existing.part_of_speech = entry.part_of_speech

    return list(merged.values())


def deduplicate_phrases(phrases: list[CollectedPhrase]) -> list[CollectedPhrase]:
    """Dédoublonne les phrases"""
    seen = set()
    unique = []
    for p in phrases:
        key = p.bam.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def export_dictionary(entries: list[CollectedEntry], output_path: str):
    """Exporte les mots au format JSON du dictionnaire"""
    mots = {}
    categories_count = defaultdict(int)

    for entry in entries:
        mots[entry.word] = {
            "fr": entry.translations_fr,
            "categorie": entry.category,
            "pos": entry.part_of_speech,
            "source": entry.source,
            "variantes": entry.variants,
            "exemples": entry.examples[:3],  # Max 3 exemples
        }
        categories_count[entry.category] += 1

    data = {
        "metadata": {
            "langue": "bambara",
            "code_iso": "bam",
            "version": "1.0.0",
            "total_mots": len(mots),
            "date_generation": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "categories": dict(categories_count),
        },
        "mots": mots,
        "patterns_bam_fr": PATTERNS_BAM_FR,
        "patterns_fr_bam": PATTERNS_FR_BAM,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[Export] Dictionnaire exporté: {output_path}")
    print(f"  - {len(mots)} mots")
    print(f"  - {len(PATTERNS_BAM_FR)} patterns BAM->FR")
    print(f"  - {len(PATTERNS_FR_BAM)} patterns FR->BAM")
    print(f"  - Catégories: {dict(categories_count)}")


def export_phrases(phrases: list[CollectedPhrase], output_path: str):
    """Exporte les phrases parallèles"""
    data = {
        "metadata": {
            "total_phrases": len(phrases),
            "date_generation": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "phrases": [
            {"bam": p.bam, "fr": p.fr, "source": p.source}
            for p in phrases
        ],
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[Export] Phrases exportées: {output_path}")
    print(f"  - {len(phrases)} phrases parallèles")


def run_pipeline(sources: list[str] = None):
    """Exécute le pipeline complet"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dict_dir = os.path.join(base_dir, "dictionnaires")
    csv_path = os.path.join(dict_dir, "sources", "manuel.csv")

    all_entries: list[CollectedEntry] = []
    all_phrases: list[CollectedPhrase] = []

    # Déterminer quelles sources utiliser
    collectors = []
    if sources is None or "bamadaba" in sources:
        collectors.append(("bamadaba", BamadabaCollector()))
    if sources is None or "huggingface" in sources:
        collectors.append(("huggingface", HuggingFaceCollector()))
    if sources is None or "csv" in sources:
        collectors.append(("csv", CSVCollector(csv_path)))

    # Collecter depuis chaque source
    for name, collector in collectors:
        print(f"\n{'='*60}")
        print(f"  Source: {name}")
        print(f"{'='*60}")
        try:
            entries, phrases = collector.collect()
            all_entries.extend(entries)
            all_phrases.extend(phrases)
        except Exception as e:
            print(f"[ERREUR] {name}: {e}")
            import traceback
            traceback.print_exc()

    # Dédoublonner
    print(f"\n{'='*60}")
    print(f"  Fusion et dédoublonnage")
    print(f"{'='*60}")

    before_entries = len(all_entries)
    all_entries = deduplicate_entries(all_entries)
    print(f"  Mots: {before_entries} -> {len(all_entries)} (dédoublonnés)")

    before_phrases = len(all_phrases)
    all_phrases = deduplicate_phrases(all_phrases)
    print(f"  Phrases: {before_phrases} -> {len(all_phrases)} (dédoublonnées)")

    # Exporter
    print(f"\n{'='*60}")
    print(f"  Export JSON")
    print(f"{'='*60}")

    dict_output = os.path.join(dict_dir, "bambara_francais.json")
    phrases_output = os.path.join(dict_dir, "bambara_phrases.json")

    export_dictionary(all_entries, dict_output)
    if all_phrases:
        export_phrases(all_phrases, phrases_output)

    print(f"\n{'='*60}")
    print(f"  Pipeline terminé !")
    print(f"  Dictionnaire: {dict_output}")
    if all_phrases:
        print(f"  Phrases: {phrases_output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline de collecte du dictionnaire Bambara")
    parser.add_argument("--source", choices=["bamadaba", "huggingface", "csv", "all"], default="all")
    args = parser.parse_args()

    if args.source == "all":
        run_pipeline()
    else:
        run_pipeline([args.source])
