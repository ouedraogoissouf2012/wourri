"""Synchronisation du corpus baoulé : le fichier relu en PR -> la base servie (ADR-0050 amendé, #623).

Le fichier `dictionnaires/corpus_ivr_bci.json` reste la source ; la base en est la
copie servie, que le moteur met lui-même à jour quand l'empreinte du fichier diffère
du dernier lot appliqué. Les quatre propriétés exigées :
  1. après synchronisation, la base est égale au fichier, entrée par entrée ;
  2. une seconde synchronisation ne change rien ;
  3. une entrée retirée du fichier est supprimée de la base ET reste dans l'historique ;
  4. deux synchronisations concurrentes : une seule applique, rien n'est dupliqué.

La synchronisation COMMITE (le cas 4 l'exige) : ces tests tournent donc sur une base
créée pour eux, migrée à `head`, puis détruite — ils ne touchent pas la base partagée.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.db.url_resolver import resolve_postgres_url
from tests.integration._helpers import exiger_postgres

_RACINE = Path(__file__).resolve().parents[2]
_FICHIER = _RACINE / "dictionnaires" / "corpus_ivr_bci.json"
_URL = resolve_postgres_url(raise_on_missing=False)

pytestmark = pytest.mark.base_de_donnees  # #638 : ce module atteint PostgreSQL
_base_joignable = exiger_postgres(_URL, "PostgreSQL non disponible (POSTGRES_URL)")


def _fichier() -> dict:
    return json.loads(_FICHIER.read_text(encoding="utf-8"))


def _servies(data: dict) -> list[dict]:
    return [e for e in data["entries"] if e.get("question_bci") and e.get("reponse_bci")]


@pytest.fixture(scope="module")
def base_isolee():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    nom = f"wourri_synchro_bci_{os.getpid()}_test"  # jetable : la garde #638 refuse tout autre nom
    admin = create_engine(_URL, future=True, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{nom}"'))
    url = make_url(_URL).set(database=nom).render_as_string(hide_password=False)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=_RACINE,
                   env={**os.environ, "POSTGRES_URL": url}, check=True, capture_output=True, timeout=180)
    eng = create_engine(url, future=True)
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
    admin.dispose()


def _synchroniser(eng, data: dict, auteur: str = "test #623"):
    from app.services import corpus_bci_base as base

    with eng.begin() as c:
        return base.synchroniser(c, _servies(data), base.empreinte(data), auteur=auteur)


def _en_base(eng) -> list[dict]:
    from app.services import corpus_bci_base as base

    with eng.connect() as c:
        return list(base.charger(c))


def _historique(eng, auteur: str, depuis: int = 0) -> list[tuple]:
    """Lignes d'historique de cet auteur, écrites après la ligne `depuis` (voir `_dernier`)."""
    from sqlalchemy import text

    with eng.connect() as c:
        return c.execute(text(
            "SELECT table_nom, operation, count(*) FROM historique_linguistique WHERE auteur = :a "
            "AND id > :d GROUP BY table_nom, operation ORDER BY table_nom, operation"
        ), {"a": auteur, "d": depuis}).all()


def _dernier(eng) -> int:
    from sqlalchemy import text

    with eng.connect() as c:
        return c.execute(text("SELECT coalesce(max(id), 0) FROM historique_linguistique")).scalar()


@pytest.fixture
def eng(base_isolee):
    """La base remise sur le fichier courant avant chaque test."""
    _synchroniser(base_isolee, _fichier(), auteur="remise en état")
    return base_isolee


def _modifie() -> dict:
    """Le fichier avec bci-q0 retiré et la traduction française d'une réponse corrigée."""
    data = copy.deepcopy(_fichier())
    data["entries"] = [e for e in data["entries"] if e["id"] != "bci-q0"]
    data["entries"][0]["reponse_fr"] += " (corrigé)"
    return data


# --------------------------------------------------------------------- 1. égalité


def test_la_base_synchronisee_est_egale_au_fichier_relu(eng):
    """Le contrôle de divergence : la base, relue au format du fichier, EST le fichier."""
    from app.services import corpus_bci_base as base

    assert _en_base(eng) == _servies(_fichier())
    with eng.connect() as c:
        assert base.lot_courant(c) == base.empreinte(_fichier())


def test_le_moteur_et_la_migration_calculent_la_meme_empreinte():
    """La migration 0006 a sa propre copie de la fonction (une migration est figée) : elles
    doivent s'accorder, sinon le moteur resynchroniserait un lot déjà appliqué."""
    from app.services import corpus_bci_base as base

    chemin = _RACINE / "alembic" / "versions" / "0006_schema_linguistique_bci.py"
    spec = importlib.util.spec_from_file_location("migration_0006", chemin)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert base.empreinte(_fichier()) == migration.empreinte(_fichier())


