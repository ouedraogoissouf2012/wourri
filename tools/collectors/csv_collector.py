"""
WOURI - Collecteur CSV (ajouts manuels)
Format CSV: mot_bambara,traduction_francais,categorie
Permet aux locuteurs natifs d'ajouter des mots facilement.
"""
import csv
import os
from .base_collector import BaseCollector, CollectedEntry, CollectedPhrase


class CSVCollector(BaseCollector):
    """Collecte depuis un fichier CSV d'ajouts manuels"""

    def __init__(self, csv_path: str):
        self._csv_path = csv_path

    @property
    def source_name(self) -> str:
        return "csv_manuel"

    def _fetch_raw(self) -> str:
        if not os.path.exists(self._csv_path):
            print(f"[csv] Fichier non trouvé: {self._csv_path} (sera créé avec le template)")
            self._create_template()
            return ""

        with open(self._csv_path, "r", encoding="utf-8") as f:
            return f.read()

    def _create_template(self):
        """Crée un fichier CSV template pour les ajouts manuels"""
        os.makedirs(os.path.dirname(self._csv_path), exist_ok=True)
        with open(self._csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["mot_bambara", "traduction_francais", "categorie", "variantes", "exemples"])
            writer.writerow(["# Ajoutez vos mots ci-dessous", "", "", "", ""])
            writer.writerow(["# Colonnes: mot_bambara, traduction_francais, categorie, variantes (séparées par |), exemples (séparés par |)"])
            writer.writerow(["malo", "riz", "agriculture.cereales", "màlo", "ne bɛ malo sɛnɛ"])
        print(f"[csv] Template créé: {self._csv_path}")

    def _parse_entries(self, raw_data: str) -> list[CollectedEntry]:
        if not raw_data:
            return []

        entries = []
        reader = csv.reader(raw_data.strip().split("\n"))

        header = None
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            if header is None:
                header = row
                continue

            if len(row) < 2:
                continue

            word = row[0].strip()
            fr = row[1].strip()
            category = row[2].strip() if len(row) > 2 else ""
            variants = [v.strip() for v in row[3].split("|")] if len(row) > 3 and row[3] else []
            examples = [e.strip() for e in row[4].split("|")] if len(row) > 4 and row[4] else []

            if word and fr:
                entries.append(CollectedEntry(
                    word=word,
                    translations_fr=[t.strip() for t in fr.split(";")],
                    category=category,
                    variants=variants,
                    examples=examples,
                ))

        return entries
