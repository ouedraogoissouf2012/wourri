"""Les lectures de l'atelier ne répondent jamais « 200, rien » à une session `*` (#641).

Suite de #637. Quatre routes lisaient la langue de session, filtraient en égalité stricte
sur `*` et répondaient 200 avec zéro entrée : GET /corpus sans `language`,
GET /assignments, GET /dictation/prompts et GET /dictation/progress. Une réponse vide
est indistinguable d'un travail inexistant : on conclurait que le locuteur n'a rien fait.

Une seule règle, `session.langue_visee`, pour tout le service : sans langue nommée, une
session `*` reçoit 400 `language_required` ; seul un admin nomme une langue (403 sinon,
même la sienne) ; une langue inconnue donne 400. Vrais comptes, vraie connexion.
"""
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import assignments as assignments_router
from app.routers import corpus as corpus_router
from app.routers import dictation as dictation_router
from app.routers import session as session_router
from app.routers import tasks as tasks_router
from app.services import assignments, workflow
from app.services import dictation_repo
from app.services import users as users_svc
from app.services.ingest import ingest
from app.services.pg_catalog import PgCorpusCatalog

_LOC = [{"user": "esse", "password": "essepass12", "language": "bci"}]

# Ce que chaque route sert pour une langue, et comment le lire dans sa réponse.
ROUTES = {
    "/corpus": lambda j: [e["text_local"] for e in j["entries"]],
    "/assignments": lambda j: [a["concept_id"] for a in j["assignments"]],
    "/dictation/prompts": lambda j: [p["text_local"] for p in j["prompts"]],
    "/dictation/progress": lambda j: j["total"],
}
# Données factices (aucune phrase de langue inventée) : un élément par route et par langue.
ATTENDU = {
    "bci": {"/corpus": ["contenu bci (factice)"], "/assignments": ["mais_conseil_001"],
            "/dictation/prompts": ["phrase bci (factice)"], "/dictation/progress": 1},
    "dyu": {"/corpus": ["contenu dyu (factice)"], "/assignments": ["riz_conseil_001"],
            "/dictation/prompts": ["phrase dyu (factice)"], "/dictation/progress": 1},
}
_CONCEPT = {"bci": "mais_conseil_001", "dyu": "riz_conseil_001"}

parametre_route = pytest.mark.parametrize("route", list(ROUTES))


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "adc.admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    app = FastAPI()
    for r in (session_router, corpus_router, assignments_router, dictation_router):
        app.include_router(r.router)
    return TestClient(app)


def _connecte(monkeypatch, tmp_path, user: str, password: str) -> TestClient:
    cli = _client(monkeypatch, tmp_path)
    assert cli.post("/auth/login", json={"user": user, "password": password}).status_code == 200
    return cli


def _admin(monkeypatch, tmp_path):
    return _connecte(monkeypatch, tmp_path, "adc.admin", "adminpass1")


def _locuteur(monkeypatch, tmp_path):
    return _connecte(monkeypatch, tmp_path, "esse", "essepass12")


def _peupler(langue: str) -> None:
    """Un élément servi par chacune des quatre routes, dans `langue`."""
    texte = f"contenu {langue} (factice)"
    assert ingest([{"text_local": texte, "text_fr": "fr", "id": texte}],
                  language=langue, actor="esse")["accepted"] == 1
    tid = next(t["id"] for t in workflow.list_tasks(language=langue) if t["text_local"] == texte)
    assert workflow.decide(tid, "admin_accepted", language=langue)["ok"]
    assert workflow.promote(tid, language=langue, actor="adc.admin")["ok"]
    assert assignments.assign_batch([_CONCEPT[langue]], target_language=langue, assigned_by="adc.admin",
                                    catalog=PgCorpusCatalog())["assigned"] == 1
    assert dictation_repo.import_prompts(
        language=langue, prompts=[{"text_local": f"phrase {langue} (factice)"}])["inserted"] == 1


def _lire(cli, route, **params):
    return cli.get(route, params=params)


# ------------------------------------------------------------------ le défaut de #641


@parametre_route
def test_une_session_etoile_sans_langue_est_refusee(seeded, corpus, monkeypatch, tmp_path, route):
    """Le cas de l'issue : compte admin, aucun paramètre. Jamais « 200, rien »."""
    _peupler("bci")
    r = _lire(_admin(monkeypatch, tmp_path), route)
    assert r.status_code == 400, f"{route} : {r.status_code} {r.text[:120]}"
    assert r.json()["detail"] == "language_required"


