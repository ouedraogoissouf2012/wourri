"""La garde de la base (#638) se prouve elle-même : chaque porte qu'elle prétend tenir a
ici son test, et chaque test fait tourner une VRAIE session pytest dans un sous-processus
(pas d'interférence avec la garde de la session qui les lance).

Aucune base n'est nécessaire : un refus doit survenir AVANT le réseau. Des sockets
d'écoute locales comptent les connexions qui l'atteignent — zéro pour un refus, une pour
un accès autorisé (sinon le compteur lui-même ne prouverait rien).
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


class _Ecoute:
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


def _session(tmp_path: Path, fichiers: dict[str, str], ecoutes: dict[str, _Ecoute]):
    """Lance pytest sur `fichiers`, garde chargée comme en CI. -> (code, sortie, issues)."""
    for nom, source in fichiers.items():
        (tmp_path / nom).write_text(textwrap.dedent(source), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        f"[pytest]\naddopts = -p garde_base -p no:cacheprovider\npythonpath = {GARDE.as_posix()}\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("POSTGRES", "PG", "LQE_DATABASE"))}
    env.update({f"PORT_{cle}": str(e.port) for cle, e in ecoutes.items()})
    rapport = tmp_path / "rapport.xml"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"--junitxml={rapport}"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=180,
    )
    return r.returncode, r.stdout + r.stderr, _issues(rapport)


def _issues(rapport: Path) -> dict[str, tuple[str, str]]:
    """{nom du test: (issue, texte du rapport)} depuis le JUnit XML."""
    if not rapport.exists():
        return {}
    issues = {}
    for cas in ET.parse(rapport).getroot().iter("testcase"):
        issue, texte = "passed", ""
        for balise in ("failure", "error", "skipped"):
            el = cas.find(balise)
            if el is not None:
                issue = {"failure": "failed", "error": "error", "skipped": "skipped"}[balise]
                texte = (el.get("message") or "") + "\n" + (el.text or "")
                break
        issues[cas.get("name")] = (issue, texte)
    return issues


@pytest.fixture
def ecoutes():
    actives: dict[str, _Ecoute] = {}

    def creer(*cles):
        for cle in cles:
            actives[cle] = _Ecoute()
        return actives

    yield creer
    for e in actives.values():
        e.fermer()


SCENARIOS = '''
import asyncio, os, subprocess, sys, threading
import psycopg, pytest

def dsn(cle, base):
    return f"host=127.0.0.1 port={os.environ['PORT_' + cle]} dbname={base} user=u password=p connect_timeout=2"

def test_temoin_sans_base():
    assert 1 + 1 == 2

def test_connect_non_declare():
    psycopg.connect(dsn("CONNECT", "x_test"))

def test_exception_avalee():
    try:
        psycopg.connect(dsn("AVALEE", "x_test"))
    except Exception:
        pass  # le repli silencieux : exactement ce que la garde doit voir quand même

def test_methode_de_classe():
    psycopg.Connection.connect(dsn("CLASSE", "x_test"))

def test_connexion_asynchrone():
    async def ouvrir():
        await psycopg.AsyncConnection.connect(dsn("ASYNC", "x_test"))
    try:
        asyncio.run(ouvrir())
    except Exception:
        pass

def test_sqlalchemy():
    from sqlalchemy import create_engine
    moteur = create_engine(f"postgresql+psycopg://u:p@127.0.0.1:{os.environ['PORT_SQLA']}/x_test")
    try:
        moteur.connect()
    except Exception:
        pass

CIBLES = [(c, m) for c in (psycopg.Cursor, psycopg.ServerCursor, psycopg.AsyncCursor, psycopg.AsyncServerCursor)
          for m in ("execute", "executemany", "copy", "stream") if m in c.__dict__]

@pytest.mark.parametrize("cls,methode", CIBLES, ids=[f"{c.__name__}.{m}" for c, m in CIBLES])
def test_requete_sur_connexion_deja_ouverte(cls, methode):
    # Le cas du pool : aucune connexion ouverte par ce test, seulement une requête.
    try:
        getattr(cls, methode)(object(), "SELECT 1")
    except Exception:
        pass

def test_fil_lance_par_le_test():
    def travail():
        try:
            psycopg.connect(dsn("FIL", "x_test"))
        except Exception:
            pass
    fil = threading.Thread(target=travail)
    fil.start()
    fil.join()

@pytest.fixture
def ferme_en_partant():
    yield
    psycopg.connect(dsn("TEARDOWN", "x_test"))

def test_connexion_au_demontage(ferme_en_partant):
    pass

@pytest.mark.base_de_donnees
def test_declare_sur_base_jetable():
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(dsn("JETABLE", "x_test"))

@pytest.mark.base_de_donnees
def test_declare_sur_base_de_dev():
    psycopg.connect(dsn("DEV", "wourri_dev"))

@pytest.mark.base_de_donnees
def test_declare_refus_avale_puis_saute():
    try:
        psycopg.connect(dsn("SAUTE", "wourri_dev"))
    except Exception:
        pytest.skip("base indisponible")  # comme postgres_reachable : un saut ne couvre pas un refus

@pytest.mark.base_de_donnees
def test_sous_processus_vers_base_de_dev():
    url = "postgresql+psycopg://u:p@127.0.0.1:1/wourri_dev"
    subprocess.run([sys.executable, "-c", "pass"], env={**os.environ, "POSTGRES_URL": url}, check=True)

@pytest.mark.base_de_donnees
def test_sous_processus_composants_de_dev():
    subprocess.run([sys.executable, "-c", "pass"], env={**os.environ, "POSTGRES_DB": "wourri_dev"}, check=True)

@pytest.mark.base_de_donnees
def test_sous_processus_vers_base_jetable():
    url = "postgresql+psycopg://u:p@127.0.0.1:1/x_test"
    subprocess.run([sys.executable, "-c", "pass"], env={**os.environ, "POSTGRES_URL": url}, check=True)
'''

REFUSES_SANS_RESEAU = ("CONNECT", "AVALEE", "CLASSE", "ASYNC", "SQLA", "FIL", "TEARDOWN", "DEV", "SAUTE")


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory):
    """Une seule session pour tous les scénarios de test : ~1 s au lieu d'une par cas."""
    ecoute = {cle: _Ecoute() for cle in (*REFUSES_SANS_RESEAU, "JETABLE")}
    try:
        code, sortie, issues = _session(tmp_path_factory.mktemp("garde"),
                                        {"test_scenarios.py": SCENARIOS}, ecoute)
    finally:
        for e in ecoute.values():
            e.fermer()
    return code, sortie, issues, {cle: e.acceptees for cle, e in ecoute.items()}


