"""Serveur voix baoulé (ADR-0045) sans GPU ni ffmpeg : pipeline et décodeur factices.

Vérifie le contrat utilisé par le serveur WhatsApp et l'API : clé obligatoire, refus des
audios vides ou illisibles, texte renvoyé, erreur du modèle sans 500, enregistrements
servis sans qu'on puisse sortir du dossier.
"""
from pathlib import Path

from fastapi.testclient import TestClient

import serveur_voix_bci as voix


class FakePipeline:
    def __init__(self, sortie=" Blɛ benin yɛ be lua kakao ", erreur=None):
        self.sortie, self.erreur, self.appels = sortie, erreur, []

    def transcribe(self, paths, lang, batch_size):
        assert lang == ["bci_Latn"] and batch_size == 1 and len(paths) == 1
        self.appels.append(paths[0])
        if self.erreur:
            raise self.erreur
        return [self.sortie]


def fake_decodeur(data, dossier):
    if data == b"illisible":
        raise ValueError("format inconnu")
    chemin = Path(dossier) / "vocal.wav"
    chemin.write_bytes(data)
    return str(chemin)


def _client(tmp_path, pipeline=None):
    app = voix.creer_app(pipeline=pipeline or FakePipeline(), decodeur=fake_decodeur,
                         cle="cle-test", dossier_audio=tmp_path)
    return TestClient(app)


def _post(c, data=b"ogg", cle="cle-test"):
    return c.post("/transcribe", files={"audio": ("vocal.ogg", data, "audio/ogg")}, headers={"X-Api-Key": cle})


def test_transcription_avec_cle(tmp_path):
    pipe = FakePipeline()
    r = _post(_client(tmp_path, pipe))
    assert r.status_code == 200 and r.json() == {"text": "Blɛ benin yɛ be lua kakao", "language": "bci"}
    assert pipe.appels and pipe.appels[0].endswith("vocal.wav")


def test_cle_refusee_audio_vide_ou_illisible(tmp_path):
    c = _client(tmp_path)
    assert _post(c, cle="mauvaise").status_code == 401
    assert _post(c, cle="").status_code == 401
    assert _post(c, data=b"").status_code == 422
    assert _post(c, data=b"illisible").status_code == 422


def test_erreur_du_modele_sans_500(tmp_path):
    r = _post(_client(tmp_path, FakePipeline(erreur=RuntimeError("trop long"))))
    assert r.status_code == 422 and "RuntimeError" in r.json()["detail"]


def test_audio_servi_sans_sortir_du_dossier(tmp_path):
    (tmp_path / "e10c94c3aa.ogg").write_bytes(b"OggS")
    c = _client(tmp_path)
    r = c.get("/audio/e10c94c3aa.ogg")
    assert r.status_code == 200 and r.content == b"OggS" and r.headers["content-type"] == "audio/ogg"
    assert c.get("/audio/absent.ogg").status_code == 404
    assert c.get("/audio/..%2F..%2Fsecret.ogg").status_code == 404
    assert c.get("/audio/x.webm").status_code == 404
    assert c.get("/health").json() == {"ok": True, "modele_charge": True, "reponses_audio": 1}


def test_app_sans_cle_refuse_tout(tmp_path):
    app = voix.creer_app(pipeline=FakePipeline(), decodeur=fake_decodeur, cle="", dossier_audio=tmp_path)
    assert _post(TestClient(app), cle="").status_code == 401


def test_notebook_runpod_embarque_les_modules_a_jour():
    """Le notebook RunPod recopie les modules (%%writefile) : copies identiques exigées."""
    import json

    here = Path(__file__).parent
    nb = json.loads((here / "colab" / "serveur_voix_baoule_runpod.ipynb").read_text(encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for name in ("dictee_to_parquet.py", "prepare_bci_dataset.py", "eval_bci_cer.py", "serveur_voix_bci.py"):
        marker = f"%%writefile {name}\n"
        embedded = [src[len(marker):] for src in cells if src.startswith(marker)]
        assert len(embedded) == 1, f"cellule {marker.strip()} introuvable"
        assert embedded[0] == (here / name).read_text(encoding="utf-8"), (
            f"Copie périmée de {name} : relancer `python finetune/colab/sync_smoke_test_notebook.py`."
        )
