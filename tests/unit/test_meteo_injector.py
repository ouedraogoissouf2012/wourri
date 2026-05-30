"""
Tests pour `app/services/chat/meteo_injector.py` (refactor P2-09 PR 1/5).

Couvre :
    - `build_meteo_bambara()` : 7 branches conditionnelles meteo
      (no data, orage, grosse pluie, pluie legere, ciel couvert, chaleur, normal)
      + branche cultures de saison (3 cas : 1 culture / 2 / 3+)
    - `inject_meteo()` : court-circuit no-tag, replace tag bam seul,
      replace tag fr seul, replace les 2, exception calendrier_agricole

Module PUR (fonctions module-level, pas d'etat). Tests simples sans mocking
lourd sauf pour `get_cultures_du_mois` (dependance externe).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.chat.meteo_injector import build_meteo_bambara, inject_meteo


# ─────────────────────────────────────────────
# build_meteo_bambara — 7 branches meteo
# ─────────────────────────────────────────────


def test_build_meteo_weather_data_none_message_generique():
    """weather_data=None → message generique invariant."""
    bam, fr = build_meteo_bambara(None, "Abidjan")
    assert "foro" in bam  # mot bambara generique present
    assert "Surveillez" in fr
    assert "Abidjan" not in bam  # message generique, pas de ville


def test_build_meteo_orage_code_95_plus():
    """weather_code >= 95 → message orage urgent."""
    weather = {"weather_code": 95, "temperature": 25, "precipitation": 10, "city": "Abidjan"}
    bam, fr = build_meteo_bambara(weather, "Abidjan")
    assert "sanfɛla" in bam  # orage en bambara
    assert "orage" in fr.lower()
    assert "Abidjan" in bam and "Abidjan" in fr


def test_build_meteo_grosse_pluie_code_61_plus_ou_precip():
    """weather_code >= 61 OU precipitation > 5 → message pluie + abri."""
    weather = {"weather_code": 65, "temperature": 26, "precipitation": 10, "city": "Bouake"}
    bam, fr = build_meteo_bambara(weather, "Bouake")
    assert "sanji" in bam  # pluie en bambara
    assert "pluie" in fr.lower()
    assert "Bouake" in bam


def test_build_meteo_precipitation_seule_declenche_pluie():
    """precipitation > 5 declenche meme branche que code >= 61."""
    weather = {"weather_code": 0, "temperature": 26, "precipitation": 10, "city": "Daloa"}
    bam, fr = build_meteo_bambara(weather, "Daloa")
    assert "sanji" in bam
    assert "pluie" in fr.lower()


def test_build_meteo_pluie_legere_code_51():
    """weather_code >= 51 (mais < 61) ou 0 < precip <= 5 → pluie legere."""
    weather = {"weather_code": 51, "temperature": 27, "precipitation": 2, "city": "Korhogo"}
    bam, fr = build_meteo_bambara(weather, "Korhogo")
    assert "fɛrɛn" in bam  # legere en bambara
    assert "Légère" in fr or "égère" in fr  # accent gere


def test_build_meteo_ciel_couvert_code_3():
    """weather_code == 3 → ciel couvert."""
    weather = {"weather_code": 3, "temperature": 28, "precipitation": 0, "city": "Yamoussoukro"}
    bam, fr = build_meteo_bambara(weather, "Yamoussoukro")
    assert "sankolo" in bam
    assert "couvert" in fr.lower()


def test_build_meteo_chaleur_intense_temp_sup_33():
    """temperature > 33 → chaleur intense + irrigation conseillee."""
    weather = {"weather_code": 0, "temperature": 36, "precipitation": 0, "city": "Korhogo"}
    bam, fr = build_meteo_bambara(weather, "Korhogo")
    assert "tile ka jugu" in bam  # chaleur en bambara
    assert "haleur" in fr.lower() or "irrig" in fr.lower()


def test_build_meteo_temps_normal_fallback_else():
    """Aucune condition speciale → branche else (ciel degage)."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    bam, fr = build_meteo_bambara(weather, "Abidjan")
    assert "tile bɛ ɲɛ" in bam
    assert "dégagé" in fr or "egag" in fr


# ─────────────────────────────────────────────
# build_meteo_bambara — branche cultures (1, 2, 3+)
# ─────────────────────────────────────────────


