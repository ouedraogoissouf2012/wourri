"""Schéma linguistique normalisé, phase 1 : le corpus baoulé en base (ADR-0050, #623).

Migration `0006` : tables `langue`, `reponse`, `enonce`, `historique_linguistique`,
peuplées depuis le lot figé `alembic/data/corpus_ivr_bci_2026-11-13.json`.

Vérification exhaustive, pas par échantillon : les 193 entrées sont reconstruites
depuis la base au format du fichier et comparées en bloc, champ par champ.

Pré-requis : un Postgres migré à `head` (la CI le fait avant pytest). Sans base
joignable, le module est ignoré, comme `test_corpus_schema.py`.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.url_resolver import resolve_postgres_url
from tests.integration._helpers import postgres_reachable

_RACINE = Path(__file__).resolve().parents[2]
_MIGRATION = _RACINE / "alembic" / "versions" / "0006_schema_linguistique_bci.py"
_LOT = _RACINE / "alembic" / "data" / "corpus_ivr_bci_2026-11-13.json"

_URL = resolve_postgres_url(raise_on_missing=False)

pytestmark = pytest.mark.skipif(
    not postgres_reachable(_URL), reason="PostgreSQL non disponible (POSTGRES_URL)"
)


def _migration():
    spec = importlib.util.spec_from_file_location("migration_0006", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lot() -> list[dict]:
    return json.loads(_LOT.read_text(encoding="utf-8"))["entries"]


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine

    eng = create_engine(_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine):
    """Connexion dont tout ce qui est écrit est annulé à la fin du test."""
    with engine.connect() as c:
        tx = c.begin()
        yield c
        tx.rollback()


def _entrees_en_base(conn) -> list[dict]:
    """Les entrées baoulé reconstruites depuis la base, au format du fichier."""
    from sqlalchemy import text

    reponses = conn.execute(text(
        "SELECT id, intent, cultures, metadonnees FROM reponse WHERE langue = 'bci' ORDER BY rang"
    )).all()
    enonces = {}
    for reponse_id, role, langue, texte, media in conn.execute(text(
        "SELECT reponse_id, role, langue, texte, media FROM enonce"
    )):
        enonces[(reponse_id, role, langue)] = (texte, media)
    out = []
    for rid, intent, cultures, meta in reponses:
        out.append({
            "id": rid,
            "filiere": meta["filiere"],
            "question_bci": enonces[(rid, "question", "bci")][0],
            "question_fr": enonces[(rid, "question", "fr")][0],
            "reponse_bci": enonces[(rid, "reponse", "bci")][0],
            "reponse_fr": enonces[(rid, "reponse", "fr")][0],
            "intent": intent,
            "cultures": list(cultures),
            "audio_reponse": enonces[(rid, "reponse", "bci")][1],
            "appariement": meta["appariement"],
        })
    return out


# --------------------------------------------------------------------- le lot figé


def test_le_lot_fige_porte_son_empreinte():
    m = _migration()
    assert len(m.charger_lot(_LOT, m.EMPREINTE_LOT)) == 193


def test_un_lot_altere_est_refuse(tmp_path):
    m = _migration()
    data = json.loads(_LOT.read_text(encoding="utf-8"))
    data["entries"][0]["reponse_bci"] += " "
    altere = tmp_path / "lot.json"
    altere.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="empreinte"):
        m.charger_lot(altere, m.EMPREINTE_LOT)


# --------------------------------------------------------------------- le peuplement


def test_les_193_entrees_sont_en_base_a_l_identique(conn):
    """Identifiants, ordre, textes, audio, intention, cultures, filière, appariement."""
    assert _entrees_en_base(conn) == _lot()


def test_quatre_enonces_par_entree_et_audio_sur_la_seule_reponse_baoule(conn):
    from sqlalchemy import text

    assert conn.execute(text("SELECT count(*) FROM enonce")).scalar() == 4 * 193
    medias = conn.execute(text(
        "SELECT role, langue, count(media) FROM enonce GROUP BY role, langue ORDER BY role, langue"
    )).all()
    assert medias == [("question", "bci", 0), ("question", "fr", 0),
                      ("reponse", "bci", 193), ("reponse", "fr", 0)]


def test_le_lot_applique_est_enregistre_avec_son_empreinte(conn):
    """La base dit quel lot elle porte : c'est ce que la PR2 compare au fichier déployé."""
    from sqlalchemy import text

    m = _migration()
    assert conn.execute(text("SELECT langue, empreinte, auteur FROM lot_linguistique")).all() == [
        ("bci", m.EMPREINTE_LOT, "migration 0006")
    ]


