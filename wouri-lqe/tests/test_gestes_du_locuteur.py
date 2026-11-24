"""Les gestes du locuteur ne se font jamais à sa place (#643).

Neuf routes écrivent au nom du locuteur : décider, reprendre, corriger, redire une
réponse, publier, enregistrer une phrase de dictée, importer (JSON, fichier, réponse
audio). Elles lisaient `user["lang"]` en direct : une session `*` (tout compte admin)
recevait un refus au motif faux (`not_found` alors que la fiche existe, `parity_required`)
ou inutile (`unknown_language`), et `/ingest/audio` gardait l'audio avant de refuser.

On ne leur ajoute PAS de paramètre de langue. Décider, corriger, reprendre et redire ne
gardent pas l'auteur, et le build du NLU prend `admin_accepted` pour la parole du
locuteur : un admin qui opérerait à sa place serait indistinguable de lui. La règle sœur
`session.langue_du_locuteur` refuse donc toute session `*` : 403
`speaker_account_required`, avant toute lecture et toute écriture.

Vrais comptes, vraie connexion. Données factices : aucune phrase de langue inventée
(le baoulé « Blɛ benin ? / Be lua i » reprend celui de test_reprendre.py).
"""
import inspect
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import corpus as corpus_router
from app.routers import dictation as dictation_router
from app.routers import ingest as ingest_router
from app.routers import session as session_router
from app.routers import tasks as tasks_router
from app.services import dictation_repo
from app.services import productions_repo as repo
from app.services import users as users_svc
from app.services import workflow
from app.services.ingest import ingest

_LOC = [{"user": "esse", "password": "essepass12", "language": "bci"}]
_AUDIO = ("voix.webm", b"VOIX", "audio/webm")
_MOT = {"kind": "mot_cle", "text_local": "mot bci (factice)", "text_fr": "mot (factice)",
        "concept_nlu": "CULTURE_MAIS", "id": "CULTURE_MAIS:factice"}


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ADMIN_USER", "adc.admin")
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", "adminpass1")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC))
    app = FastAPI()
    for r in (session_router, tasks_router, corpus_router, dictation_router, ingest_router):
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


# ------------------------------------------------------------------ une fiche par geste


def _fiche(texte: str, *, kind: str = "contenu", statut: str = "bronze") -> str:
    entree = {"text_local": texte, "text_fr": "fr (factice)", "id": texte}
    if kind == "paire_qr":
        entree.update(kind="paire_qr", reponse_bci="Be lua i", reponse_fr="On plante")
    assert ingest([entree], language="bci", actor="esse")["accepted"] == 1
    fid = next(r["id"] for r in repo.list_by(language="bci") if r["text_local"] == texte)
    if statut != "bronze":
        assert workflow.decide(fid, statut, language="bci")["ok"]
    return fid


def _phrase_de_dictee() -> str:
    dictation_repo.import_prompts(language="bci", prompts=[{"text_local": "phrase bci (factice)"}])
    return dictation_repo.list_prompts(language="bci")[0]["id"]


# Chaque geste : (méthode d'appel, préparation qui rend les arguments de l'appel).
GESTES = {
    "decision": lambda: ("/tasks/decision", {"json": {"id": _fiche("a decider"), "decision": "admin_accepted"}}),
    "reprendre": lambda: ("/tasks/reprendre", {"json": {"id": _fiche("a reprendre", statut="admin_accepted")}}),
    "edit": lambda: ("/tasks/edit", {"json": {"id": _fiche("a corriger"), "text_local": "corrige (factice)",
                                               "text_fr": "fr"}}),
    "voix": lambda: (f"/tasks/{_fiche('Blɛ benin ?', kind='paire_qr')}/voix", {"files": {"audio": _AUDIO}}),
    "promote": lambda: ("/corpus/promote", {"json": {"id": _fiche("a publier", statut="admin_accepted")}}),
    "dictee": lambda: (f"/dictation/{_phrase_de_dictee()}/audio", {"files": {"audio": _AUDIO}}),
    "ingest_json": lambda: ("/ingest/json", {"json": [_MOT]}),
    "ingest_file": lambda: ("/ingest/file", {"files": {"file": ("mots.json", json.dumps([_MOT]).encode(),
                                                                "application/json")}}),
    "ingest_audio": lambda: ("/ingest/audio", {"data": {"concept_id": "mais_conseil_001",
                                                        "text_fr": "Plante ton mais"},
                                               "files": {"audio": _AUDIO}}),
}
_MODULES = {"decision": tasks_router, "reprendre": tasks_router, "edit": tasks_router, "voix": tasks_router,
            "promote": corpus_router, "dictee": dictation_router, "ingest_json": ingest_router,
            "ingest_file": ingest_router, "ingest_audio": ingest_router}

parametre_geste = pytest.mark.parametrize("geste", list(GESTES))


def _etat(tmp_path) -> tuple:
    """Tout ce qu'un geste peut écrire : fiches, phrases de dictée, fichiers audio."""
    fiches = sorted((r["id"], r["status"], r["text_local"], r["text_fr"], r["audio_url"],
                     json.dumps(r["meta"], sort_keys=True)) for r in repo.list_by(language="bci"))
    dictee = sorted((p["id"], p["status"], p["audio_url"]) for p in dictation_repo.list_prompts(language="bci"))
    dossier = tmp_path / "audio"
    audios = sorted(p.name for p in dossier.iterdir()) if dossier.exists() else []
    return fiches, dictee, audios


