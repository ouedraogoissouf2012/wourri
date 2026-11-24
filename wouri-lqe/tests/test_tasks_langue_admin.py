"""Un admin nomme la langue sur `/tasks` — ADR-0047 rendu atteignable, ADR-0034 intact.

Pourquoi ces tests existent. `POST /tasks/reexamen` exige le rôle `admin` ; or
`users.create_user` force la langue d'un compte admin à `*`
(`test_users.py::test_create_admin_gets_wildcard_language`), et le dépôt filtre en
égalité stricte (`WHERE language = %s`, sans joker). Le mécanisme d'ADR-0047 — reposer
une question au locuteur AVEC le motif — était donc **inatteignable pour toute langue,
par tout compte**. C'est la raison pour laquelle la relecture des mots-clés baoulé du
2026-10-26 a été faite en éditant un fichier du dépôt, et pourquoi le locuteur n'a
jamais su ce qui avait été décidé de ses mots.

Le test qui existait ne l'a pas vu parce qu'il **fabriquait** une session
`{"lang": "bci", "roles": ["admin"]}` que le système ne sait pas produire. Ceux-ci
passent par de vrais comptes et une vraie connexion : l'état impossible ne peut pas
y être simulé.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import productions_repo as repo
from app.services import users as users_svc
from app.services import workflow
from app.services.ingest import ingest

# Reproduit la production : `esse.adc` est un compte de locuteur (langue bci, pas admin),
# `adc.admin` est l'admin d'amorçage — qui porte forcément la langue `*`.
_LOC = [{"user": "esse", "password": "essepass12", "language": "bci"}]
_MOT = {"kind": "mot_cle", "text_local": "gua", "text_fr": "prix",
        "concept_nlu": "ACTION_VENDRE", "id": "ACTION_VENDRE:gua"}
_MOTIF = "ta traduction « prix » ne dit pas le concept « vendre »"


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "adc.admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    from app.routers import session as session_router
    from app.routers import tasks as tasks_router

    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(tasks_router.router)
    return TestClient(app)


def _admin(monkeypatch, tmp_path) -> TestClient:
    cli = _client(monkeypatch, tmp_path)
    assert cli.post("/auth/login", json={"user": "adc.admin", "password": "adminpass1"}).status_code == 200
    return cli


def _locuteur(monkeypatch, tmp_path) -> TestClient:
    cli = _client(monkeypatch, tmp_path)
    assert cli.post("/auth/login", json={"user": "esse", "password": "essepass12"}).status_code == 200
    return cli


def _un_mot_a_valider() -> str:
    ingest([_MOT], language="bci", actor="esse")
    return next(r["id"] for r in repo.list_by(language="bci") if r["text_local"] == "gua")


def _une_paire_acceptee(language: str, question: str) -> str:
    """Une paire question/réponse acceptée par le locuteur : ce que lit le build du NLU."""
    paire = {"kind": "paire_qr", "text_local": question, "text_fr": "Quand ?",
             "reponse_bci": "Be lua i", "reponse_fr": "On plante", "id": f"paire:{question}"}
    ingest([paire], language=language, actor="esse")
    pid = next(r["id"] for r in repo.list_by(language=language) if r["text_local"] == question)
    assert workflow.decide(pid, "admin_accepted", language=language)["ok"]
    return pid


# ------------------------------------------------------------------ la prémisse


def test_la_session_admin_porte_forcement_la_langue_etoile(seeded, monkeypatch, tmp_path):
    """Toute la raison d'être du paramètre tient dans cette ligne."""
    cli = _admin(monkeypatch, tmp_path)
    me = cli.get("/auth/me").json()
    assert me["language"] == "*" and "admin" in me["roles"]


def test_sans_parametre_un_admin_est_refuse_au_lieu_de_recevoir_des_listes_vides(
        seeded, monkeypatch, tmp_path):
    """#637 : ce test exigeait 200 et trois listes vides (#617) — il figeait le défaut.
    La langue `*` ne vise aucune fiche : répondre « rien » ment, refuser le dit."""
    _un_mot_a_valider()
    r = _admin(monkeypatch, tmp_path).get("/tasks")
    assert r.status_code == 400
    assert r.json()["detail"] == "language_required"


# ------------------------------------------------------------------ ce que le correctif ouvre


def test_un_admin_voit_les_fiches_de_la_langue_qu_il_nomme(seeded, monkeypatch, tmp_path):
    _un_mot_a_valider()
    t = _admin(monkeypatch, tmp_path).get("/tasks?language=bci").json()
    assert t["language"] == "bci"
    assert [r["text_local"] for r in t["bronze"]] == ["gua"]