def test_les_langues_sont_des_lignes(conn):
    from sqlalchemy import text

    assert conn.execute(text("SELECT code FROM langue ORDER BY code")).scalars().all() == ["bci", "fr"]


# --------------------------------------------------------------------- les contraintes


@pytest.mark.parametrize("valeurs, message", [
    ("('bci-q0', 'autre', 'bci', 'x', NULL)", "enonce_role_check"),
    ("('bci-q0', 'question', 'bci', 'x', NULL)", "enonce_reponse_id_role_langue_key"),
    ("('bci-q0', 'question', 'xx', 'x', NULL)", "enonce_langue_fkey"),
    ("('bci-inconnu', 'question', 'bci', 'x', NULL)", "enonce_reponse_id_fkey"),
])
def test_le_schema_refuse_un_enonce_invalide(conn, valeurs, message):
    from sqlalchemy import exc, text

    with pytest.raises(exc.IntegrityError, match=message):
        conn.execute(text(f"INSERT INTO enonce (reponse_id, role, langue, texte, media) VALUES {valeurs}"))


# --------------------------------------------------------------------- la traçabilité (ADR-0050 §6)


def test_le_peuplement_est_historise(conn):
    from sqlalchemy import text

    lignes = conn.execute(text(
        "SELECT table_nom, operation, auteur, count(*) FROM historique_linguistique "
        "GROUP BY table_nom, operation, auteur ORDER BY table_nom"
    )).all()
    assert lignes == [("enonce", "INSERT", "migration 0006", 4 * 193),
                      ("langue", "INSERT", "migration 0006", 2),
                      ("reponse", "INSERT", "migration 0006", 193)]


def test_une_modification_garde_l_avant_l_apres_et_l_auteur(conn):
    from sqlalchemy import text

    conn.execute(text("SET LOCAL wourri.auteur = 'test #623'"))
    avant = conn.execute(text(
        "SELECT texte FROM enonce WHERE reponse_id = 'bci-q0' AND role = 'reponse' AND langue = 'fr'"
    )).scalar()
    conn.execute(text(
        "UPDATE enonce SET texte = 'modifie' WHERE reponse_id = 'bci-q0' AND role = 'reponse' AND langue = 'fr'"
    ))
    op, a, b, auteur = conn.execute(text(
        "SELECT operation, avant->>'texte', apres->>'texte', auteur FROM historique_linguistique "
        "WHERE table_nom = 'enonce' ORDER BY id DESC LIMIT 1"
    )).one()
    assert (op, a, b, auteur) == ("UPDATE", avant, "modifie", "test #623")


def test_une_suppression_garde_la_reponse_et_ses_enonces(conn):
    from sqlalchemy import text

    conn.execute(text("DELETE FROM reponse WHERE id = 'bci-q0'"))
    supprimes = conn.execute(text(
        "SELECT table_nom, count(*) FROM historique_linguistique WHERE operation = 'DELETE' "
        "AND coalesce(avant->>'reponse_id', avant->>'id') = 'bci-q0' GROUP BY table_nom ORDER BY table_nom"
    )).all()
    assert supprimes == [("enonce", 4), ("reponse", 1)]


# --------------------------------------------------------------------- le retour arrière


def _alembic(*args: str) -> None:
    env = {**__import__("os").environ, "POSTGRES_URL": _URL}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=_RACINE, env=env, check=True,
                   capture_output=True, timeout=120)


def test_la_migration_se_defait_et_se_refait(engine):
    from sqlalchemy import inspect, text

    try:
        _alembic("downgrade", "0005")
        restantes = set(inspect(engine).get_table_names()) & {
            "langue", "reponse", "enonce", "historique_linguistique", "lot_linguistique"}
        assert restantes == set()
        assert "corpus_entries" in inspect(engine).get_table_names()  # le dioula n'est pas touché
    finally:
        _alembic("upgrade", "head")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM reponse")).scalar() == 193
