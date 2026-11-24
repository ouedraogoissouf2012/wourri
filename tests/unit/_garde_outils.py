"""Outils des tests de la garde de la base (#638) : une VRAIE session pytest en
sous-processus, garde chargée, et de faux serveurs qui comptent les connexions reçues.

Aucune base n'est nécessaire : un refus doit survenir AVANT le réseau — zéro connexion
reçue pour un refus, une pour un accès autorisé (sinon le compteur ne prouverait rien).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

GARDE = Path(__file__).resolve().parents[2] / "tools" / "pytest"
NON_DECLARE = "sans le déclarer"
NON_JETABLE = "base non jetable : wourri_dev (attendu : un nom finissant par `_test`)"


class Ecoute:
    """Un faux serveur : accepte, compte, raccroche."""

    def __init__(self):
        self._s = socket.create_server(("127.0.0.1", 0))
        self._s.settimeout(0.1)
        self.port = self._s.getsockname()[1]
        self.acceptees = 0
        self._fin = threading.Event()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def _boucle(self):
        while not self._fin.is_set():
            try:
                conn, _ = self._s.accept()
            except OSError:
                continue
            self.acceptees += 1
            conn.close()

    def fermer(self):
        self._fin.set()
        self._fil.join()
        self._s.close()


def lancer_session(tmp_path: Path, fichiers: dict[str, str], ecoutes: dict[str, Ecoute],
                   *args: str):
    """Lance pytest sur `fichiers`, garde chargée comme en CI. -> (code, sortie, issues).

    `tmp_path` est sur le PYTHONPATH : un fichier qui y est écrit peut être chargé comme
    greffon (`-p nom`), là où un conftest ne verrait pas les appels faits par la Session."""
    for nom, source in fichiers.items():
        cible = tmp_path / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(textwrap.dedent(source), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = -p garde_base -p no:cacheprovider\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("POSTGRES", "PG", "LQE_DATABASE"))}
    # PYTHONPATH et non `pythonpath` du pytest.ini : ce dernier s'applique APRÈS l'import des
    # greffons `-p`. Ces sessions éprouvent la garde ; son câblage réel a son propre test.
    env["PYTHONPATH"] = os.pathsep.join((str(GARDE), str(tmp_path)))
    env.update({f"PORT_{cle}": str(e.port) for cle, e in ecoutes.items()})
    rapport = tmp_path / "rapport.xml"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"--junitxml={rapport}", *args],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=180,
    )
    return r.returncode, r.stdout + r.stderr, issues(rapport)


def issues(rapport: Path) -> dict[str, tuple[str, str]]:
    """{nom du test: (issue, texte du rapport)} depuis le JUnit XML."""
    if not rapport.exists():
        return {}
    resultat = {}
    for cas in ET.parse(rapport).getroot().iter("testcase"):
        issue, texte = "passed", ""
        for balise in ("failure", "error", "skipped"):
            el = cas.find(balise)
            if el is not None:
                issue = {"failure": "failed", "error": "error", "skipped": "skipped"}[balise]
                texte = (el.get("message") or "") + "\n" + (el.text or "")
                break
        resultat[cas.get("name")] = (issue, texte)
    return resultat


@pytest.fixture
def ecoutes():
    actives: dict[str, Ecoute] = {}

    def creer(*cles):
        for cle in cles:
            actives[cle] = Ecoute()
        return actives

    yield creer
    for e in actives.values():
        e.fermer()
