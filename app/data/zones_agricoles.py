"""
WOURI - Zones agricoles Côte d'Ivoire
Mapping: région administrative CI → zone agricole → cultures typiques
"""
import logging

logger = logging.getLogger(__name__)

# ============================================================
# ZONES AGRICOLES (4 grandes zones CI)
# ============================================================

# Cultures par zone — associations agro-écologiques documentées (Côte d'Ivoire) :
# Sud forêt = pérennes (cacao/café/hévéa/palmier) ; Centre = anacarde + vivriers
# + coton (frange) ; Nord savane = coton + anacarde + céréales ; Ouest = café-cacao
# + riz. Réf. : profil pays FAO CI, zonage agro-climatique (limite forêt/savane
# Man–Yamoussoukro–Bondoukou).
# ⚠️ #509 : listes ENRICHIES depuis sources documentées — À FAIRE VALIDER
# (CNRA / ANADER) avant merge. Ne pas inventer ; ordonnées par importance.
ZONES = {
    "ZONE_SUD_FORET": {
        "label_fr": "Zone forestière (sud)",
        "label_bam": "Gɛlɛgɛlɛ yɔrɔ (woroba)",
        "cultures": [
            "CULTURE_CACAO",
            "CULTURE_CAFE",
            "CULTURE_HEVEA",
            "CULTURE_PALMIER_HUILE",
            "CULTURE_BANANE",
            "CULTURE_MANIOC",
        ],
    },
    "ZONE_CENTRE": {
        "label_fr": "Zone de transition (centre)",
        "label_bam": "Tɛmɛnen yɔrɔ (diɲɛ)",
        "cultures": [
            "CULTURE_ANACARDE",
            "CULTURE_IGNAME",
            "CULTURE_MAIS",
            "CULTURE_RIZ",
            "CULTURE_ARACHIDE",
            "CULTURE_MANIOC",
            "CULTURE_COTON",
        ],
    },
    "ZONE_NORD_SAVANE": {
        "label_fr": "Zone de savane (nord)",
        "label_bam": "Savane yɔrɔ (north)",
        "cultures": [
            "CULTURE_COTON",
            "CULTURE_ANACARDE",
            "CULTURE_MAIS",
            "CULTURE_MIL",
            "CULTURE_RIZ",
            "CULTURE_ARACHIDE",
            "CULTURE_IGNAME",
            "CULTURE_SESAME",
        ],
    },
    "ZONE_OUEST_MONTAGNES": {
        "label_fr": "Zone montagneuse (ouest)",
        "label_bam": "Kulu yɔrɔ (tilimanjin)",
        "cultures": [
            "CULTURE_CAFE",
            "CULTURE_CACAO",
            "CULTURE_RIZ",
            "CULTURE_MAIS",
            "CULTURE_IGNAME",
            "CULTURE_ARACHIDE",
        ],
    },
}

# ============================================================
# MAPPING RÉGION CI → ZONE AGRICOLE
# Source: régions dans IVORIAN_CITIES
# ============================================================

REGION_TO_ZONE = {
    # Zone Sud-Forêt
    "Lagunes":           "ZONE_SUD_FORET",
    "Bas-Sassandra":     "ZONE_SUD_FORET",
    "Nawa":              "ZONE_SUD_FORET",
    "Grands-Ponts":      "ZONE_SUD_FORET",
    "Agnéby-Tiassa":     "ZONE_SUD_FORET",
    "Lôh-Djiboua":       "ZONE_SUD_FORET",
    "Sud-Comoé":         "ZONE_SUD_FORET",
    "Indénié-Djuablin":  "ZONE_SUD_FORET",
    "Comoé":             "ZONE_SUD_FORET",

    # Zone Centre
    "Vallée du Bandama": "ZONE_CENTRE",
    "Lacs":              "ZONE_CENTRE",
    "Marahoué":          "ZONE_CENTRE",
    "Gôh-Djiboua":       "ZONE_CENTRE",
    "Gôh":               "ZONE_CENTRE",
    "Haut-Sassandra":    "ZONE_CENTRE",
    "N'Zi":              "ZONE_CENTRE",
    "Gontougo":          "ZONE_CENTRE",
    "Iffou":             "ZONE_CENTRE",
    "Moronou":           "ZONE_CENTRE",

    # Zone Nord-Savane
    "Savanes":           "ZONE_NORD_SAVANE",
    "Poro":              "ZONE_NORD_SAVANE",
    "Tchologo":          "ZONE_NORD_SAVANE",
    "Bagoué":            "ZONE_NORD_SAVANE",
    "Hambol":            "ZONE_NORD_SAVANE",
    "Kabadougou":        "ZONE_NORD_SAVANE",
    "Béré":              "ZONE_NORD_SAVANE",
    "Worodougou":        "ZONE_NORD_SAVANE",
    "Bafing":            "ZONE_NORD_SAVANE",

    # Zone Ouest-Montagnes
    "Montagnes":         "ZONE_OUEST_MONTAGNES",
    "Guémon":            "ZONE_OUEST_MONTAGNES",
    "Cavally":           "ZONE_OUEST_MONTAGNES",
    "Tonkpi":            "ZONE_OUEST_MONTAGNES",
}


def get_zone_for_city(city: str) -> str:
    """Retourne la zone agricole pour une ville CI (ZONE_CENTRE par défaut)."""
    from app.data.cities import IVORIAN_CITIES
    city_data = IVORIAN_CITIES.get(city, {})
    region = city_data.get("region", "")
    zone = REGION_TO_ZONE.get(region, "ZONE_CENTRE")
    logger.debug("[ZONE] %s → région '%s' → %s", city, region, zone)
    return zone


def get_cultures_zone(city: str) -> list:
    """Retourne les cultures typiques de la zone pour une ville CI."""
    zone_id = get_zone_for_city(city)
    return ZONES.get(zone_id, {}).get("cultures", [])