def test_build_meteo_avec_1_culture_de_saison():
    """1 culture → format simple 'malo' / 'riz'."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    cultures = [{"bambara": "malo", "fr": "riz"}]
    bam, fr = build_meteo_bambara(weather, "Abidjan", cultures)
    assert "malo" in bam
    assert "riz" in fr
    # Pas de connecteur "ani" / "et" pour 1 seule culture
    assert " ani " not in bam.split("Sisan")[-1].split("malo")[0]


def test_build_meteo_avec_2_cultures_de_saison():
    """2 cultures → format 'malo ani kaba' / 'riz et maïs'."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    cultures = [{"bambara": "malo", "fr": "riz"}, {"bambara": "kaba", "fr": "maïs"}]
    bam, fr = build_meteo_bambara(weather, "Abidjan", cultures)
    assert "malo ani kaba" in bam
    assert "riz et maïs" in fr


def test_build_meteo_avec_3_plus_cultures_de_saison():
    """3+ cultures → format virgules + dernier 'ani' / 'et'."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    cultures = [
        {"bambara": "malo", "fr": "riz"},
        {"bambara": "kaba", "fr": "maïs"},
        {"bambara": "tiga", "fr": "arachide"},
    ]
    bam, fr = build_meteo_bambara(weather, "Abidjan", cultures)
    assert "malo, kaba ani tiga" in bam
    assert "riz, maïs et arachide" in fr


# ─────────────────────────────────────────────
# inject_meteo — court-circuit + remplacement
# ─────────────────────────────────────────────


def test_inject_meteo_court_circuit_aucun_tag():
    """Aucun tag → retourne les chaines inchangees sans appel calendrier."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0}
    bam_input = "Reponse bambara simple sans tag"
    fr_input = "Reponse francaise simple sans tag"

    # Le court-circuit doit eviter l'import de calendrier_agricole.
    # On verifie qu'aucune exception n'est levee meme si on patch
    # get_cultures_du_mois pour qu'elle leve (preuve qu'elle n'est pas appelee).
    with patch("app.data.calendrier_agricole.get_cultures_du_mois") as mock_cultures:
        mock_cultures.side_effect = RuntimeError("Ne devrait pas etre appele")
        bam, fr = inject_meteo(bam_input, fr_input, weather, "Abidjan")

    assert bam == bam_input
    assert fr == fr_input
    mock_cultures.assert_not_called()


def test_inject_meteo_tag_bambara_seul():
    """Tag bambara present → remplacement avec meteo bambara reelle."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    bam_input = "Reponse: {{METEO_CONTEXTUEL}}"
    fr_input = "Reponse francaise sans tag"

    with patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=None):
        bam, fr = inject_meteo(bam_input, fr_input, weather, "Abidjan")

    assert "{{METEO_CONTEXTUEL}}" not in bam
    assert "tile" in bam or "ɲɛ" in bam  # message meteo bambara present
    assert fr == fr_input  # FR inchange car pas de tag


def test_inject_meteo_tag_fr_seul():
    """Tag FR present → remplacement avec meteo FR reelle."""
    weather = {"weather_code": 95, "temperature": 25, "precipitation": 10, "city": "Bouake"}
    bam_input = "Reponse bambara sans tag"
    fr_input = "Reponse: {{METEO_FR}}"

    with patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=None):
        bam, fr = inject_meteo(bam_input, fr_input, weather, "Bouake")

    assert bam == bam_input  # bam inchange
    assert "{{METEO_FR}}" not in fr
    assert "orage" in fr.lower() or "Bouake" in fr


def test_inject_meteo_les_2_tags_presents():
    """Les 2 tags presents → remplacement dans les 2 versions."""
    weather = {"weather_code": 65, "temperature": 26, "precipitation": 8, "city": "Daloa"}
    bam_input = "Bambara: {{METEO_CONTEXTUEL}}"
    fr_input = "Francais: {{METEO_FR}}"

    with patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=None):
        bam, fr = inject_meteo(bam_input, fr_input, weather, "Daloa")

    assert "{{METEO_CONTEXTUEL}}" not in bam
    assert "{{METEO_FR}}" not in fr
    assert "sanji" in bam  # pluie en bam
    assert "pluie" in fr.lower()


def test_inject_meteo_exception_calendrier_remplace_par_vide():
    """Si `get_cultures_du_mois` leve une exception → meteo_bam/fr vides
    (= tags remplaces par vide, pas de crash)."""
    weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Abidjan"}
    bam_input = "Reponse: {{METEO_CONTEXTUEL}} ici"
    fr_input = "Reponse: {{METEO_FR}} ici"

    with patch(
        "app.data.calendrier_agricole.get_cultures_du_mois",
        side_effect=ValueError("Donnees indisponibles"),
    ):
        bam, fr = inject_meteo(bam_input, fr_input, weather, "Abidjan")

    # Tags remplaces par vide, contenu autour preserve
    assert "{{METEO_CONTEXTUEL}}" not in bam
    assert "{{METEO_FR}}" not in fr
    assert "Reponse:" in bam  # contenu autour preserve
    assert "ici" in bam
    assert "Reponse:" in fr
    assert "ici" in fr
