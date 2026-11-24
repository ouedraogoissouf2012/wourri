"""La garde de la base (#638) pendant la COLLECTE : zone sans droit, et le coupable est
nommé — y compris quand les collectes s'imbriquent.

Elles s'imbriquent (mesuré) : la Session collecte en elle-même les dossiers et paquets qui
mènent aux chemins passés en argument (`Dir '.'`, `Package 'tests'`…). Un accès dans la
Session APRÈS un enfant doit être imputé à la Session, pas à « hors de tout test » ; un
accès AVANT doit faire échouer la collecte, pas seulement la fin de session.
"""
from __future__ import annotations

from tests.unit._garde_outils import ecoutes, lancer_session  # noqa: F401

CONNEXION = '''
import os, psycopg

def connecter(cle):
    try:
        psycopg.connect(f"host=127.0.0.1 port={os.environ['PORT_' + cle]} dbname=x_test user=u connect_timeout=2")
    except Exception:
        pass  # avalé : la garde doit le voir quand même
'''

# Le test qu'une collecte fautive ne doit JAMAIS laisser tourner.
SOUS_TEST = {"sous/test_x.py": "def test_x():\n    pass\n"}


def test_une_connexion_a_l_import_est_une_erreur_de_collecte(tmp_path, ecoutes):
    """Le cas le plus sournois : un module qui se connecte à l'import, hors de tout test,
    et avale l'erreur — comme le faisaient les `skipif` de module avec postgres_reachable."""
    e = ecoutes("IMPORT")
    code, sortie, _ = lancer_session(tmp_path, {
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
    assert "pendant la collecte" in sortie, sortie
    # Une ERREUR DE COLLECTE, pas un échec de fin de session : le module fautif est nommé
    # comme tel et rien ne tourne (le filet de fin de session aurait laissé passer ses tests).
    assert "ERROR test_a_l_import.py" in sortie and "error during collection" in sortie, sortie
    assert e["IMPORT"].acceptees == 0


def test_un_acces_dans_la_session_apres_un_enfant_est_impute_a_la_session(tmp_path, ecoutes):
    """Tracé : la Session collecte `Dir '.'` puis `Dir 'sous'`, chacun imbriqué. Entre les
    deux, `pytest_collectstart(Dir 'sous')` tourne DANS la Session, APRÈS un enfant. La zone
    doit y être celle de la Session — pas « hors de tout test », ce qu'elle devenait quand
    la sortie d'un enfant l'écrasait."""
    e = ecoutes("APRES")
    code, sortie, issues = lancer_session(tmp_path, {**SOUS_TEST, "sonde_apres.py": CONNEXION + '''
def pytest_collectstart(collector):
    if collector.nodeid == "sous":  # le 2e enfant : le 1er (Dir '.') est déjà sorti
        connecter("APRES")
'''}, e, "-p", "sonde_apres", "sous/test_x.py")
    assert code != 0 and "error during collection" in sortie, sortie
    assert "pendant la collecte" in sortie and "<session>" in sortie, sortie
    assert "hors de tout test" not in sortie, sortie  # la mauvaise étiquette
    assert "test_x" not in issues, sortie
    assert e["APRES"].acceptees == 0


def test_un_acces_dans_la_session_avant_un_enfant_fait_echouer_la_collecte(tmp_path, ecoutes):
    """`pytest_collect_directory(parent=Session)` tourne DANS la collecte de la Session,
    AVANT tout enfant. Le refus doit faire échouer cette collecte — il n'était imputé
    qu'au filet de fin de session, et les tests tournaient quand même."""
    e = ecoutes("AVANT")
    code, sortie, issues = lancer_session(tmp_path, {**SOUS_TEST, "sonde_avant.py": CONNEXION + '''
import pytest

def pytest_collect_directory(path, parent):
    if isinstance(parent, pytest.Session):
        connecter("AVANT")
'''}, e, "-p", "sonde_avant", "sous/test_x.py")
    assert code != 0 and "error during collection" in sortie, sortie
    assert "pendant la collecte" in sortie and "<session>" in sortie, sortie
    assert "test_x" not in issues, sortie  # rien ne tourne après une collecte fautive
    assert e["AVANT"].acceptees == 0
