"""
WOURRI - Calendrier Agricole Côte d'Ivoire / Mali
Conseils adaptés au mois actuel, par culture et intent.
"""

from datetime import datetime

# ============================================================
# CALENDRIER PAR CULTURE
# mois = 1 (janvier) ... 12 (décembre)
# ============================================================

CALENDRIER = {
    "CULTURE_IGNAME": {
        "plantation": [1, 2, 3],       # janvier → mars
        "entretien":  [4, 5, 6],       # avril → juin
        "recolte":    [7, 8, 9],       # juillet → septembre
        "repos":      [10, 11, 12],    # octobre → décembre
    },
    "CULTURE_RIZ": {
        "plantation": [5, 6, 7],       # mai → juillet
        "entretien":  [7, 8, 9],       # juillet → septembre
        "recolte":    [10, 11],        # octobre → novembre
        "repos":      [12, 1, 2, 3, 4],
    },
    "CULTURE_MAIS": {
        "plantation": [4, 5, 6],       # avril → juin
        "entretien":  [6, 7, 8],
        "recolte":    [8, 9, 10],
        "repos":      [11, 12, 1, 2, 3],
    },
    "CULTURE_ARACHIDE": {
        "plantation": [5, 6],          # mai → juin
        "entretien":  [6, 7, 8],
        "recolte":    [9, 10],
        "repos":      [11, 12, 1, 2, 3, 4],
    },
    "CULTURE_MANIOC": {
        "plantation": [4, 5, 6],
        "entretien":  [6, 7, 8, 9, 10, 11],
        "recolte":    [12, 1, 2, 3],   # toute l'année possible, pic saison sèche
        "repos":      [],
    },
    "CULTURE_CACAO": {
        "plantation": [5, 6, 7],
        "entretien":  [8, 9, 10],
        "recolte":    [10, 11, 12],
        "repos":      [1, 2, 3, 4],
    },
    "CULTURE_COTON": {
        "plantation": [6, 7],
        "entretien":  [7, 8, 9],
        "recolte":    [11, 12, 1],
        "repos":      [2, 3, 4, 5],
    },
    "CULTURE_TOMATE": {
        "plantation": [10, 11, 12],    # saison sèche (maraîchage)
        "entretien":  [12, 1, 2],
        "recolte":    [1, 2, 3],
        "repos":      [4, 5, 6, 7, 8, 9],
    },
    "CULTURE_PATATE": {
        "plantation": [3, 4, 5],
        "entretien":  [5, 6, 7],
        "recolte":    [7, 8, 9],
        "repos":      [10, 11, 12, 1, 2],
    },
    "CULTURE_SESAME": {
        "plantation": [6, 7],
        "entretien":  [7, 8],
        "recolte":    [9, 10],
        "repos":      [11, 12, 1, 2, 3, 4, 5],
    },
    "CULTURE_HARICOT": {
        "plantation": [5, 6, 9, 10],   # deux saisons
        "entretien":  [6, 7, 10, 11],
        "recolte":    [7, 8, 11, 12],
        "repos":      [1, 2, 3, 4],
    },
    "CULTURE_MIL": {
        "plantation": [6, 7],
        "entretien":  [7, 8, 9],
        "recolte":    [10, 11],
        "repos":      [12, 1, 2, 3, 4, 5],
    },
    "CULTURE_SORGHO": {
        "plantation": [6, 7],
        "entretien":  [7, 8, 9],
        "recolte":    [10, 11],
        "repos":      [12, 1, 2, 3, 4, 5],
    },
}

# ============================================================
# NOMS DES MOIS EN BAMBARA/DIOULA
# ============================================================

MOIS_BAMBARA = {
    1:  "zanwiye kalo",    # janvier
    2:  "feburuye kalo",   # février
    3:  "marisi kalo",     # mars
    4:  "awirili kalo",    # avril
    5:  "mɛ kalo",         # mai
    6:  "zuwɛn kalo",      # juin
    7:  "zuluye kalo",     # juillet
    8:  "uti kalo",        # août
    9:  "sɛtanburu kalo",  # septembre
    10: "ɔkutɔburu kalo",  # octobre
    11: "nowanburu kalo",  # novembre
    12: "desanburu kalo",  # décembre
}

