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

from app.data.cities import IVORIAN_CITIES, fold_name

# Index precalcule (issue #516). Le tri par longueur ET la compilation des
# regex etaient refaits a CHAQUE appel ; les precalculer une fois ramene le
# cout de 598 us a 96 us par appel (mesure locale, message sans ville, 3000
# iterations) — soit 6,2x plus rapide que l'implementation d'avant #516.
#
# Tri descending par longueur : "Bouake" matche avant "Bouna" si les 2 sont
# presents ; "San Pedro" matche avant "San" (mot court). `fold_name` ne retire
# que les marques combinantes, donc la longueur du nom est inchangee et l'ordre
# du tri reste celui d'avant le repli.
#
# `IVORIAN_CITIES` est une constante de donnees, jamais mutee a l'execution —
# meme hypothese que `app/data/constants.py:17` qui fige deja un `sorted()`
# au chargement du module.
_CITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (city, re.compile(r"\b" + re.escape(fold_name(city)) + r"\b"))
    for city in sorted(IVORIAN_CITIES.keys(), key=len, reverse=True)
]


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
    # Repli des diacritiques des DEUX cotes (issue #516) : le referentiel
    # melange cles accentuees (`Séguéla`) et non accentuees (`Bouake`), donc
    # comparer sur la forme brute ratait « Bouaké » comme « Seguela ».
    # Cote noms de villes, le repli est deja fait dans `_CITY_PATTERNS`.
    msg_folded = fold_name(message)
    for city_name, pattern in _CITY_PATTERNS:
        if pattern.search(msg_folded):
            return city_name
    return None
