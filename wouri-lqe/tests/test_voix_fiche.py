"""La voix se refait dans la fiche (ADR-0045, revision du 2026-11-24). Sur Postgres reel.

Ce qui doit tenir :
  - la voix est attachee AU TEXTE : le serveur range, avec l'extrait, la reponse telle
    qu'elle est en base au moment de l'envoi — jamais un texte fourni par le client ;
  - seule une paire question/reponse recoit une voix (le marqueur `audio_a_reenregistrer`
    n'existe que pour elles), jamais une fiche publiee, jamais une autre langue ;
  - un refus n'ecrit aucun fichier audio (pas d'orphelin dans le stockage) ;
  - les controles de format, de vide et de taille sont ceux de la dictee.
"""
import json

from app.services import productions_repo as repo
from app.services import workflow
from app.services.ingest import ingest

_ADMIN = {"user": "adm", "password": "admin-pass-12"}
_LOC_BCI = [{"user": "loc", "password": "locpass12", "language": "bci"}]
# Textes repris des tests existants de l'atelier (test_reprendre.py) : aucun baoule invente.
_PAIRE = {"kind": "paire_qr", "text_local": "Blɛ benin ?", "text_fr": "Quand ?",
          "reponse_bci": "Be lua i", "reponse_fr": "On plante", "id": "paire:3:210"}
_MOT = {"kind": "mot_cle", "text_local": "kakao", "text_fr": "cacao",
        "concept_nlu": "CULTURE_CACAO", "id": "CULTURE_CACAO:kakao"}
_CONTENU = {"text_local": "contenu", "text_fr": "contenu fr"}


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    monkeypatch.setenv("LQE_ACCOUNTS", json.dumps(_LOC_BCI))
    monkeypatch.setenv("LQE_ADMIN_USER", _ADMIN["user"])
    monkeypatch.setenv("LQE_ADMIN_PASSWORD", _ADMIN["password"])


