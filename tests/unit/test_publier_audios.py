"""Publication des audios vers le serveur voix (ADR-0049, option B).

Le test qui compte vraiment est `test_le_nom_publie_est_celui_que_le_handler_demande` :
il attache les deux bouts. Publier sous un autre nom reviendrait à copier des fichiers
que personne ne lira — exactement la panne silencieuse que ce script existe pour éviter.
"""
import json
import shutil
import subprocess

import pytest

from scripts import publier_audios as pub

CORPUS = {
    "version": "bci-test",
    "statut": "valide",
    "entries": [
        {"id": "bci-q0", "audio_reponse": "audio/aaa111.webm"},
        {"id": "bci-q1", "audio_reponse": "audio/bbb222.webm"},
        # Réponse corrigée par le locuteur : servie en texte, audio à réenregistrer.
        {"id": "bci-q2", "audio_reponse": None, "audio_a_reenregistrer": True},
    ],
}

MESSAGES = {"messages": {"_SYSTEME_REPLI": {"texte": "…", "audio": "audio/ccc333.webm"}}}


@pytest.fixture
def dicos(tmp_path):
    (tmp_path / "corpus_ivr_bci.json").write_text(
        json.dumps(CORPUS, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_refs_ignorent_les_entrees_sans_audio(dicos):
    refs = pub.refs_attendues("bci", dossier=dicos)
    assert [r for _, r in refs] == ["audio/aaa111.webm", "audio/bbb222.webm"]
    assert pub.sans_audio("bci", dossier=dicos) == ["bci-q2"]


def test_les_messages_systeme_s_ajoutent_quand_le_fichier_existe(dicos):
    assert len(pub.refs_attendues("bci", dossier=dicos)) == 2
    (dicos / "messages_systeme_bci.json").write_text(
        json.dumps(MESSAGES, ensure_ascii=False), encoding="utf-8"
    )
    refs = pub.refs_attendues("bci", dossier=dicos)
    assert ("_SYSTEME_REPLI", "audio/ccc333.webm") in refs
    assert len(refs) == 3


def test_langue_sans_fichier_versionne_ne_leve_pas(tmp_path):
    assert pub.refs_attendues("xxx", dossier=tmp_path) == []
    assert pub.sans_audio("xxx", dossier=tmp_path) == []


def test_le_nom_publie_est_celui_que_le_handler_demande(tmp_path):
    """Contrat entre ce script et `baoule_handler._audio_url`.

    Le handler sert `<base>/<stem>.ogg` à partir de `audio_reponse`. Si la destination
    portait un autre nom, les fichiers seraient copiés pour rien.
    """
    from pathlib import PurePosixPath

    ref = "audio/aaa111.webm"
    publie = pub.cible(ref, tmp_path).name
    demande = PurePosixPath(ref).stem + ".ogg"  # ce que fait le handler
    assert publie == demande == "aaa111.ogg"


def test_idempotence_seuls_les_manquants_sont_retenus(dicos, tmp_path):
    vers = tmp_path / "ogg"
    vers.mkdir()
    refs = pub.refs_attendues("bci", dossier=dicos)
    assert len(pub.a_publier(refs, vers)) == 2

    pub.cible("audio/aaa111.webm", vers).write_bytes(b"deja la")
    restant = pub.a_publier(refs, vers)
    assert [r for _, r in restant] == ["audio/bbb222.webm"]


def test_etat_compte_ce_qui_manque_et_ce_qui_est_muet(dicos, tmp_path):
    vers = tmp_path / "ogg"
    vers.mkdir()
    pub.cible("audio/aaa111.webm", vers).write_bytes(b"deja la")
    e = pub.etat("bci", vers, dossier=dicos)
    assert e["attendus"] == 2
    assert e["publies"] == 1
    assert e["manquants"] == 1
    assert e["sans_audio"] == 1


def test_verifier_n_ecrit_rien_et_ne_contacte_pas_l_atelier(dicos, tmp_path, monkeypatch, capsys):
    vers = tmp_path / "ogg"
    monkeypatch.setattr(pub, "connexion", lambda *a, **k: pytest.fail("atelier contacté"))
    code = pub.main(["bci", "--vers", str(vers), "--verifier",
                     "--dictionnaires", str(dicos)])
    assert code == 0
    assert not vers.exists()
    assert "à publier" in capsys.readouterr().out


def test_destination_a_jour_ne_contacte_pas_l_atelier(dicos, tmp_path, monkeypatch):
    vers = tmp_path / "ogg"
    vers.mkdir()
    for nom in ("aaa111.ogg", "bbb222.ogg"):
        (vers / nom).write_bytes(b"deja la")
    monkeypatch.setattr(pub, "connexion", lambda *a, **k: pytest.fail("atelier contacté"))
    assert pub.main(["bci", "--vers", str(vers), "--dictionnaires", str(dicos)]) == 0


def test_un_audio_disparu_de_l_atelier_est_signale(dicos, tmp_path, monkeypatch, capsys):
    """Un 404 ne doit pas passer sous silence : l'entrée sera servie sans voix."""
    vers = tmp_path / "ogg"
    monkeypatch.setenv("LQE_USER", "u")
    monkeypatch.setenv("LQE_PASSWORD", "x" * 12)
    monkeypatch.setattr(pub, "connexion", lambda *a, **k: object())
    monkeypatch.setattr(pub, "telecharger", lambda *a, **k: None)
    code = pub.main(["bci", "--vers", str(vers), "--atelier", "http://atelier",
                     "--dictionnaires", str(dicos)])
    sortie = capsys.readouterr().out
    assert code == 1, "un audio introuvable doit sortir en échec"
    assert "INTROUVABLES" in sortie and "bci-q0" in sortie


def test_identifiants_manquants_echouent_clairement(dicos, tmp_path, monkeypatch):
    monkeypatch.delenv("LQE_USER", raising=False)
    monkeypatch.delenv("LQE_PASSWORD", raising=False)
    with pytest.raises(pub.EchecPublication, match="identifiants"):
        pub.main(["bci", "--vers", str(tmp_path / "ogg"), "--atelier", "http://x",
                  "--dictionnaires", str(dicos)])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_un_webm_opus_est_remuxe_sans_reencodage(tmp_path):
    """L'atelier enregistre du WebM/Opus : le flux doit être recopié, pas ré-encodé."""
    source = tmp_path / "src.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-c:a", "libopus", str(source)],
        check=True, capture_output=True,
    )
    destination = tmp_path / "out.ogg"
    assert pub.convertir(source.read_bytes(), "audio/src.webm", destination) == "remux"
    assert destination.is_file() and destination.stat().st_size > 0
    # Un remux conserve le flux : la taille reste du même ordre que la source.
    assert destination.stat().st_size > source.stat().st_size * 0.8


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_un_wav_est_reencode_et_signale(tmp_path):
    """wav/mp3/m4a sont acceptés par l'atelier et ne contiennent pas d'Opus."""
    source = tmp_path / "src.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", str(source)],
        check=True, capture_output=True,
    )
    destination = tmp_path / "out.ogg"
    assert pub.convertir(source.read_bytes(), "audio/src.wav", destination) == "réencodage"
    assert destination.is_file() and destination.stat().st_size > 0