def _faire(cli, geste):
    url, kwargs = GESTES[geste]()
    return cli.post(url, **kwargs)


# ------------------------------------------------------------------ le défaut de #643


@parametre_geste
def test_une_session_etoile_est_refusee_avec_un_motif_vrai(seeded, corpus, monkeypatch, tmp_path, geste):
    cli = _admin(monkeypatch, tmp_path)
    r = _faire(cli, geste)
    assert r.status_code == 403, f"{geste} : {r.status_code} {r.text[:160]}"
    assert r.json()["detail"] == "speaker_account_required"


@parametre_geste
def test_rien_n_est_ecrit_quand_le_geste_est_refuse(seeded, corpus, monkeypatch, tmp_path, geste):
    """Ni fiche, ni phrase, ni fichier audio — /ingest/audio gardait l'audio avant de refuser."""
    cli = _admin(monkeypatch, tmp_path)
    url, kwargs = GESTES[geste]()  # la préparation écrit ; l'état se lit APRÈS elle
    avant = _etat(tmp_path)
    cli.post(url, **kwargs)
    assert _etat(tmp_path) == avant


@parametre_geste
def test_un_compte_qui_garde_l_etoile_sans_etre_admin_est_refuse(seeded, corpus, monkeypatch, tmp_path, geste):
    """La garde porte sur la VALEUR `*`, pas sur le rôle (un admin rétrogradé la garde)."""
    _client(monkeypatch, tmp_path)  # fixe LQE_DATA_DIR avant d'écrire le compte
    assert users_svc.create_user(user="ancien.admin", password="ancienpass1",
                                 language="bci", roles=["admin"])["ok"]
    assert users_svc.update_user("ancien.admin", roles=["review", "ingest", "promote"])["ok"]
    assert users_svc.find_user("ancien.admin")["language"] == "*"  # la prémisse
    r = _faire(_connecte(monkeypatch, tmp_path, "ancien.admin", "ancienpass1"), geste)
    assert r.status_code == 403 and r.json()["detail"] == "speaker_account_required"


# ------------------------------------------------------------------ rien ne change pour le locuteur


@parametre_geste
def test_le_locuteur_fait_ses_gestes_comme_avant(seeded, corpus, monkeypatch, tmp_path, geste):
    """Ce que le front envoie aujourd'hui, sans langue : le geste aboutit et écrit."""
    cli = _locuteur(monkeypatch, tmp_path)
    url, kwargs = GESTES[geste]()
    avant = _etat(tmp_path)
    r = cli.post(url, **kwargs)
    assert r.status_code == 200, f"{geste} : {r.status_code} {r.text[:160]}"
    assert _etat(tmp_path) != avant


# ------------------------------------------------------------------ une seule règle, et la bonne


def test_les_routeurs_tiennent_la_regle_sœur():
    for module in (tasks_router, corpus_router, dictation_router, ingest_router):
        assert module.langue_du_locuteur is session_router.langue_du_locuteur, module.__name__


@parametre_geste
def test_chaque_geste_passe_par_la_regle_sœur(seeded, corpus, monkeypatch, tmp_path, geste):
    """Une copie en ligne de la règle contournerait la sonde : la route doit répondre 418."""
    def sonde(user):
        raise HTTPException(status_code=418, detail="regle_soeur")

    cli = _locuteur(monkeypatch, tmp_path)
    monkeypatch.setattr(_MODULES[geste], "langue_du_locuteur", sonde)
    r = _faire(cli, geste)
    assert r.status_code == 418 and r.json()["detail"] == "regle_soeur"


def test_les_deux_politiques_restent_distinctes():
    """Lire : un admin nomme la langue. Agir comme le locuteur : personne à sa place.
    Fusionner les deux fonctions, ou donner une langue à la seconde, ferait échouer ceci."""
    admin = {"u": "adc.admin", "lang": "*", "roles": ["admin"]}
    with pytest.raises(HTTPException) as lire:
        session_router.langue_visee(admin, None)
    assert (lire.value.status_code, lire.value.detail) == (400, "language_required")
    with pytest.raises(HTTPException) as agir:
        session_router.langue_du_locuteur(admin)
    assert (agir.value.status_code, agir.value.detail) == (403, "speaker_account_required")
    assert list(inspect.signature(session_router.langue_du_locuteur).parameters) == ["user"]
    assert session_router.langue_du_locuteur({"u": "esse", "lang": "bci", "roles": []}) == "bci"


def test_aucun_routeur_ne_lit_la_langue_de_session_en_direct():
    """La prochaine route qui lirait `user["lang"]` elle-même rouvrirait la classe de
    défauts de #637, #641 et #643. Seul session.py la lit : ses deux règles et /auth/me."""
    from pathlib import Path

    dossier = Path(session_router.__file__).parent
    fautifs = [f"{p.name}:{n}" for p in sorted(dossier.glob("*.py")) if p.name != "session.py"
               for n, ligne in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if 'user["lang"]' in ligne or "user['lang']" in ligne]
    assert fautifs == []