MOIS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
}

# ============================================================
# CONSEILS BAMBARA PAR PHASE
# ============================================================

CONSEILS_BAMBARA = {
    "plantation_debut": "Sisan ye {culture} sɛnɛ waati daminɛ ye. Joona k'a daminɛ!",
    "plantation_milieu": "Sisan ye {culture} sɛnɛ waati ɲuman ye. Sɛnɛ kɛ sisan!",
    "plantation_fin": "Sisan ye {culture} sɛnɛ waati laban na. Joona k'a kɛ, waati bɛ ban!",
    "plantation_passe": "Sɛnɛ waati tɛmɛna. San kura na, i ka labɛn joona.",
    "entretien": "Sisan ye {culture} lakanako waati ye. I ka i ka foro kɔlɔsi.",
    "recolte_debut": "Sisan ye {culture} lajɛ waati ye. I ka kɛ ŋɔgɔn na ka lajɛ!",
    "recolte_milieu": "Sisan ye {culture} lajɛ waati ɲuman ye. Joona k'a lajɛ!",
    "recolte_fin": "Sisan ye {culture} lajɛ waati laban na. Joona k'a lajɛ ka ban.",
    "repos": "Sisan {culture} sɛnɛ waati tɛ. I ka foro lafiɲɛ ka labɛn san kura na.",
}

CONSEILS_FR = {
    "plantation_debut": "Nous sommes au début de la saison de plantation du {culture}. C'est le bon moment pour commencer!",
    "plantation_milieu": "Nous sommes en pleine saison de plantation du {culture}. Plante maintenant!",
    "plantation_fin": "Nous sommes à la fin de la saison de plantation du {culture}. Plante vite, il reste peu de temps!",
    "plantation_passe": "La saison de plantation est passée. Prépare-toi bien pour la prochaine saison.",
    "entretien": "C'est la période d'entretien du {culture}. Surveille bien ton champ.",
    "recolte_debut": "La saison de récolte du {culture} commence. Prépare-toi à récolter!",
    "recolte_milieu": "C'est le bon moment pour récolter le {culture}. Fais vite!",
    "recolte_fin": "La saison de récolte du {culture} se termine. Termine ta récolte rapidement.",
    "repos": "Ce n'est pas la saison du {culture}. Laisse ton champ se reposer et prépare la prochaine saison.",
}

# ============================================================
# NOMS DES CULTURES EN BAMBARA
# ============================================================

NOMS_CULTURES_BAMBARA = {
    "CULTURE_IGNAME":    "ku",
    "CULTURE_RIZ":       "malo",
    "CULTURE_MAIS":      "kaba",
    "CULTURE_ARACHIDE":  "tiga",
    "CULTURE_MANIOC":    "bananku",
    "CULTURE_CACAO":     "kakawo",
    "CULTURE_COTON":     "kɔrɔni",
    "CULTURE_TOMATE":    "tamati",
    "CULTURE_PATATE":    "woso",
    "CULTURE_SESAME":    "bɛnɛ",
    "CULTURE_HARICOT":   "soso",
    "CULTURE_MIL":       "nyɔ",
    "CULTURE_SORGHO":    "keninge",
}

NOMS_CULTURES_FR = {
    "CULTURE_IGNAME":    "igname",
    "CULTURE_RIZ":       "riz",
    "CULTURE_MAIS":      "maïs",
    "CULTURE_ARACHIDE":  "arachide",
    "CULTURE_MANIOC":    "manioc",
    "CULTURE_CACAO":     "cacao",
    "CULTURE_COTON":     "coton",
    "CULTURE_TOMATE":    "tomate",
    "CULTURE_PATATE":    "patate douce",
    "CULTURE_SESAME":    "sésame",
    "CULTURE_HARICOT":   "haricot",
    "CULTURE_MIL":       "mil",
    "CULTURE_SORGHO":    "sorgho",
}


# ============================================================
# FONCTION PRINCIPALE
# ============================================================

