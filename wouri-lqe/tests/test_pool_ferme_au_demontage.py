"""#649 : aucun fil du pool ne survit au test qui l'a ouvert.

Mesuré (5 passes sur 30 de test_startup.py) : pendant un test déclaré, `getconn` attend,
le pool « grandit » d'une connexion ; son `_configure` (`app/db.py`, SET search_path,
fil `lqe-worker-N`) tombait 0,13 ms après le début du test SUIVANT — que la garde de la
base accusait alors d'un accès qu'il n'avait pas fait. Le pool est désormais fermé au
démontage (fixture autouse de `conftest.py`) : la tentative en vol se termine pendant le
test qui l'a provoquée, et plus aucun fil n'existe pour accuser qui que ce soit.

Les deux tests sont liés par l'ordre du fichier : le premier ouvre le pool, le second
constate qu'il n'en reste rien.
"""
import threading

import app.db as app_db


def test_1_un_test_declare_ouvre_le_pool(db):
    from app.db import get_conn

    with get_conn() as conn:
        conn.execute("SELECT 1")


def test_2_aucun_fil_du_pool_ne_survit_au_test_precedent():
    vivants = [t.name for t in threading.enumerate() if t.name.startswith("lqe-worker")]
    assert vivants == [], f"fils du pool encore vivants : {vivants}"
    assert app_db._pool is None, "le pool du test précédent est encore ouvert"