# --------------------------------------------------------------------- 2. idempotence


def test_une_seconde_synchronisation_ne_change_rien(eng):
    bilan = _synchroniser(eng, _fichier(), auteur="seconde")
    assert bilan.applique is False
    assert _historique(eng, "seconde") == []


# --------------------------------------------------------------------- 3. suppression tracée


def test_une_entree_retiree_est_supprimee_et_reste_dans_l_historique(eng):
    from sqlalchemy import text

    data = _modifie()
    bilan = _synchroniser(eng, data, auteur="retrait")
    assert (bilan.applique, bilan.supprimees, bilan.modifiees) == (True, 1, 1)
    assert _en_base(eng) == _servies(data)
    with eng.connect() as c:
        garde = c.execute(text(
            "SELECT table_nom, count(*) FROM historique_linguistique WHERE auteur = 'retrait' "
            "AND operation = 'DELETE' AND coalesce(avant->>'reponse_id', avant->>'id') = 'bci-q0' "
            "GROUP BY table_nom ORDER BY table_nom"
        )).all()
        corrige = c.execute(text(
            "SELECT avant->>'texte', apres->>'texte' FROM historique_linguistique "
            "WHERE auteur = 'retrait' AND table_nom = 'enonce' AND operation = 'UPDATE'"
        )).all()
    assert garde == [("enonce", 4), ("reponse", 1)]
    premiere = data["entries"][0]
    assert corrige == [(premiere["reponse_fr"].removesuffix(" (corrigé)"), premiere["reponse_fr"])]


# --------------------------------------------------------------------- 4. concurrence


def _attendre_deux_en_attente(conn) -> None:
    """Jusqu'à ce que les deux synchronisations soient bloquées (verrou de table ou consultatif)."""
    import time

    from sqlalchemy import text

    for _ in range(200):
        if conn.execute(text(
            "SELECT count(*) FROM pg_locks WHERE NOT granted "
            "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
        )).scalar() >= 2:
            return
        time.sleep(0.05)
    raise AssertionError("les deux synchronisations ne se sont jamais trouvées en attente")


def _course_forcee(eng, synchroniser) -> list[Exception]:
    """Lance `synchroniser` deux fois en parallèle, la première écriture bloquée jusqu'à ce que
    les deux attendent ; renvoie les erreurs levées (une course perdue doit se voir)."""
    from sqlalchemy import text

    erreurs = []

    def lancer():
        try:
            synchroniser()
        except Exception as exc:
            erreurs.append(exc)

    with eng.connect() as portier:
        tx = portier.begin()
        portier.execute(text("LOCK TABLE reponse IN SHARE MODE"))
        fils = [threading.Thread(target=lancer) for _ in range(2)]
        for f in fils:
            f.start()
        with eng.connect() as observateur:
            _attendre_deux_en_attente(observateur)
        tx.commit()
    for f in fils:
        f.join(timeout=60)
    return erreurs


def test_deux_synchronisations_concurrentes_une_seule_applique(eng):
    """La course est FORCÉE, pas espérée : une troisième connexion bloque la première écriture
    (SHARE laisse passer les lectures) jusqu'à ce que les deux synchronisations attendent.
    Sans le verrou consultatif, toutes deux ont lu l'ancien lot et toutes deux appliquent."""
    data = _modifie()
    bilans = []
    assert _course_forcee(eng, lambda: bilans.append(_synchroniser(eng, data, auteur="concurrent"))) == []
    assert sorted(b.applique for b in bilans) == [False, True]
    assert _en_base(eng) == _servies(data)  # rien de dupliqué, rien de perdu
    # Une seule application dans l'historique : 1 réponse et 4 énoncés supprimés, 1 énoncé corrigé.
    assert ("enonce", "DELETE", 4) in _historique(eng, "concurrent")
    assert ("reponse", "DELETE", 1) in _historique(eng, "concurrent")
    assert ("enonce", "UPDATE", 1) in _historique(eng, "concurrent")


# --------------------------------------------------------------------- garde-fous


def test_un_lot_vide_est_refuse_et_la_base_garde_son_contenu(eng):
    from app.services import corpus_bci_base as base

    with pytest.raises(ValueError, match="vide"):
        with eng.begin() as c:
            base.synchroniser(c, [], "empreinte-quelconque", auteur="vide")
    assert len(_en_base(eng)) == len(_servies(_fichier()))


