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
    # #509 : régions des villes de IVORIAN_CITIES absentes de ce mapping — elles
    # tombaient sur le défaut ZONE_CENTRE. Zone reprise du district déjà mappé
    # (Bas-Sassandra, où se trouve la ville de San-Pedro).
    "San-Pédro":         "ZONE_SUD_FORET",   # Tabou
    "Gbôklé":            "ZONE_SUD_FORET",   # Sassandra, Fresco

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
    # #509 : idem, zone de la ville voisine déjà mappée (Yamoussoukro, Bouaké).
    "Bélier":            "ZONE_CENTRE",      # Toumodi, Tiébissou
    "Gbêkê":             "ZONE_CENTRE",      # Sakassou

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
    """Retourne la zone agricole pour une ville CI (ZONE_CENTRE par défaut).

    La ville est résolue comme pour la météo (`get_city` : casse et diacritiques
    ignorés, #516). Le serveur WhatsApp envoie des noms ASCII (« Seguela »,
    « Ferkessedougou ») : une recherche par clé exacte les envoyait tous au
    défaut ZONE_CENTRE (#509). Ce défaut reste en place pour une ville ou une
    région inconnue, mais il est désormais signalé.
    """
    from app.data.cities import get_city
    city_data = get_city(city) if city else None
    region = (city_data or {}).get("region", "")
    zone = REGION_TO_ZONE.get(region)
    if zone is None:
        logger.warning(
            "[ZONE] %s (région '%s') sans zone agricole connue → ZONE_CENTRE par défaut",
            city, region,
        )
        return "ZONE_CENTRE"
    logger.debug("[ZONE] %s → région '%s' → %s", city, region, zone)
    return zone


def get_cultures_zone(city: str) -> list:
    """Retourne les cultures typiques de la zone pour une ville CI."""
    zone_id = get_zone_for_city(city)
    return ZONES.get(zone_id, {}).get("cultures", [])