def test_un_admin_repose_la_question_dans_la_langue_qu_il_nomme(seeded, monkeypatch, tmp_path):
    """Le cœur du correctif : sans `language`, cet appel ne pouvait que renvoyer 404."""
    tid = _un_mot_a_valider()
    r = _admin(monkeypatch, tmp_path).post(
        "/tasks/reexamen", json={"id": tid, "motif": _MOTIF, "language": "bci"})
    assert r.status_code == 200 and r.json()["status"] == "bronze"
    assert repo.get(item_id=tid, language="bci")["meta"]["motif_reexamen"] == _MOTIF


def test_le_motif_parvient_bien_au_locuteur(seeded, monkeypatch, tmp_path):
    """Ce qui compte pour de vrai : le locuteur revoit sa fiche AVEC la raison."""
    tid = _un_mot_a_valider()
    assert _admin(monkeypatch, tmp_path).post(
        "/tasks/reexamen", json={"id": tid, "motif": _MOTIF, "language": "bci"}
    ).status_code == 200

    vu = _locuteur(monkeypatch, tmp_path).get("/tasks").json()
    fiche = next(r for r in vu["bronze"] if r["id"] == tid)
    assert fiche["meta"]["motif_reexamen"] == _MOTIF


def test_sans_langue_l_admin_ne_peut_toujours_pas_reposer_la_question(seeded, monkeypatch, tmp_path):
    """La langue `*` ne vise rien. #637 : l'appel répondait 404 `not_found` alors que la
    fiche existe — un faux motif ; il dit maintenant ce qui manque."""
    tid = _un_mot_a_valider()
    r = _admin(monkeypatch, tmp_path).post("/tasks/reexamen", json={"id": tid, "motif": _MOTIF})
    assert r.status_code == 400
    assert r.json()["detail"] == "language_required"
    assert "motif_reexamen" not in repo.get(item_id=tid, language="bci")["meta"]


# ------------------------------------------------------------------ l'isolation d'ADR-0034


def test_un_locuteur_ne_peut_pas_nommer_une_langue(seeded, monkeypatch, tmp_path):
    """Le cœur de la garde : le paramètre ne perce pas l'isolation entre locuteurs."""
    cli = _locuteur(monkeypatch, tmp_path)
    assert cli.get("/tasks?language=dyu").status_code == 403
    # Même sa PROPRE langue est refusée : seul un admin nomme une langue.
    assert cli.get("/tasks?language=bci").status_code == 403


def test_un_locuteur_ne_peut_pas_reposer_une_question(seeded, monkeypatch, tmp_path):
    """Reposer une question reste un geste de relecteur (ADR-0047), pas de locuteur."""
    tid = _un_mot_a_valider()
    r = _locuteur(monkeypatch, tmp_path).post(
        "/tasks/reexamen", json={"id": tid, "motif": _MOTIF, "language": "bci"})
    assert r.status_code == 403
    assert "motif_reexamen" not in repo.get(item_id=tid, language="bci")["meta"]


def test_langue_inconnue_refusee(seeded, monkeypatch, tmp_path):
    cli = _admin(monkeypatch, tmp_path)
    assert cli.get("/tasks?language=zzz").status_code == 400
    r = cli.get("/tasks/validations", params={"kind": "paire_qr", "language": "zzz"})
    assert r.status_code == 400 and r.json()["detail"] == "unknown_language"
    tid = _un_mot_a_valider()
    assert cli.post(
        "/tasks/reexamen", json={"id": tid, "motif": _MOTIF, "language": "zzz"}
    ).status_code == 400


def test_l_appel_existant_du_locuteur_n_est_pas_touche(seeded, monkeypatch, tmp_path):
    """Le front appelle `/tasks` sans paramètre : ce comportement ne change pas."""
    _un_mot_a_valider()
    t = _locuteur(monkeypatch, tmp_path).get("/tasks").json()
    assert t["language"] == "bci"
    assert [r["text_local"] for r in t["bronze"]] == ["gua"]


def test_sans_session_rien(seeded, monkeypatch, tmp_path):
    cli = _client(monkeypatch, tmp_path)
    assert cli.get("/tasks?language=bci").status_code == 401
    assert cli.get("/tasks/validations",
                   params={"kind": "paire_qr", "language": "bci"}).status_code == 401
    assert cli.post(
        "/tasks/reexamen", json={"id": "1", "motif": _MOTIF, "language": "bci"}
    ).status_code == 401


