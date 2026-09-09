"""Tests — conseil de semis conscient de la date (issue #509 C1).

Le message hors-saison doit dire QUAND est la prochaine fenêtre de semis
(calculée depuis le calendrier), au lieu du vague « prépare-toi pour la
prochaine saison » que SODEXAM a jugé non-sens.

`datetime` est mocké au niveau du module pour figer le mois courant.
"""
from __future__ import annotations

from unittest.mock import patch

from app.data import calendrier_agricole as cal
from app.data.calendrier_agricole import (
    _intervalle_mois_fr,
    _prochaine_fenetre,
    get_conseil_saisonnier,
)


def _fake_datetime(year: int, month: int, day: int = 15):
    import datetime as _d

    class _Fake:
        @staticmethod
        def now():
            return _d.datetime(year, month, day)

    return _Fake


# ── helpers purs ─────────────────────────────────────────────


def test_prochaine_fenetre_mais_depuis_septembre():
    # maïs plantation = [4,5,6] ; en septembre (9) → avril (4), dans 7 mois
    assert _prochaine_fenetre([4, 5, 6], 9) == (4, 7)


def test_prochaine_fenetre_deux_saisons():
    # haricot [5,6,9,10] en août (8) → prochaine = septembre (9), dans 1 mois
    assert _prochaine_fenetre([5, 6, 9, 10], 8) == (9, 1)


def test_intervalle_mois_fr():
    assert _intervalle_mois_fr([4, 5, 6]) == "avril-juin"
    assert _intervalle_mois_fr([5, 6, 9, 10]) == "mai-juin et septembre-octobre"


# ── message hors-saison spécifique ──────────────────────────


def test_conseil_mais_hors_saison_est_specifique():
    """Septembre + « quand semer le maïs » → message DATÉ et précis."""
    with patch.object(cal, "datetime", _fake_datetime(2026, 9)):
        c = get_conseil_saisonnier(["CULTURE_MAIS"], intent="QUESTION_SAISON_PLANTATION")
    assert c is not None
    assert c["phase"] == "plantation_passe"
    fr = c["fr"]
    assert "avril" in fr            # dit QUAND commence la prochaine fenêtre
    assert "mois" in fr             # dit dans combien de temps
    assert "prochaine" in fr.lower()
    # ne doit plus être le message vague d'origine
    assert "Prépare-toi bien pour la prochaine saison" not in fr


def test_conseil_mais_en_saison_reste_encourageant():
    """Avril (en saison) → phase de plantation, pas 'passé'."""
    with patch.object(cal, "datetime", _fake_datetime(2026, 4, 10)):
        c = get_conseil_saisonnier(["CULTURE_MAIS"], intent="QUESTION_SAISON_PLANTATION")
    assert c["phase"].startswith("plantation")
    assert c["phase"] != "plantation_passe"