@parametre_route
def test_un_compte_qui_garde_l_etoile_sans_etre_admin_est_refuse(seeded, corpus, monkeypatch, tmp_path, route):
    """La garde porte sur la VALEUR `*`, pas sur le rôle : `update_user` garde la langue
    quand seuls les rôles changent, un admin rétrogradé porte encore `*`. Rôles ingest +
    review : il franchit `require_role("ingest")` des routes de dictée."""
    _peupler("bci")
    _client(monkeypatch, tmp_path)  # fixe LQE_DATA_DIR avant d'écrire le compte
    assert users_svc.create_user(user="ancien.admin", password="ancienpass1",
                                 language="bci", roles=["admin"])["ok"]
    assert users_svc.update_user("ancien.admin", roles=["ingest", "review"])["ok"]
    assert users_svc.find_user("ancien.admin")["language"] == "*"  # la prémisse
    r = _lire(_connecte(monkeypatch, tmp_path, "ancien.admin", "ancienpass1"), route)
    assert r.status_code == 400 and r.json()["detail"] == "language_required"


# ------------------------------------------------------------------ ce que le correctif ouvre


@parametre_route
def test_un_admin_lit_la_langue_qu_il_nomme(seeded, corpus, monkeypatch, tmp_path, route):
    _peupler("bci")
    r = _lire(_admin(monkeypatch, tmp_path), route, language="bci")
    assert r.status_code == 200
    assert r.json()["language"] == "bci"
    assert ROUTES[route](r.json()) == ATTENDU["bci"][route]


@parametre_route
def test_un_admin_ne_recoit_jamais_une_autre_langue(seeded, corpus, monkeypatch, tmp_path, route):
    _peupler("bci")
    _peupler("dyu")
    cli = _admin(monkeypatch, tmp_path)
    for langue in ("bci", "dyu"):
        j = _lire(cli, route, language=langue).json()
        assert j["language"] == langue
        assert ROUTES[route](j) == ATTENDU[langue][route]


# ------------------------------------------------------------------ l'isolation d'ADR-0034


@parametre_route
def test_un_locuteur_ne_peut_pas_nommer_une_langue(seeded, corpus, monkeypatch, tmp_path, route):
    """Le paramètre ne perce pas l'isolation — même pour sa PROPRE langue."""
    cli = _locuteur(monkeypatch, tmp_path)
    for langue in ("dyu", "bci"):
        assert _lire(cli, route, language=langue).status_code == 403


@parametre_route
def test_langue_inconnue_refusee(seeded, corpus, monkeypatch, tmp_path, route):
    r = _lire(_admin(monkeypatch, tmp_path), route, language="zzz")
    assert r.status_code == 400 and r.json()["detail"] == "unknown_language"


@parametre_route
def test_l_appel_du_locuteur_sans_parametre_n_est_pas_touche(seeded, corpus, monkeypatch, tmp_path, route):
    """Ce que le front appelle aujourd'hui (Studio, Mes demandes, Dictée)."""
    _peupler("bci")
    _peupler("dyu")
    j = _lire(_locuteur(monkeypatch, tmp_path), route).json()
    assert j["language"] == "bci"
    assert ROUTES[route](j) == ATTENDU["bci"][route]


# ------------------------------------------------------------------ une seule règle


_ROUTEURS = {
    "/corpus": corpus_router, "/assignments": assignments_router,
    "/dictation/prompts": dictation_router, "/dictation/progress": dictation_router,
}


def test_tous_les_routeurs_tiennent_la_meme_regle():
    """Une seule définition dans le service : chaque routeur qui lit une langue tient
    l'objet même de `session.langue_visee`, jamais une copie."""
    for module in (tasks_router, corpus_router, assignments_router, dictation_router):
        assert module.langue_visee is session_router.langue_visee, module.__name__


@parametre_route
def test_chaque_route_passe_par_la_regle_partagee(seeded, monkeypatch, tmp_path, route):
    """Une copie en ligne de la règle (comme celle que portait corpus.py) contournerait
    `langue_visee` : on la remplace par une sonde, la route doit répondre ce qu'elle dit."""
    def sonde(user, demandee):
        raise HTTPException(status_code=418, detail="regle_partagee")

    monkeypatch.setattr(_ROUTEURS[route], "langue_visee", sonde)
    r = _lire(_locuteur(monkeypatch, tmp_path), route)
    assert r.status_code == 418 and r.json()["detail"] == "regle_partagee"


def test_sans_session_rien(seeded, monkeypatch, tmp_path):
    cli = _client(monkeypatch, tmp_path)
    for route in ROUTES:
        assert _lire(cli, route, language="bci").status_code == 401
