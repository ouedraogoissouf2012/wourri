"""Import du catalogue des concepts NLU (ADR-0047, #600)."""
import json

import pytest

from scripts import import_nlu_concepts as imp


def test_lit_les_concepts_avec_leur_sens_et_le_repere_dioula(tmp_path):
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"concepts": {
        "TEMPS_METEO": {"label_fr": "météo", "keywords": ["tile", "foroko", "ɲɛgɛn"]},
        "ACTION_VENDRE": {"label_fr": "vendre", "keywords": []},
    }}, ensure_ascii=False), encoding="utf-8")

    lignes = {c["id"]: c for c in imp.lire(src)}
    assert lignes["TEMPS_METEO"]["label_fr"] == "météo"
    assert lignes["TEMPS_METEO"]["ref_dyu"] == "tile, foroko, ɲɛgɛn"
    # un concept sans mot dioula reste exploitable : le sens francais suffit au locuteur
    assert lignes["ACTION_VENDRE"]["ref_dyu"] == ""


def test_le_repere_dioula_est_borne(tmp_path):
    """Certains concepts portent plus de 40 mots : on en montre assez pour situer le
    sens, pas la liste entiere."""
    src = tmp_path / "c.json"
    mots = [f"m{i}" for i in range(30)]
    src.write_text(json.dumps({"concepts": {"X": {"label_fr": "x", "keywords": mots}}}),
                   encoding="utf-8")
    assert imp.lire(src)[0]["ref_dyu"].count(",") == imp.MAX_REF - 1


def test_le_libelle_retombe_sur_l_identifiant(tmp_path):
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"concepts": {"SANS_LABEL": {"keywords": []}}}), encoding="utf-8")
    assert imp.lire(src)[0]["label_fr"] == "SANS_LABEL"


def test_le_dsn_vient_de_la_source_unique_du_projet(monkeypatch):
    """Deviner un nom de variable (DATABASE_URL, POSTGRES_DSN) echouait en production :
    aucune des deux n'y existe. `resolve_postgres_url` est la source utilisee par alembic."""
    monkeypatch.setattr(
        "app.db.url_resolver.resolve_postgres_url",
        lambda **_: "postgresql+psycopg://u:p@h:5432/d",
    )
    # le prefixe de pilote SQLAlchemy est retire : psycopg attend une URL simple
    assert imp._dsn() == "postgresql://u:p@h:5432/d"
