"""Garde des fichiers de validations téléchargés de l'atelier (#637).

Pourquoi ces tests existent. Les validations du locuteur arrivent par un fichier
téléchargé de `/tasks/validations`. Un corps d'erreur enregistré à sa place
(`{"detail": "language_required"}`, un `curl -s` sans `-f`) était lu comme « aucune
entrée » : le build tournait à vide, sans un mot, et l'on concluait que le locuteur
n'avait rien produit. Un export d'une autre langue passait de même, et polluait le NLU
baoulé. Une seule fonction contrôle le fichier ; les trois points de lecture l'appellent.

Limite déclarée : un export PÉRIMÉ est un export valide (bonne langue, bon type,
`entries` présent) — aucune garde lisant le fichier ne peut le distinguer (#642).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import baoule_nlu_build as build
from scripts import baoule_sources as src
from scripts.validations_atelier import ValidationsInvalides, charger_validations

ROOT = Path(__file__).resolve().parents[2]
_REFUS = {"detail": "language_required"}  # ce que l'atelier répond à un admin sans langue


def _export(kind: str, language: str = "bci", entries=None) -> dict:
    """La forme réelle de la réponse de /tasks/validations."""
    entries = entries if entries is not None else [
        {"status": "admin_accepted", "text_local": "zuka", "text_fr": "zorbe", "meta": {}}]
    return {"language": language, "kind": kind, "entries": entries, "count": len(entries)}


def _ecrire(tmp_path: Path, nom: str, contenu) -> Path:
    p = tmp_path / nom
    p.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu), encoding="utf-8")
    return p


# ------------------------------------------------------------------ la fonction


def test_un_export_valide_est_rendu_tel_quel(tmp_path):
    export = _export("paire_qr")
    assert charger_validations(_ecrire(tmp_path, "p.json", export), kind="paire_qr", langue="bci") == export


def test_un_corps_d_erreur_est_refuse_en_citant_le_serveur_sans_deviner(tmp_path):
    chemin = _ecrire(tmp_path, "paires_bci.json", _REFUS)
    with pytest.raises(ValidationsInvalides) as exc:
        charger_validations(chemin, kind="paire_qr", langue="bci")
    msg = str(exc.value)
    assert str(chemin) in msg
    assert "kind=paire_qr" in msg and "language=bci" in msg  # ce qui était attendu
    assert '{"detail": "language_required"}' in msg          # ce qui a été trouvé, cité
    assert "retélécharger" in msg                             # la seule remédiation sûre
    # Le message rapporte, il ne diagnostique pas : aucune cause supposée.
    assert "admin" not in msg.lower() and "compte" not in msg.lower()


def test_un_export_d_une_autre_langue_est_refuse(tmp_path):
    with pytest.raises(ValidationsInvalides, match='language = "dyu"'):
        charger_validations(_ecrire(tmp_path, "p.json", _export("paire_qr", "dyu")),
                            kind="paire_qr", langue="bci")


def test_un_export_d_un_autre_type_est_refuse(tmp_path):
    with pytest.raises(ValidationsInvalides, match='kind = "mot_cle"'):
        charger_validations(_ecrire(tmp_path, "p.json", _export("mot_cle")), kind="paire_qr", langue="bci")


@pytest.mark.parametrize("contenu", ["", "pas du json", json.dumps([{"status": "admin_accepted"}]),
                                     json.dumps({"language": "bci", "kind": "paire_qr", "entries": {}})])
def test_un_fichier_illisible_ou_d_une_autre_forme_est_refuse(tmp_path, contenu):
    with pytest.raises(ValidationsInvalides, match="retélécharger"):
        charger_validations(_ecrire(tmp_path, "p.json", contenu), kind="paire_qr", langue="bci")


def test_un_fichier_absent_est_refuse_avec_un_message(tmp_path):
    with pytest.raises(ValidationsInvalides, match="absent"):
        charger_validations(tmp_path / "jamais_telecharge.json", kind="paire_qr", langue="bci")


# ------------------------------------------------------------------ les trois points de lecture
#
# Chaque test passe par l'entrée publique : retirer l'appel à la garde dans l'un des trois
# lecteurs doit faire échouer le sien.


def test_le_build_refuse_des_paires_invalides_avant_tout_calcul(tmp_path):
    mots = _ecrire(tmp_path, "mots.json", _export("mot_cle"))
    paires = _ecrire(tmp_path, "paires.json", _REFUS)
    with pytest.raises(ValidationsInvalides, match=str(paires).replace("\\", "\\\\")):
        build.main([str(tmp_path / "export_absent.zip"), "--mots-cles", str(mots), "--paires", str(paires)])


def test_le_build_refuse_des_mots_cles_invalides_avant_tout_calcul(tmp_path):
    mots = _ecrire(tmp_path, "mots.json", _export("mot_cle", "dyu"))
    paires = _ecrire(tmp_path, "paires.json", _export("paire_qr"))
    with pytest.raises(ValidationsInvalides, match=str(mots).replace("\\", "\\\\")):
        build.main([str(tmp_path / "export_absent.zip"), "--mots-cles", str(mots), "--paires", str(paires)])


def test_la_source_locuteur_refuse_un_corps_d_erreur_des_l_appel(tmp_path):
    """Dès l'appel, pas à la première lecture : `baoule_validation_mots` arrête alors la
    validation sur ce message, au lieu d'une AttributeError sur un dict d'erreur."""
    with pytest.raises(ValidationsInvalides, match="language_required"):
        src.validations_locuteur(_ecrire(tmp_path, "mots.json", _REFUS))


def test_la_source_locuteur_refuse_un_export_de_paires(tmp_path):
    with pytest.raises(ValidationsInvalides, match='kind = "paire_qr"'):
        src.validations_locuteur(_ecrire(tmp_path, "mots.json", _export("paire_qr")))


# ------------------------------------------------------------------ à l'écran


def test_le_refus_remonte_lisiblement_a_l_ecran(tmp_path):
    """Ce que voit l'opérateur : un message et un code d'échec, jamais « 0 contenu »."""
    mots = _ecrire(tmp_path, "mots.json", _export("mot_cle"))
    paires = _ecrire(tmp_path, "paires.json", _REFUS)
    r = subprocess.run(
        [sys.executable, "scripts/baoule_nlu_build.py", str(tmp_path / "export_absent.zip"),
         "--mots-cles", str(mots), "--paires", str(paires)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120,
    )
    assert r.returncode == 2
    assert "ÉCHEC" in r.stderr and "language_required" in r.stderr
    assert "Traceback" not in r.stderr
    assert "servies" not in r.stdout  # le build n'a rien produit