def _speaker(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers import session as session_router
    from app.routers import tasks as tasks_router

    _env(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(session_router.router)
    app.include_router(tasks_router.router)
    c = TestClient(app)
    assert c.post("/auth/login", json={"user": "loc", "password": "locpass12"}).status_code == 200
    return c


def _id(text_local, language="bci"):
    return next(r["id"] for r in repo.list_by(language=language) if r["text_local"] == text_local)


def _audios(tmp_path):
    dossier = tmp_path / "audio"
    return sorted(p.name for p in dossier.iterdir()) if dossier.exists() else []


def _envoyer(client, item_id, data=b"VOIX", mime="audio/webm", nom="voix.webm"):
    return client.post(f"/tasks/{item_id}/voix", files={"audio": (nom, data, mime)})


# ---------- la voix attachee au texte ----------

def test_la_voix_porte_la_reponse_lue_en_base(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    s = _speaker(monkeypatch, tmp_path)
    r = _envoyer(s, pid, data=b"VOIX-1")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["ok"] is True and corps["voix"]["champ"] == "reponse_bci"
    assert corps["voix"]["texte"] == "Be lua i"
    assert corps["voix"]["audio"].startswith("audio/")
    voix = repo.get(item_id=pid, language="bci")["meta"]["voix"]
    assert voix == corps["voix"]
    assert (tmp_path / voix["audio"]).read_bytes() == b"VOIX-1"


def test_la_voix_suit_la_reponse_corrigee(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    workflow.edit_text(pid, language="bci", text_local="Blɛ benin ?", text_fr="Quand ?",
                       reponse_bci="Be lua i kpa", reponse_fr="On plante bien")
    s = _speaker(monkeypatch, tmp_path)
    assert _envoyer(s, pid).json()["voix"]["texte"] == "Be lua i kpa"


def test_le_texte_du_client_est_ignore(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    s = _speaker(monkeypatch, tmp_path)
    r = s.post(f"/tasks/{pid}/voix", data={"texte": "autre chose"},
               files={"audio": ("v.webm", b"VOIX", "audio/webm")})
    assert r.json()["voix"]["texte"] == "Be lua i"


def test_une_nouvelle_voix_remplace_la_precedente(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    s = _speaker(monkeypatch, tmp_path)
    premiere = _envoyer(s, pid, data=b"VOIX-1").json()["voix"]["audio"]
    seconde = _envoyer(s, pid, data=b"VOIX-2").json()["voix"]["audio"]
    assert premiere != seconde
    assert repo.get(item_id=pid, language="bci")["meta"]["voix"]["audio"] == seconde


def test_la_voix_ne_touche_ni_le_texte_ni_le_statut(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    avant = repo.get(item_id=pid, language="bci")
    assert _envoyer(_speaker(monkeypatch, tmp_path), pid).status_code == 200
    apres = repo.get(item_id=pid, language="bci")
    assert "voix" in apres["meta"]
    assert (apres["status"], apres["text_local"], apres["text_fr"]) == (
        avant["status"], avant["text_local"], avant["text_fr"])
    assert {k: v for k, v in apres["meta"].items() if k != "voix"} == avant["meta"]


# ---------- refus : aucun fichier ecrit ----------

def test_refusee_hors_des_paires_sans_fichier_ecrit(seeded, monkeypatch, tmp_path):
    ingest([_MOT, _CONTENU], language="bci", actor="loc")
    s = _speaker(monkeypatch, tmp_path)
    for texte in ("kakao", "contenu"):
        r = _envoyer(s, _id(texte))
        assert (r.status_code, r.json()["detail"]) == (400, "type_sans_voix")
    assert _audios(tmp_path) == []


def test_refusee_sur_une_fiche_publiee(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    repo.set_status(item_id=pid, language="bci", status="production")
    r = _envoyer(_speaker(monkeypatch, tmp_path), pid)
    assert (r.status_code, r.json()["detail"]) == (400, "locked")
    assert _audios(tmp_path) == []


def test_introuvable_et_autre_langue(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="dyu", actor="loc")  # meme texte, autre langue
    s = _speaker(monkeypatch, tmp_path)  # session bci
    for item_id in (_id("Blɛ benin ?", language="dyu"), "999999"):
        r = _envoyer(s, item_id)
        assert (r.status_code, r.json()["detail"]) == (404, "not_found")  # la route, pas FastAPI
    assert _audios(tmp_path) == []


def test_le_depot_filtre_lui_meme_par_langue_et_par_type(seeded):
    # Derniere defense, independante du service : l'UPDATE ne touche jamais une fiche
    # d'une autre langue, ni un type sans voix, meme si un appelant oublie de verifier.
    ingest([_PAIRE], language="dyu", actor="loc")
    ingest([_MOT], language="bci", actor="loc")
    pid_dyu, mid = _id("Blɛ benin ?", language="dyu"), _id("kakao")
    tous = {"bronze", "admin_accepted"}
    assert repo.set_voix(item_id=pid_dyu, language="bci", kind="paire_qr",
                         audio_url="audio/x.webm", allowed_from=tous) is None
    assert "voix" not in repo.get(item_id=pid_dyu, language="dyu")["meta"]
    assert repo.set_voix(item_id=mid, language="bci", kind="mot_cle",
                         audio_url="audio/x.webm", allowed_from=tous) is None
    assert repo.set_voix(item_id=mid, language="bci", kind="paire_qr",  # type annonce faux
                         audio_url="audio/x.webm", allowed_from=tous) is None
    assert "voix" not in repo.get(item_id=mid, language="bci")["meta"]


def test_controles_audio_de_la_dictee(seeded, monkeypatch, tmp_path):
    ingest([_PAIRE], language="bci", actor="loc")
    pid = _id("Blɛ benin ?")
    s = _speaker(monkeypatch, tmp_path)
    assert _envoyer(s, pid, mime="text/plain", nom="x.txt").json()["detail"] == "format_audio_non_supporte"
    assert _envoyer(s, pid, data=b"").json()["detail"] == "audio_vide"
    monkeypatch.setattr("app.services.audio_upload.MAX_AUDIO", 3)
    assert _envoyer(s, pid, data=b"VOIX").json()["detail"] == "audio_trop_grand"
    assert _audios(tmp_path) == []
    # le type peut porter des parametres (navigateur : « audio/webm;codecs=opus »)
    assert _envoyer(s, pid, data=b"ok", mime="audio/webm;codecs=opus").status_code == 200