def test_le_moteur_applique_le_fichier_a_la_premiere_lecture(eng, monkeypatch):
    """Bout en bout : la base porte un autre lot ; la première lecture du moteur la met à jour."""
    from sqlalchemy import text

    from app.services import baoule_ivr

    _synchroniser(eng, _modifie(), auteur="ancien lot")
    monkeypatch.setattr("app.db.engine.get_engine", lambda: eng)
    monkeypatch.setattr(baoule_ivr, "_synchronises", set())
    monkeypatch.setattr(baoule_ivr, "_cache", None)

    assert list(baoule_ivr.entrees()) == _servies(_fichier())
    with eng.connect() as c:
        auteurs = c.execute(text(
            "SELECT DISTINCT auteur FROM historique_linguistique WHERE auteur LIKE 'moteur, lot %'"
        )).scalars().all()
    assert auteurs == [f"moteur, lot {baoule_ivr._lot_fichier(str(baoule_ivr.CORPUS_PATH)).empreinte[:12]}"]
    assert sorted(baoule_ivr.filieres()) == sorted({e["filiere"] for e in _servies(_fichier())})


def test_le_cache_suit_le_lot_en_base_sans_redemarrage(eng, monkeypatch):
    """Décision (B) : le corpus servi est gardé en mémoire tant que le lot en base ne change
    pas, et l'empreinte est relue À CHAQUE requête. La propriété exigée : le lot change en
    base (ici, par un autre processus) -> la lecture suivante voit le nouveau contenu."""
    from app.services import baoule_ivr, corpus_bci_base

    lectures = []
    charger = corpus_bci_base.charger
    monkeypatch.setattr(corpus_bci_base, "charger", lambda c: lectures.append(1) or charger(c))
    monkeypatch.setattr("app.db.engine.get_engine", lambda: eng)
    monkeypatch.setattr(baoule_ivr, "_synchronises", set())
    monkeypatch.setattr(baoule_ivr, "_cache", None)

    assert list(baoule_ivr.entrees()) == _servies(_fichier())
    assert list(baoule_ivr.entrees()) == _servies(_fichier())
    assert len(lectures) == 1  # lot inchangé : le corpus n'est pas relu

    _synchroniser(eng, _modifie(), auteur="autre processus")
    assert list(baoule_ivr.entrees()) == _servies(_modifie())
    assert len(lectures) == 2


def test_deux_premieres_requetes_du_moteur_ne_synchronisent_qu_une_fois(eng, monkeypatch):
    """La même course, par le CHEMIN DU MOTEUR (`_synchroniser_si_besoin`) : il doit garder sa
    transaction, sans quoi son verrou consultatif (de transaction) ne verrouille rien. Le test
    précédent tient sa propre transaction et ne verrait pas cette fuite."""
    from app.services import baoule_ivr

    _synchroniser(eng, _modifie(), auteur="ancien lot")
    monkeypatch.setattr(baoule_ivr, "_synchronises", set())
    auteur = f"moteur, lot {baoule_ivr._lot_fichier(str(baoule_ivr.CORPUS_PATH)).empreinte[:12]}"
    depuis = _dernier(eng)  # un test précédent écrit sous le même auteur : ne compter que celui-ci

    assert _course_forcee(eng, lambda: baoule_ivr._synchroniser_si_besoin(eng)) == []
    assert _en_base(eng) == _servies(_fichier())
    # Une seule application : bci-q0 rajoutée (1 réponse, 4 énoncés), la traduction rétablie.
    historique = _historique(eng, auteur, depuis)
    assert ("reponse", "INSERT", 1) in historique
    assert ("enonce", "INSERT", 4) in historique
    assert ("enonce", "UPDATE", 1) in historique


def test_un_fichier_refuse_n_empeche_pas_de_servir_la_base(eng, monkeypatch, caplog):
    """Le refus d'un lot vide protège la base : encore faut-il que le moteur continue de la
    servir. Le refus est définitif pour ce fichier — il n'est pas retenté à chaque requête."""
    from app.services import baoule_ivr

    tentatives = []
    vide = baoule_ivr._Lot("lot-vide", ())
    monkeypatch.setattr(baoule_ivr, "_lot_fichier", lambda path: tentatives.append(1) or vide)
    monkeypatch.setattr("app.db.engine.get_engine", lambda: eng)
    monkeypatch.setattr(baoule_ivr, "_synchronises", set())
    monkeypatch.setattr(baoule_ivr, "_cache", None)

    with caplog.at_level("ERROR", logger="app.services.baoule_ivr"):
        assert list(baoule_ivr.entrees()) == _servies(_fichier())
        assert list(baoule_ivr.entrees()) == _servies(_fichier())
    refus = [r.getMessage() for r in caplog.records if "refusé" in r.getMessage()]
    assert len(refus) == 1 and "lot-vide" in refus[0]
