"""Second catalogue : les concepts NLU (ADR-0047, #600).

Le MEME mecanisme d'assignation sert deux catalogues — les phrases du corpus et les
concepts NLU. Aucun ecran specifique, aucun `if`-langue : ouvrir une langue nouvelle
n'ajoute rien a construire.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_conn
from app.services import assignments
from app.services import productions_repo as repo
from app.services.nlu_catalog import NluConceptCatalog


@pytest.fixture
def concepts(db):
    """Deux concepts NLU dans le catalogue partage (ecrit par le moteur)."""
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS nlu_concepts ("
            " id TEXT PRIMARY KEY, label_fr TEXT NOT NULL,"
            " ref_dyu TEXT NOT NULL DEFAULT '', intent TEXT NOT NULL DEFAULT '',"
            " updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        conn.execute("DELETE FROM nlu_concepts")
        conn.execute(
            "INSERT INTO nlu_concepts (id, label_fr, ref_dyu) VALUES"
            " ('TEMPS_METEO', 'météo', 'tile, foroko'),"
            " ('ACTION_VENDRE', 'vendre', 'faran, fere')"
        )
        conn.commit()
    yield


def test_le_catalogue_lit_les_concepts(concepts):
    cat = NluConceptCatalog()
    tous = {c.id: c for c in cat.list_concepts()}
    assert set(tous) == {"TEMPS_METEO", "ACTION_VENDRE"}
    # le pivot envoye au locuteur est le SENS en francais
    assert tous["TEMPS_METEO"].text_fr == "météo"
    # le repere dioula est porte, pour etre AFFICHE et jamais recopie
    assert tous["TEMPS_METEO"].ref_dyu == "tile, foroko"
    assert cat.get_concept("INEXISTANT") is None


def test_assigner_un_concept_demande_un_mot_cle(concepts, seeded):
    out = assignments.assign_batch(
        ["TEMPS_METEO"], target_language="bci", assigned_by="admin",
        catalog=NluConceptCatalog(), kind="mot_cle",
    )
    assert out["assigned"] == 1
    ouvertes = assignments.list_open(language="bci")
    assert len(ouvertes) == 1
    a = ouvertes[0]
    assert a["kind"] == "mot_cle"
    assert a["source_fr"] == "météo"
    # le repere dioula est resolu a la lecture, pas stocke
    assert a["ref_dyu"] == "tile, foroko"


def test_une_assignation_de_corpus_reste_un_contenu(concepts, seeded):
    """Non-regression : le comportement d'avant est inchange par defaut."""
    assignments.assign_batch(
        ["TEMPS_METEO"], target_language="bci", assigned_by="admin",
        catalog=NluConceptCatalog(),
    )
    a = assignments.list_open(language="bci")[0]
    assert a["kind"] == "contenu"
    assert "ref_dyu" not in a  # pas de lecture du catalogue pour un contenu


def test_la_route_refuse_un_catalogue_inconnu(concepts, seeded):
    from app.routers import assignments as router_mod

    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[router_mod.current_user] = lambda: {
        "u": "admin", "lang": "bci", "roles": ["admin"],
    }
    cli = TestClient(app)

    r = cli.get("/assignments/missing?language=bci&catalogue=nlu")
    assert r.status_code == 200 and r.json()["kind"] == "mot_cle"

    r = cli.get("/assignments/missing?language=bci&catalogue=inconnu")
    assert r.status_code == 400 and r.json()["detail"] == "unknown_catalogue"


def test_un_mot_produit_arrive_dans_son_concept(concepts, seeded):
    """Sans le `kind`, le mot arriverait comme contenu et ne rejoindrait jamais
    son concept — c'est tout l'objet de la chaine."""
    from app.services.ingest import ingest_response

    out = ingest_response(
        concept_id="TEMPS_METEO", text_local="<mot du locuteur>", text_fr="météo",
        audio_url="media/x.webm", language="bci", actor="loc", kind="mot_cle",
    )
    assert out["ok"]
    fiche = next(r for r in repo.list_by(language="bci") if r["text_fr"] == "météo")
    assert fiche["kind"] == "mot_cle"
    assert fiche["concept_id"] == "TEMPS_METEO"
    assert fiche["status"] == "bronze"
