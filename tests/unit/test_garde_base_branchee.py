"""La garde de la base (#638) est-elle BRANCHÉE dans cette session-ci ?

`test_garde_base.py` prouve que la garde fonctionne, dans des sessions où elle est chargée
explicitement. Rien n'y échouerait si la suite réelle tournait sans elle : `addopts` mal
écrit, `pythonpath` cassé, `-p no:garde_base` dans une commande. Ce test-ci, lui, échoue
quand le câblage casse sans que le code de la garde change — la panne la plus probable,
parce qu'elle ne ressemble pas à une panne.
"""
import psycopg


def test_la_garde_est_branchee_dans_cette_session(request):
    assert request.config.pluginmanager.has_plugin("garde_base"), (
        "garde_base absente de la session : voir addopts et pythonpath dans pytest.ini"
    )
    assert hasattr(psycopg.Cursor.execute, "__garde__"), "garde chargée mais psycopg non surveillé"
