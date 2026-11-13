"""Reposer une question au locuteur (ADR-0047).

Un relecteur remet une fiche « a valider » AVEC le motif. Sans ce motif, le locuteur
reverrait la fiche comme neuve et la re-deciderait a l'identique : c'est toute la raison
d'etre du mecanisme. Le motif disparait des qu'il a tranche.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import productions_repo as repo
from app.services import workflow
from app.services.ingest import ingest

_MOT = {"kind": "mot_cle", "text_local": "gua", "text_fr": "prix",
        "concept_nlu": "ACTION_VENDRE", "id": "ACTION_VENDRE:gua"}
_MOTIF = "ta traduction « prix » ne dit pas le concept « vendre »"


def _id(text_local, language="bci"):
    return next(r["id"] for r in repo.list_by(language=language)
                if r["text_local"] == text_local)


def test_la_fiche_revient_a_valider_avec_son_motif(seeded):
    ingest([_MOT], language="bci", actor="loc")
    tid = _id("gua")
    assert workflow.decide(tid, "admin_accepted", language="bci")["ok"]

    out = workflow.remettre_en_question(tid, language="bci", motif=_MOTIF)
    assert out["ok"] and out["status"] == "bronze"

    row = repo.get(item_id=tid, language="bci")
    assert row["status"] == "bronze"
    assert row["meta"]["motif_reexamen"] == _MOTIF
    # le texte n'est PAS restaure : on reexamine la fiche telle qu'elle est
    assert row["text_local"] == "gua"


def test_le_motif_disparait_quand_le_locuteur_a_tranche(seeded):
    ingest([_MOT], language="bci", actor="loc")
    tid = _id("gua")
    workflow.decide(tid, "admin_accepted", language="bci")
    workflow.remettre_en_question(tid, language="bci", motif=_MOTIF)
    assert "motif_reexamen" in repo.get(item_id=tid, language="bci")["meta"]

    assert workflow.decide(tid, "admin_rejected", language="bci")["ok"]
    row = repo.get(item_id=tid, language="bci")
    assert row["status"] == "admin_rejected"
    assert "motif_reexamen" not in row["meta"]


def test_un_motif_vide_est_refuse(seeded):
    """Reposer une question sans dire pourquoi ne sert a rien : la fiche serait
    re-decidee a l'identique."""
    ingest([_MOT], language="bci", actor="loc")
    tid = _id("gua")
    for vide in ("", "   "):
        out = workflow.remettre_en_question(tid, language="bci", motif=vide)
        assert out == {"ok": False, "reason": "motif_requis"}
    assert "motif_reexamen" not in repo.get(item_id=tid, language="bci")["meta"]


def test_ne_touche_jamais_une_production(seeded):
    """Seul un `contenu` atteint 'production' : une validation (mot-cle, paire) n'est
    jamais publiee (ADR-0045, garde dans `repo.promote`). Le test porte donc sur un
    contenu — c'est le seul cas ou le statut 'production' existe reellement."""
    ingest([{"text_local": "Aw ni ce", "text_fr": "Merci"}], language="bci", actor="loc")
    tid = _id("Aw ni ce")
    assert workflow.decide(tid, "admin_accepted", language="bci")["ok"]
    assert workflow.promote(tid, language="bci", actor="admin")["ok"]

    out = workflow.remettre_en_question(tid, language="bci", motif=_MOTIF)
    assert out["ok"] is False and out["reason"] == "locked"
    assert repo.get(item_id=tid, language="bci")["status"] == "production"


def test_ne_touche_jamais_une_autre_langue(seeded):
    ingest([_MOT], language="bci", actor="loc")
    tid = _id("gua")
    assert workflow.remettre_en_question(tid, language="dyu", motif=_MOTIF) == {
        "ok": False, "reason": "not_found"}
    assert "motif_reexamen" not in repo.get(item_id=tid, language="bci")["meta"]


def test_route_reexamen_reservee_a_l_admin(seeded, monkeypatch):
    from app.routers import tasks

    ingest([_MOT], language="bci", actor="loc")
    tid = _id("gua")
    app = FastAPI()
    app.include_router(tasks.router)

    # require_role("admin") passe par current_user : le dict doit porter les roles.
    # ATTENTION : cette session est FABRIQUEE. Un compte admin reel porte toujours la
    # langue `*` (users.create_user l'impose), jamais `bci` — c'est pourquoi ce test
    # passait alors que la route etait inatteignable en production. Le cas reel est
    # couvert par tests/test_tasks_langue_admin.py, qui se connecte pour de vrai.
    app.dependency_overrides[tasks.current_user] = lambda: {
        "u": "admin", "lang": "bci", "roles": ["admin", "review"],
    }
    cli = TestClient(app)
    r = cli.post("/tasks/reexamen", json={"id": tid, "motif": _MOTIF})
    assert r.status_code == 200 and r.json()["status"] == "bronze"

    r = cli.post("/tasks/reexamen", json={"id": tid, "motif": ""})
    assert r.status_code == 422  # motif vide refuse par le schema
