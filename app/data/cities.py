"""
WOURI - Villes de Côte d'Ivoire (60 villes)
"""

IVORIAN_CITIES = {
    # Grandes villes
    "Abidjan": {"lat": 5.3600, "lon": -4.0083, "region": "Lagunes"},
    "Bouake": {"lat": 7.6833, "lon": -5.0331, "region": "Vallée du Bandama"},
    "Daloa": {"lat": 6.8774, "lon": -6.4502, "region": "Haut-Sassandra"},
    "Yamoussoukro": {"lat": 6.8276, "lon": -5.2893, "region": "Lacs"},
    "Korhogo": {"lat": 9.4500, "lon": -5.6333, "region": "Savanes"},
    "San-Pedro": {"lat": 4.7485, "lon": -6.6363, "region": "Bas-Sassandra"},
    "Man": {"lat": 7.4125, "lon": -7.5536, "region": "Montagnes"},
    "Gagnoa": {"lat": 6.1319, "lon": -5.9506, "region": "Gôh-Djiboua"},
    "Abengourou": {"lat": 6.7297, "lon": -3.4964, "region": "Comoé"},
    "Divo": {"lat": 5.8372, "lon": -5.3572, "region": "Lôh-Djiboua"},

    # Villes moyennes
    "Anyama": {"lat": 5.4833, "lon": -4.0500, "region": "Lagunes"},
    "Bingerville": {"lat": 5.3500, "lon": -3.8833, "region": "Lagunes"},
    "Grand-Bassam": {"lat": 5.2000, "lon": -3.7333, "region": "Lagunes"},
    "Agboville": {"lat": 5.9333, "lon": -4.2167, "region": "Agnéby-Tiassa"},
    "Dabou": {"lat": 5.3167, "lon": -4.3833, "region": "Grands-Ponts"},
    "Dimbokro": {"lat": 6.6500, "lon": -4.7000, "region": "N'Zi"},
    "Bondoukou": {"lat": 8.0333, "lon": -2.8000, "region": "Gontougo"},
    "Séguéla": {"lat": 7.9667, "lon": -6.6667, "region": "Worodougou"},
    "Odienné": {"lat": 9.5000, "lon": -7.5667, "region": "Kabadougou"},
    "Ferkessédougou": {"lat": 9.6000, "lon": -5.2000, "region": "Tchologo"},

    # Autres villes importantes
    "Soubré": {"lat": 5.7833, "lon": -6.6000, "region": "Nawa"},
    "Bouaflé": {"lat": 6.9833, "lon": -5.7500, "region": "Marahoué"},
    "Issia": {"lat": 6.4833, "lon": -6.5833, "region": "Haut-Sassandra"},
    "Oumé": {"lat": 6.3833, "lon": -5.4167, "region": "Gôh"},
    "Lakota": {"lat": 5.8500, "lon": -5.6833, "region": "Lôh-Djiboua"},
    "Sinfra": {"lat": 6.6167, "lon": -5.9167, "region": "Marahoué"},
    "Zuénoula": {"lat": 7.4333, "lon": -6.0500, "region": "Marahoué"},
    "Touba": {"lat": 8.2833, "lon": -7.6833, "region": "Bafing"},
    "Mankono": {"lat": 8.0500, "lon": -6.1833, "region": "Béré"},
    "Katiola": {"lat": 8.1333, "lon": -5.1000, "region": "Hambol"},

    # Villes du Nord
    "Boundiali": {"lat": 9.5167, "lon": -6.4833, "region": "Bagoué"},
    "Tengrela": {"lat": 10.4833, "lon": -6.4000, "region": "Bagoué"},
    "Ouangolodougou": {"lat": 9.9667, "lon": -5.1500, "region": "Tchologo"},
    "Kong": {"lat": 9.1500, "lon": -4.6167, "region": "Tchologo"},
    "Dabakala": {"lat": 8.3667, "lon": -4.4333, "region": "Hambol"},
    "Niakara": {"lat": 8.6667, "lon": -5.2833, "region": "Hambol"},
    "Tafire": {"lat": 9.1500, "lon": -5.4833, "region": "Poro"},
    "Niakaramandougou": {"lat": 8.6667, "lon": -5.3000, "region": "Hambol"},

    # Villes de l'Est
    "Tanda": {"lat": 7.8000, "lon": -3.1667, "region": "Gontougo"},
    "Agnibilékrou": {"lat": 7.1333, "lon": -3.2000, "region": "Indénié-Djuablin"},
    "Bettié": {"lat": 6.1000, "lon": -3.4667, "region": "Indénié-Djuablin"},
    "Aboisso": {"lat": 5.4667, "lon": -3.2000, "region": "Sud-Comoé"},
    "Adiaké": {"lat": 5.2833, "lon": -3.3000, "region": "Sud-Comoé"},
    "Bonoua": {"lat": 5.2667, "lon": -3.5833, "region": "Sud-Comoé"},

    # Villes de l'Ouest
    "Danané": {"lat": 7.2667, "lon": -8.1500, "region": "Tonkpi"},
    "Duékoué": {"lat": 6.7333, "lon": -7.3500, "region": "Guémon"},
    "Guiglo": {"lat": 6.5333, "lon": -7.4833, "region": "Cavally"},
    "Toulépleu": {"lat": 6.5667, "lon": -8.4167, "region": "Cavally"},
    "Tabou": {"lat": 4.4167, "lon": -7.3500, "region": "San-Pédro"},
    "Sassandra": {"lat": 4.9500, "lon": -6.0833, "region": "Gbôklé"},

    # Villes du Centre
    "Toumodi": {"lat": 6.5500, "lon": -5.0167, "region": "Bélier"},
    "Tiébissou": {"lat": 7.1500, "lon": -5.2333, "region": "Bélier"},
    "Bocanda": {"lat": 7.0667, "lon": -4.5000, "region": "N'Zi"},
    "M'Bahiakro": {"lat": 7.4500, "lon": -4.3333, "region": "N'Zi"},
    "Prikro": {"lat": 7.6000, "lon": -3.8333, "region": "Iffou"},
    "Sakassou": {"lat": 7.4500, "lon": -5.2833, "region": "Gbêkê"},

    # Villes côtières
    "Jacqueville": {"lat": 5.2000, "lon": -4.4167, "region": "Grands-Ponts"},
    "Grand-Lahou": {"lat": 5.1333, "lon": -5.0000, "region": "Grands-Ponts"},
    "Fresco": {"lat": 5.0667, "lon": -5.5667, "region": "Gbôklé"},
}


def get_city(name: str) -> dict | None:
    """Retourne les infos d'une ville"""
    # Recherche exacte
    if name in IVORIAN_CITIES:
        return {"name": name, **IVORIAN_CITIES[name]}

    # Recherche insensible à la casse
    name_lower = name.lower()
    for city, data in IVORIAN_CITIES.items():
        if city.lower() == name_lower:
            return {"name": city, **data}

    return None


def search_cities(query: str) -> list[dict]:
    """Recherche des villes par nom partiel"""
    query_lower = query.lower()
    results = []
    for city, data in IVORIAN_CITIES.items():
        if query_lower in city.lower():
            results.append({"name": city, **data})
    return results


def get_all_cities() -> list[dict]:
    """Retourne toutes les villes"""
    return [{"name": city, **data} for city, data in IVORIAN_CITIES.items()]
