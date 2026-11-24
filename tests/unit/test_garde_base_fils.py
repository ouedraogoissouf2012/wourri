"""La garde de la base (#649) face aux FILS : un refus est imputé à la zone où il a été
DÉCIDÉ, jamais à celle où il finit d'être enregistré.

Mesuré dans l'atelier (passe 26 sur 30) : un fil du pool décide un refus pendant un test
non déclaré ; la construction du message (`_origine()`, ~70 ms sur un poste chargé) laisse
le test suivant commencer ; l'enregistrement relisait la zone globale et accusait ce test
suivant — DÉCLARÉ, donc innocent. Ici la course est rendue déterministe : `_origine()`
attend que le test suivant ait commencé.
"""
from __future__ import annotations

from tests.unit._garde_outils import ecoutes, lancer_session  # noqa: F401

CONFTEST = '''
import threading
import garde_base

reprendre = threading.Event()
_vraie_origine = garde_base._origine

def _origine_lente():
    reprendre.wait(10)  # la décision est prise ; on laisse le test suivant commencer
    return _vraie_origine()

garde_base._origine = _origine_lente
'''

TESTS = '''
import threading
import conftest
import psycopg
import pytest

fils = []

def test_a_lance_un_fil_qui_survit():
    def acces():
        try:
            psycopg.Cursor.execute(object(), "SELECT 1")
        except Exception:
            pass
    fil = threading.Thread(target=acces, name="fil-qui-survit")
    fil.start()
    fils.append(fil)

@pytest.mark.base_de_donnees
def test_b_declare_et_innocent():
    conftest.reprendre.set()  # le refus de A s'enregistre PENDANT B
    fils[0].join(10)
'''


def test_un_refus_est_impute_a_la_zone_ou_il_a_ete_decide(tmp_path, ecoutes):
    code, sortie, issues = lancer_session(tmp_path, {"conftest.py": CONFTEST, "test_course.py": TESTS}, ecoutes())
    # B avait le droit de toucher la base : il ne doit jamais être accusé du refus de A.
    assert issues["test_b_declare_et_innocent"][0] == "passed", sortie
    # A s'est terminé avant que son refus soit enregistré : le filet de fin de session le
    # ramasse, sous SON nom — la session échoue, et le coupable est le bon.
    assert code != 0, sortie
    assert "test_course.py::test_a_lance_un_fil_qui_survit a atteint PostgreSQL sans le déclarer" in sortie, sortie