def get_conseil_saisonnier(cultures: list[str], intent: str = "") -> dict | None:
    """
    Retourne un conseil adapté au mois actuel pour la culture donnée.

    Args:
        cultures: liste de concepts culture détectés (ex: ["CULTURE_IGNAME"])
        intent: intent NLU (ex: "QUESTION_SAISON_PLANTATION")

    Returns:
        dict avec "bambara" et "fr", ou None si pas de calendrier pour cette culture
    """
    mois = datetime.now().month
    mois_bam = MOIS_BAMBARA.get(mois, "")
    mois_fr = MOIS_FR.get(mois, "")

    for culture in cultures:
        cal = CALENDRIER.get(culture)
        if not cal:
            continue

        nom_bam = NOMS_CULTURES_BAMBARA.get(culture, culture)
        nom_fr = NOMS_CULTURES_FR.get(culture, culture)

        plantation = cal.get("plantation", [])
        entretien = cal.get("entretien", [])
        recolte = cal.get("recolte", [])

        # Déterminer la phase actuelle
        if mois in plantation:
            idx = plantation.index(mois)
            taille = len(plantation)
            if idx == 0:
                phase = "plantation_debut"
            elif idx == taille - 1:
                phase = "plantation_fin"
            else:
                phase = "plantation_milieu"
        elif mois in entretien:
            phase = "entretien"
        elif mois in recolte:
            idx = recolte.index(mois)
            taille = len(recolte)
            if idx == 0:
                phase = "recolte_debut"
            elif idx == taille - 1:
                phase = "recolte_fin"
            else:
                phase = "recolte_milieu"
        else:
            phase = "repos"

        # Si l'intent est plantation mais qu'on est hors saison → message spécial
        if "PLANTATION" in intent and phase not in ("plantation_debut", "plantation_milieu", "plantation_fin"):
            phase = "plantation_passe"

        conseil_bam = CONSEILS_BAMBARA[phase].format(culture=nom_bam)
        conseil_fr = CONSEILS_FR[phase].format(culture=nom_fr)

        print(f"[CALENDRIER] {culture} en {mois_fr} → phase: {phase}")
        print(f"[CALENDRIER BAM] {conseil_bam}")
        print(f"[CALENDRIER FR]  {conseil_fr}")

        return {
            "bambara": conseil_bam,
            "fr": conseil_fr,
            "phase": phase,
            "mois_bam": mois_bam,
            "mois_fr": mois_fr,
            "culture": culture,
        }

    return None


def get_cultures_du_mois(city: str = "Abidjan", month: int = None, max_cultures: int = 3) -> list:
    """
    Retourne les cultures actives (plantation ou entretien) pour une ville et un mois.
    Filtrées selon la zone agricole de la ville (zones_agricoles.py).

    Args:
        city: nom de la ville CI (ex: "Bouaké")
        month: mois 1-12, None = mois actuel
        max_cultures: nombre max de cultures à retourner

    Returns:
        liste de dicts {culture_key, fr, bambara, phase}
    """
    from app.data.zones_agricoles import get_cultures_zone

    if month is None:
        month = datetime.now().month

    cultures_zone = get_cultures_zone(city)
    cultures_actives = []

    for culture_key in cultures_zone:
        cal = CALENDRIER.get(culture_key)
        if not cal:
            continue

        plantation = cal.get("plantation", [])
        entretien = cal.get("entretien", [])

        if month in plantation:
            phase = "plantation"
        elif month in entretien:
            phase = "entretien"
        else:
            continue  # Repos ou récolte — on n'annonce pas ça en salutation

        cultures_actives.append({
            "culture_key": culture_key,
            "fr": NOMS_CULTURES_FR.get(culture_key, culture_key),
            "bambara": NOMS_CULTURES_BAMBARA.get(culture_key, culture_key),
            "phase": phase,
        })

        if len(cultures_actives) >= max_cultures:
            break

    print(f"[ZONE CULTURES] {city} / mois {month} → {[c['fr'] for c in cultures_actives]}")
    return cultures_actives