def test_un_test_sain_n_est_pas_gene(scenarios):
    code, sortie, issues, _ = scenarios
    assert issues["test_temoin_sans_base"][0] == "passed", sortie
    assert code != 0  # la session, elle, échoue : elle contient des fautifs


@pytest.mark.parametrize("nom", [
    "test_connect_non_declare",
    "test_exception_avalee",
    "test_methode_de_classe",
    "test_connexion_asynchrone",
    "test_sqlalchemy",
    "test_fil_lance_par_le_test",
    "test_connexion_au_demontage",
])
def test_un_test_non_declare_qui_atteint_la_base_echoue_et_est_nomme(scenarios, nom):
    _, sortie, issues, _ = scenarios
    issue, texte = issues[nom]
    assert issue in ("failed", "error"), f"{nom} : {issue}\n{sortie}"
    assert NON_DECLARE in texte and nom in texte, texte


def test_une_requete_sur_une_connexion_du_pool_est_refusee(scenarios):
    """La mesure de #638 : 3 des 4 tests fautifs n'ouvraient AUCUNE connexion, ils
    réutilisaient celle du pool. Une garde posée sur `connect` seul les laissait passer."""
    _, sortie, issues, _ = scenarios
    cas = {n: v for n, v in issues.items() if n.startswith("test_requete_sur_connexion_deja_ouverte")}
    assert len(cas) >= 12, sorted(cas)  # execute/executemany/copy/stream × 4 classes (servers : 2)
    for nom, (issue, texte) in cas.items():
        assert issue == "failed" and NON_DECLARE in texte, f"{nom} : {issue}\n{texte}"


