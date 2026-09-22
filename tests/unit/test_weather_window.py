"""Fenetre de prevision alimentant le conseil — ADR-0038 / issue #517.

Les templates dioula valides nativement sont PROSPECTIFS : `sanji bɛ na`
(« la pluie vient »), `sanji bɛ se ka na` (« la pluie peut venir »). Avant
#517, ils etaient alimentes par le bloc `current` d'Open-Meteo — une mesure
sur 15 minutes (`interval: 900`). Le moteur annoncait donc ce qui arrive a
partir de ce qui tombe.

ADR-0038 option A : aligner la donnee sur les phrases. Le conseil est desormais
produit depuis la precipitation ATTENDUE de l'heure courante a la fin de
journee locale.

Ces tests couvrent l'agregation de fenetre en isolation (fonction pure), y
compris les cas limites que l'API peut reellement produire : appel en fin de
journee, valeurs `null`, bloc absent.
"""
from __future__ import annotations

import pytest

from app.services.weather import aggregate_forecast_window


# ─────────────────────────────────────────────
# Cas nominal
# ─────────────────────────────────────────────


def _hourly(times, precip, codes, temps):
    return {
        "time": times,
        "precipitation": precip,
        "weather_code": codes,
        "temperature_2m": temps,
    }


def test_somme_de_l_heure_courante_a_la_fin_de_fenetre():
    """La fenetre part de l'heure courante — les heures passees sont exclues."""
    hourly = _hourly(
        ["2026-09-17T06:00", "2026-09-17T07:00", "2026-09-17T08:00", "2026-09-17T09:00"],
        [10.0, 1.0, 2.0, 3.0],
        [61, 51, 51, 3],
        [24.0, 26.0, 28.0, 30.0],
    )
    # Il est 07:00 : les 10 mm de 06:00 sont DEJA TOMBES, ils ne comptent pas.
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T07:30", window_end_hour=23)

    assert result["precipitation_attendue"] == pytest.approx(6.0), "1 + 2 + 3, pas les 10 de 06:00"
    assert result["weather_code_attendu"] == 51
    assert result["temperature_max_attendue"] == pytest.approx(30.0)


def test_heure_courante_incluse_dans_la_fenetre():
    """L'heure en cours compte : la pluie de l'heure courante est encore a venir."""
    hourly = _hourly(
        ["2026-09-17T08:00", "2026-09-17T09:00"],
        [4.0, 1.0],
        [61, 51],
        [28.0, 29.0],
    )
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T08:15", window_end_hour=23)
    assert result["precipitation_attendue"] == pytest.approx(5.0)


def test_code_retenu_est_le_plus_severe_de_la_fenetre():
    """Le code attendu est le max : une averse a 15h doit primer sur un ciel clair a 9h.

    Les codes WMO exploites par la cascade sont ordonnes par severite croissante
    dans les plages utilisees (0-3 clair/couvert, 51-55 bruine, 61-65 pluie,
    80-82 averses, 95-99 orage) — le `max` reproduit donc la priorite de risque
    de `classify_meteo`.
    """
    hourly = _hourly(
        ["2026-09-17T09:00", "2026-09-17T12:00", "2026-09-17T15:00"],
        [0.0, 0.0, 8.0],
        [0, 3, 95],
        [28.0, 31.0, 29.0],
    )
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T09:00", window_end_hour=23)
    assert result["weather_code_attendu"] == 95, "l'orage de 15h doit etre retenu"


def test_fenetre_bornee_par_window_end_hour():
    """Les heures au-dela de la borne ne comptent pas."""
    hourly = _hourly(
        ["2026-09-17T20:00", "2026-09-17T21:00", "2026-09-17T22:00", "2026-09-17T23:00"],
        [1.0, 1.0, 1.0, 1.0],
        [51, 51, 51, 51],
        [26.0, 25.0, 24.0, 24.0],
    )
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T20:00", window_end_hour=21)
    assert result["precipitation_attendue"] == pytest.approx(2.0), "20h et 21h seulement"


# ─────────────────────────────────────────────
# Cas limites reels
# ─────────────────────────────────────────────


def test_appel_en_fin_de_journee_fenetre_vide():
    """A 23h30, il ne reste plus d'heure a venir dans la journee.

    Le moteur ne doit pas retourner un cumul nul qui ferait basculer la
    classification vers « degage » : il retourne None, et l'appelant retombe
    sur son comportement degrade (message generique).
    """
    hourly = _hourly(
        ["2026-09-17T22:00", "2026-09-17T23:00"],
        [5.0, 5.0],
        [61, 61],
        [24.0, 24.0],
    )
    result = aggregate_forecast_window(hourly, now_iso="2026-09-18T00:30", window_end_hour=23)
    assert result is None, "aucune heure a venir -> None, pas un faux 0 mm"


def test_valeurs_null_de_l_api_ignorees():
    """Open-Meteo peut renvoyer `null` sur une variable — coalescence requise."""
    hourly = _hourly(
        ["2026-09-17T08:00", "2026-09-17T09:00", "2026-09-17T10:00"],
        [1.0, None, 2.0],
        [51, None, 61],
        [28.0, None, 30.0],
    )
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T08:00", window_end_hour=23)
    assert result["precipitation_attendue"] == pytest.approx(3.0)
    assert result["weather_code_attendu"] == 61
    assert result["temperature_max_attendue"] == pytest.approx(30.0)


def test_bloc_hourly_absent_ou_vide():
    """Reponse degradee : pas de bloc, ou bloc sans axe temporel."""
    assert aggregate_forecast_window(None, now_iso="2026-09-17T08:00", window_end_hour=23) is None
    assert aggregate_forecast_window({}, now_iso="2026-09-17T08:00", window_end_hour=23) is None
    assert (
        aggregate_forecast_window(_hourly([], [], [], []), now_iso="2026-09-17T08:00", window_end_hour=23)
        is None
    )


def test_tableaux_de_longueurs_incoherentes():
    """Defense : l'axe temporel est plus long que les series de valeurs."""
    hourly = {
        "time": ["2026-09-17T08:00", "2026-09-17T09:00", "2026-09-17T10:00"],
        "precipitation": [1.0, 2.0],
        "weather_code": [51],
        "temperature_2m": [],
    }
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T08:00", window_end_hour=23)
    assert result is not None
    assert result["precipitation_attendue"] == pytest.approx(3.0), "les valeurs presentes sont sommees"


def test_horodatage_courant_introuvable_dans_l_axe():
    """Si l'heure courante precede tout l'axe, la fenetre demarre au debut."""
    hourly = _hourly(
        ["2026-09-17T10:00", "2026-09-17T11:00"],
        [2.0, 3.0],
        [51, 51],
        [28.0, 29.0],
    )
    result = aggregate_forecast_window(hourly, now_iso="2026-09-17T08:00", window_end_hour=23)
    assert result["precipitation_attendue"] == pytest.approx(5.0)
