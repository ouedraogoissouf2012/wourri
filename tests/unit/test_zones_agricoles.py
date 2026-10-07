"""Tests — `app/data/zones_agricoles.py` : ville → région → zone agricole (#509)."""
from __future__ import annotations

import logging

import pytest

from app.data.cities import IVORIAN_CITIES
from app.data.zones_agricoles import REGION_TO_ZONE, ZONES, get_zone_for_city


def test_toutes_les_regions_du_referentiel_villes_ont_une_zone():
    """Une région absente du mapping retombait en silence sur ZONE_CENTRE :
    Tabou et Sassandra (côte sud-ouest) recevaient les cultures du centre."""
    regions = {data["region"] for data in IVORIAN_CITIES.values()}
    assert sorted(regions - REGION_TO_ZONE.keys()) == []


def test_chaque_zone_mappee_existe():
    assert set(REGION_TO_ZONE.values()) <= ZONES.keys()


@pytest.mark.parametrize(
    ("ville", "zone"),
    [
        # Noms tels que les envoie le serveur WhatsApp (city_resolver.js : ASCII,
        # initiale en majuscule) pour des clés accentuées ou de casse différente.
        ("Seguela", "ZONE_NORD_SAVANE"),
        ("Ferkessedougou", "ZONE_NORD_SAVANE"),
        ("Odienne", "ZONE_NORD_SAVANE"),
        ("Soubre", "ZONE_SUD_FORET"),
        ("San-pedro", "ZONE_SUD_FORET"),
        ("Grand-bassam", "ZONE_SUD_FORET"),
        ("Agnibilekrou", "ZONE_SUD_FORET"),
        ("Danane", "ZONE_OUEST_MONTAGNES"),
        ("Duekoue", "ZONE_OUEST_MONTAGNES"),
        # Régions ajoutées au mapping
        ("Tabou", "ZONE_SUD_FORET"),
        ("Sassandra", "ZONE_SUD_FORET"),
        ("Fresco", "ZONE_SUD_FORET"),
        ("Toumodi", "ZONE_CENTRE"),
        ("Sakassou", "ZONE_CENTRE"),
        # Clés exactes : comportement inchangé
        ("Korhogo", "ZONE_NORD_SAVANE"),
        ("Bouake", "ZONE_CENTRE"),
        ("Abidjan", "ZONE_SUD_FORET"),
    ],
)
def test_zone_resolue_comme_la_meteo(ville, zone):
    assert get_zone_for_city(ville) == zone


@pytest.mark.parametrize("ville", ["Vavoua", "", None])
def test_ville_inconnue_defaut_centre_signale(ville, caplog):
    with caplog.at_level(logging.WARNING, logger="app.data.zones_agricoles"):
        assert get_zone_for_city(ville) == "ZONE_CENTRE"
    assert any("ZONE_CENTRE par défaut" in m for m in caplog.messages)