def test_aucun_refus_n_atteint_le_reseau(scenarios):
    _, sortie, _, acceptees = scenarios
    # Un zéro ne prouve rien si rien n'a tourné : dans la MÊME session, l'accès autorisé
    # a bien été compté. Sans cette ligne, ce test passe garde absente.
    assert acceptees["JETABLE"] == 1, sortie
    assert {c: acceptees[c] for c in REFUSES_SANS_RESEAU} == dict.fromkeys(REFUSES_SANS_RESEAU, 0), sortie


def test_un_test_declare_atteint_une_base_jetable(scenarios):
    _, sortie, issues, acceptees = scenarios
    assert issues["test_declare_sur_base_jetable"][0] == "passed", sortie
    assert acceptees["JETABLE"] == 1  # le compteur sait compter : les zéros ci-dessus prouvent


@pytest.mark.parametrize("nom", ["test_declare_sur_base_de_dev", "test_declare_refus_avale_puis_saute"])
def test_un_test_declare_ne_peut_pas_toucher_une_base_non_jetable(scenarios, nom):
    _, sortie, issues, _ = scenarios
    issue, texte = issues[nom]
    assert issue == "failed", f"{nom} : {issue}\n{sortie}"
    assert NON_JETABLE in texte, texte


@pytest.mark.parametrize("nom", ["test_sous_processus_vers_base_de_dev", "test_sous_processus_composants_de_dev"])
def test_un_sous_processus_vers_une_base_non_jetable_est_refuse(scenarios, nom):
    _, sortie, issues, _ = scenarios
    issue, texte = issues[nom]
    assert issue == "failed" and NON_JETABLE in texte, f"{nom} : {issue}\n{texte}"


def test_un_sous_processus_vers_une_base_jetable_est_autorise(scenarios):
    _, sortie, issues, _ = scenarios
    assert issues["test_sous_processus_vers_base_jetable"][0] == "passed", sortie


def test_une_connexion_a_l_import_est_une_erreur_de_collecte(tmp_path, ecoutes):
    """Le cas le plus sournois : un module qui se connecte à l'import, hors de tout test,
    et avale l'erreur — comme le faisaient les `skipif` de module avec postgres_reachable."""
    e = ecoutes("IMPORT")
    code, sortie, _ = _session(tmp_path, {
        "test_a_l_import.py": '''
            import os, psycopg
            try:
                psycopg.connect(f"host=127.0.0.1 port={os.environ['PORT_IMPORT']} dbname=x_test user=u connect_timeout=2")
            except Exception:
                pass
            def test_rien():
                pass
        ''',
        "test_voisin.py": "def test_voisin():\n    pass\n",
    }, e)
    assert code != 0, sortie
    assert "test_a_l_import.py" in sortie and "pendant la collecte" in sortie, sortie
    assert e["IMPORT"].acceptees == 0


def test_une_connexion_hors_de_tout_test_fait_echouer_la_session(tmp_path, ecoutes):
    e = ecoutes("HORS")
    code, sortie, issues = _session(tmp_path, {
        "conftest.py": '''
            import os, psycopg
            def pytest_sessionstart(session):
                try:
                    psycopg.connect(f"host=127.0.0.1 port={os.environ['PORT_HORS']} dbname=x_test user=u connect_timeout=2")
                except Exception:
                    pass
        ''',
        "test_sain.py": "def test_sain():\n    pass\n",
    }, e)
    assert issues["test_sain"][0] == "passed", sortie
    assert code != 0 and "hors de tout test" in sortie, sortie
    assert e["HORS"].acceptees == 0
