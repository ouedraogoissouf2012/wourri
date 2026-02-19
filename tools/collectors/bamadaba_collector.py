"""
WOURI - Collecteur Bamadaba (dictionnaire Bambara-Francais)
Source: GitHub maslinych/bamadaba - 13 000+ entrees
Format: SIL Toolbox - balises: lx, ps, gf, gvf, smf, xv, xf, va
"""
import re
import urllib.request
from .base_collector import BaseCollector, CollectedEntry


POS_MAP = {
    "n": "nom",
    "n.prop": "nom propre",
    "v": "verbe",
    "vt": "verbe transitif",
    "vi": "verbe intransitif",
    "vq": "verbe qualitatif",
    "adj": "adjectif",
    "adv": "adverbe",
    "pp": "postposition",
    "conj": "conjonction",
    "dtm": "determinant",
    "prn": "pronom",
    "ptcp": "particule",
    "intj": "interjection",
    "num": "nombre",
    "cop": "copule",
    "prep": "preposition",
    "pers": "pronom personnel",
    "pm": "marqueur predicatif",
}

CATEGORY_KEYWORDS = {
    "agriculture": ["cultiver", "semer", "recolte", "champ", "terre", "sol", "engrais",
                     "plantation", "agriculture", "plante", "graine", "semence", "labour"],
    "agriculture.cereales": ["riz", "mais", "mil", "sorgho", "ble", "fonio", "cereale"],
    "agriculture.legumes": ["tomate", "oignon", "gombo", "piment", "aubergine", "carotte",
                            "haricot", "arachide", "legume"],
    "agriculture.fruits": ["mangue", "banane", "orange", "citron", "papaye", "ananas",
                           "fruit", "noix"],
    "agriculture.elevage": ["vache", "mouton", "chevre", "poulet", "boeuf", "troupeau",
                            "elevage", "betail", "animal"],
    "meteo": ["pluie", "soleil", "vent", "chaleur", "froid", "saison", "seche",
              "nuage", "orage", "ciel", "temperature"],
    "nature": ["eau", "riviere", "fleuve", "foret", "arbre", "herbe", "montagne", "pierre"],
    "sante": ["maladie", "medicament", "douleur", "fievre", "sante", "soigner",
              "traitement", "guerir", "hopital", "medecin"],
    "commerce": ["vendre", "acheter", "prix", "marche", "argent", "commerce", "payer"],
    "famille": ["pere", "mere", "enfant", "frere", "soeur", "famille", "mari",
                "femme", "fils", "fille"],
    "corps": ["tete", "main", "pied", "oeil", "bouche", "ventre", "dos", "bras",
              "jambe", "coeur"],
    "temps": ["jour", "nuit", "matin", "soir", "annee", "mois", "semaine", "heure"],
    "salutation": ["bonjour", "bonsoir", "salut", "merci", "pardon"],
}


def categorize_entry(translations_fr: list[str]) -> str:
    all_text = " ".join(translations_fr).lower()
    # Enlever les accents pour la comparaison
    import unicodedata
    all_text_norm = unicodedata.normalize('NFD', all_text)
    all_text_norm = ''.join(c for c in all_text_norm if unicodedata.category(c) != 'Mn')
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in all_text_norm:
                return category
    return "general"


def _clean_translation(text: str) -> list[str]:
    """Nettoie et separe un texte de traduction en parties utilisables"""
    results = []
    for part in re.split(r"[;]", text):
        part = part.strip()
        # Enlever numerotation de sens (1. 2. etc)
        part = re.sub(r"^\d+[.)]\s*", "", part)
        # Enlever parentheses englobantes
        part = re.sub(r"^\((.+)\)$", r"\1", part).strip()
        # Enlever espaces multiples
        part = re.sub(r"\s+", " ", part)
        # Ignorer les abbreviations grammaticales (1SG, 3PL, etc)
        if re.match(r"^\d[A-Z]+$", part):
            continue
        # Ignorer trop court ou trop long
        if part and len(part) >= 2 and len(part) < 100:
            results.append(part)
    return results


class BamadabaCollector(BaseCollector):

    BAMADABA_URL = "https://raw.githubusercontent.com/maslinych/bamadaba/master/bamadaba.txt"

    @property
    def source_name(self) -> str:
        return "bamadaba"

    def _fetch_raw(self) -> str:
        print(f"[bamadaba] Telechargement depuis GitHub...")
        req = urllib.request.Request(
            self.BAMADABA_URL,
            headers={"User-Agent": "WOURI-Dictionary-Builder/1.0"}
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read().decode("utf-8")
        print(f"[bamadaba] {len(data)} caracteres telecharges")
        return data

    def _parse_entries(self, raw_data: str) -> list[CollectedEntry]:
        """Parse le format SIL Toolbox de Bamadaba"""
        entries = []
        current_entry = None

        for line in raw_data.split("\n"):
            line = line.rstrip()
            if not line:
                continue

            # Nouvelle entree lexicale (\lx)
            if line.startswith("\\lx "):
                if current_entry and current_entry.translations_fr:
                    current_entry.category = categorize_entry(current_entry.translations_fr)
                    entries.append(current_entry)
                word = line[4:].strip()
                current_entry = CollectedEntry(word=word)

            elif current_entry is None:
                continue

            # Variantes (\va)
            elif line.startswith("\\va "):
                variant = line[4:].strip()
                if variant and variant != current_entry.word:
                    current_entry.variants.append(variant)

            # Part of speech (\ps)
            elif line.startswith("\\ps "):
                ps = line[4:].strip().lower()
                current_entry.part_of_speech = POS_MAP.get(ps, ps)

            # Gloss francais court (\gf) - ex: "riz", "cultiver"
            elif line.startswith("\\gf "):
                gloss = line[4:].strip()
                if gloss:
                    for t in _clean_translation(gloss):
                        if t not in current_entry.translations_fr:
                            current_entry.translations_fr.append(t)

            # Gloss verbose francais (\gvf) - sens detaille
            elif line.startswith("\\gvf "):
                gloss = line[5:].strip()
                if gloss:
                    for t in _clean_translation(gloss):
                        if t not in current_entry.translations_fr:
                            current_entry.translations_fr.append(t)

            # Sens / definition francais (\smf)
            elif line.startswith("\\smf "):
                defn = line[5:].strip()
                if defn:
                    # Nettoyer parentheses
                    cleaned = re.sub(r"^\(|\)$", "", defn).strip()
                    for t in _clean_translation(cleaned):
                        if t not in current_entry.translations_fr:
                            current_entry.translations_fr.append(t)

            # Gloss anglais (\ge) - rare mais utile
            elif line.startswith("\\ge "):
                gloss = line[4:].strip()
                if gloss:
                    for t in _clean_translation(gloss):
                        if t not in current_entry.translations_fr:
                            current_entry.translations_fr.append(t)

            # Exemples bambara (\xv)
            elif line.startswith("\\xv "):
                example = line[4:].strip()
                if example:
                    current_entry.examples.append(example)

        # Derniere entree
        if current_entry and current_entry.translations_fr:
            current_entry.category = categorize_entry(current_entry.translations_fr)
            entries.append(current_entry)

        return entries
