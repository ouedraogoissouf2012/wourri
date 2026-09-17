"""Tests de la resolution de ville — `app/data/cities.py` (issue #516).

Le referentiel melange des cles accentuees (`Séguéla`, `Odienné`, `Soubré`…)
et non accentuees (`Bouake`, `Korhogo`…). Avant #516, `get_city()` et
`search_cities()` ne repliaient pas les diacritiques : un utilisateur ecrivant
correctement « Bouaké » — 2e ville du pays — n'obtenait aucune donnee, et le
routeur demo partait sur un defaut introuvable.

Ces tests verrouillent les deux sens du repli :
    - saisie accentuee  -> cle non accentuee  (Bouaké  -> Bouake)
    - saisie sans accent -> cle accentuee     (Seguela -> Séguéla)

Ils verrouillent aussi la NON-regression des deux strategies historiques
(exacte, puis insensible a la casse), qui restent prioritaires.
"""
from __future__ import annotations

import pytest

from app.data.cities import IVORIAN_CITIES, get_city, search_cities


# ─────────────────────────────────────────────
# Sanity : le referentiel est bien mixte
# ─────────────────────────────────────────────


def test_referentiel_contient_des_cles_accentuees_et_non_accentuees():
    """Le test n'a de sens que si le melange existe reellement."""
    accentuees = [c for c in IVORIAN_CITIES if any(ord(ch) > 127 for ch in c)]
    non_accentuees = [c for c in IVORIAN_CITIES if all(ord(ch) < 128 for ch in c)]
    assert accentuees, "aucune cle accentuee — le test ne couvre plus rien"
    assert non_accentuees, "aucune cle non accentuee — le test ne couvre plus rien"


# ─────────────────────────────────────────────
# get_city — non-regression des strategies existantes
# ─────────────────────────────────────────────


def test_get_city_match_exact_inchange():
    """Strategie 1 (exacte) : prioritaire, comportement historique preserve."""
    assert get_city("Abidjan")["name"] == "Abidjan"
    assert get_city("Bouake")["name"] == "Bouake"


def test_get_city_insensible_a_la_casse_inchange():
    """Strategie 2 (casse) : comportement historique preserve."""
    assert get_city("abidjan")["name"] == "Abidjan"
    assert get_city("BOUAKE")["name"] == "Bouake"


def test_get_city_ville_inconnue_retourne_none():
    assert get_city("Paris") is None
    assert get_city("") is None


# ─────────────────────────────────────────────
# get_city — repli des diacritiques (#516)
# ─────────────────────────────────────────────


def test_get_city_saisie_accentuee_vers_cle_non_accentuee():
    """« Bouaké » est l'orthographe correcte ; la cle du referentiel ne l'est pas.

    C'est le cas qui cassait la surface de demo : le routeur demo declare
    `city: str = "Bouaké"` alors que la cle est `Bouake`.
    """
    resultat = get_city("Bouaké")
    assert resultat is not None, "« Bouaké » doit resoudre vers la cle « Bouake »"
    assert resultat["name"] == "Bouake"
    assert resultat["lat"] == IVORIAN_CITIES["Bouake"]["lat"]


def test_get_city_saisie_sans_accent_vers_cle_accentuee():
    """Sens inverse : l'utilisateur tape sans accent, la cle en porte."""
    resultat = get_city("Seguela")
    assert resultat is not None, "« Seguela » doit resoudre vers « Séguéla »"
    assert resultat["name"] == "Séguéla"


@pytest.mark.parametrize(
    "saisie, attendu",
    [
        ("Odienne", "Odienné"),
        ("Soubre", "Soubré"),
        ("Bouafle", "Bouaflé"),
        ("Ferkessedougou", "Ferkessédougou"),
        ("SEGUELA", "Séguéla"),
        ("séguéla", "Séguéla"),
    ],
)
def test_get_city_repli_diacritiques_parametrique(saisie, attendu):
    """Le repli combine minuscules ET suppression des diacritiques."""
    resultat = get_city(saisie)
    assert resultat is not None, f"« {saisie} » doit resoudre"
    assert resultat["name"] == attendu


def test_get_city_repli_ne_cree_pas_de_faux_positif():
    """Le repli ne doit pas rendre resolvable une ville qui n'existe pas."""
    assert get_city("Bouake-Nord") is None
    assert get_city("Ouagadougou") is None


# ─────────────────────────────────────────────
# search_cities — meme repli (#516)
# ─────────────────────────────────────────────


def test_search_cities_comportement_historique_preserve():
    noms = [c["name"] for c in search_cities("abid")]
    assert "Abidjan" in noms


def test_search_cities_repli_diacritiques():
    """Une recherche sans accent doit trouver les villes accentuees."""
    noms = [c["name"] for c in search_cities("seguela")]
    assert "Séguéla" in noms, "recherche sans accent -> ville accentuee"

    noms = [c["name"] for c in search_cities("bouaké")]
    assert "Bouake" in noms, "recherche accentuee -> ville non accentuee"


def test_search_cities_requete_absente_retourne_liste_vide():
    assert search_cities("zzzz") == []


# ─────────────────────────────────────────────
# Garde-fou : le defaut du routeur demo doit resoudre
# ─────────────────────────────────────────────


def test_defaut_du_routeur_demo_resout_vers_une_ville_reelle():
    """La valeur par defaut du routeur demo doit etre resolvable.

    C'est le defaut exact qui cassait la surface de demo : `DemoAgriRequest`
    declare « Bouaké » (orthographe correcte) alors que la cle du referentiel
    est « Bouake ». Toute requete demo sans ville explicite partait donc sans
    donnee meteo.

    Le test importe la valeur REELLE plutot que de la recopier : si quelqu'un
    change le defaut pour une valeur non resolvable, l'echec est immediat.
    """
    from app.routers.demo import DemoAgriRequest

    defaut = DemoAgriRequest(message="test").city
    assert get_city(defaut) is not None, (
        f"le defaut du routeur demo ({defaut!r}) ne resout vers aucune ville"
    )