# ------------------------------------------------------------------ /tasks/validations (#637)
#
# Les deux entrées obligatoires du build du NLU baoulé (`scripts/baoule_nlu_build.py`).
# Un admin qui n'obtenait rien, en 200, aurait reconstruit un corpus amputé sans un mot.


def test_un_admin_sans_langue_est_refuse_sur_les_validations(seeded, monkeypatch, tmp_path):
    """Le cas qui a motivé #637 : compte admin, aucun paramètre. Jamais « 200, 0 entrée »."""
    _une_paire_acceptee("bci", "Blɛ benin ?")
    r = _admin(monkeypatch, tmp_path).get("/tasks/validations", params={"kind": "paire_qr"})
    assert not (r.status_code == 200 and r.json().get("count") == 0), "le défaut qui ment"
    assert r.status_code == 400
    assert r.json()["detail"] == "language_required"


def test_un_admin_lit_les_validations_de_la_langue_qu_il_nomme(seeded, monkeypatch, tmp_path):
    _une_paire_acceptee("bci", "Blɛ benin ?")
    r = _admin(monkeypatch, tmp_path).get(
        "/tasks/validations", params={"kind": "paire_qr", "language": "bci"})
    assert r.status_code == 200
    v = r.json()
    assert v["language"] == "bci" and v["kind"] == "paire_qr" and v["count"] == 1
    assert [e["text_local"] for e in v["entries"]] == ["Blɛ benin ?"]


def test_un_admin_ne_recoit_jamais_une_autre_langue(seeded, monkeypatch, tmp_path):
    """Le build ne trie pas par langue (`accepted()` ne lit que le statut) : une réponse
    qui mêlerait le dioula au baoulé l'injecterait dans le NLU baoulé sans un mot."""
    _une_paire_acceptee("bci", "Blɛ benin ?")
    _une_paire_acceptee("dyu", "question dyu (factice)")
    cli = _admin(monkeypatch, tmp_path)
    for langue, question in (("bci", "Blɛ benin ?"), ("dyu", "question dyu (factice)")):
        v = cli.get("/tasks/validations", params={"kind": "paire_qr", "language": langue}).json()
        assert v["language"] == langue
        assert {e["language"] for e in v["entries"]} == {langue}
        assert [e["text_local"] for e in v["entries"]] == [question]


def test_un_locuteur_ne_peut_pas_nommer_une_langue_sur_les_validations(seeded, monkeypatch, tmp_path):
    """Le paramètre ne perce pas l'isolation d'ADR-0034 — même pour sa PROPRE langue."""
    _une_paire_acceptee("dyu", "question dyu (factice)")
    cli = _locuteur(monkeypatch, tmp_path)
    for langue in ("dyu", "bci"):
        r = cli.get("/tasks/validations", params={"kind": "paire_qr", "language": langue})
        assert r.status_code == 403


def test_l_appel_du_locuteur_sur_les_validations_n_est_pas_touche(seeded, monkeypatch, tmp_path):
    """Sans paramètre, un compte de langue `bci` lit ses validations comme avant."""
    _une_paire_acceptee("bci", "Blɛ benin ?")
    v = _locuteur(monkeypatch, tmp_path).get("/tasks/validations", params={"kind": "paire_qr"}).json()
    assert v["language"] == "bci" and v["count"] == 1
    assert [e["text_local"] for e in v["entries"]] == ["Blɛ benin ?"]


def test_un_compte_qui_garde_l_etoile_sans_etre_admin_est_refuse(seeded, monkeypatch, tmp_path):
    """La garde porte sur la VALEUR `*`, pas sur le rôle — ne pas la « simplifier » en test
    de rôle. `update_user` garde la langue quand seuls les rôles changent : un admin
    rétrogradé porte encore `*`, et un test de rôle le laisserait retomber dans « 200,
    rien »."""
    _une_paire_acceptee("bci", "Blɛ benin ?")
    cli = _client(monkeypatch, tmp_path)
    assert users_svc.create_user(user="ancien.admin", password="ancienpass1",
                                 language="bci", roles=["admin"])["ok"]
    assert users_svc.update_user("ancien.admin", roles=["review"])["ok"]
    compte = users_svc.find_user("ancien.admin")
    assert compte["language"] == "*" and compte["roles"] == ["review"]  # la prémisse

    assert cli.post("/auth/login", json={"user": "ancien.admin", "password": "ancienpass1"}).status_code == 200
    for r in (cli.get("/tasks/validations", params={"kind": "paire_qr"}), cli.get("/tasks")):
        assert r.status_code == 400
        assert r.json()["detail"] == "language_required"
