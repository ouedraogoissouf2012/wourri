"""
WOURI — CityDetector : extraction de `chat_service.py` (refactor P2-09 PR 2/5).

Module PUR (pas d'etat persistant) qui detecte une ville ivoirienne dans
un message utilisateur via word boundary regex.

Pattern aligne avec PR 1/5 (MeteoInjector) : fonctions module-level pour
les helpers sans etat. La constante `IVORIAN_CITIES` reste dans
`app/data/cities.py` (donnees, pas logique).

Refs :
  - Issue parent : #204 Sprint L item P2-09
  - PR precedente : PR 1/5 #262 (MeteoInjector)
"""
from __future__ import annotations

import re
from typing import Optional

from app.data.cities import IVORIAN_CITIES


def detect_city(message: str) -> Optional[str]:
    """Detecte une ville ivoirienne dans le message.

    Cherche les noms de villes par ordre decroissant de longueur (priorite
    aux noms longs) avec word boundary regex pour eviter les faux positifs
    (ex: "manioc" ne doit pas matcher "Man" — pattern aligne avec city_resolver
    cote whatsapp-server PR #199).

    Args:
        message: Texte utilisateur a analyser (toute langue).

    Returns:
        Nom canonique de la ville detectee (clef IVORIAN_CITIES), ou None
        si aucune ville reconnue.
    """
    msg_lower = message.lower()
    # Tri descending par longueur : "Bouake" matche avant "Bouna" si les 2 sont
    # presents ; "San Pedro" matche avant "San" (mot court).
    for city_name in sorted(IVORIAN_CITIES.keys(), key=len, reverse=True):
        pattern = r"\b" + re.escape(city_name.lower()) + r"\b"
        if re.search(pattern, msg_lower):
            return city_name
    return None
