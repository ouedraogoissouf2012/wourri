"""Tests du decoupage SQL conscient des litteraux (issue #493).

Tests purs (aucune base) : ils fixent le contrat du garde-fou du runner de migrations.
"""
import pytest

from app.services.migrate import MIGRATIONS_DIR
from app.services.sql_script import SqlScriptError, split_statements


def test_decoupe_les_statements_et_retire_les_separateurs():
    sql = "CREATE TABLE a (x int);\nCREATE TABLE b (y int);\n"
    assert split_statements(sql, origin="t.sql") == [
        "CREATE TABLE a (x int)",
        "CREATE TABLE b (y int)",
    ]


def test_dernier_statement_sans_point_virgule_final():
    assert split_statements("SELECT 1", origin="t.sql") == ["SELECT 1"]


def test_commentaire_en_fin_de_ligne_est_retire():
    # L'ancien filtre ne retirait que les lignes COMMENCANT par '--' : le ';' de ce
    # commentaire coupait le statement suivant en deux (issue #493).
    sql = "CREATE TABLE t (a int);  -- colonne a ; pas un separateur\nCREATE TABLE u (b int);"
    assert split_statements(sql, origin="t.sql") == [
        "CREATE TABLE t (a int)",
        "CREATE TABLE u (b int)",
    ]


def test_ligne_entiere_de_commentaire_est_retiree():
    assert split_statements("-- entete ; ici\nSELECT 1;", origin="t.sql") == ["SELECT 1"]


def test_semicolon_dans_une_chaine_est_refuse():
    sql = "INSERT INTO t (message)\nVALUES ('bonjour ; salut');\n"
    with pytest.raises(SqlScriptError) as excinfo:
        split_statements(sql, origin="005_seed.sql")
    message = str(excinfo.value)
    assert message.startswith("005_seed.sql:2")  # nomme le fichier ET la ligne fautive
    assert "';'" in message


def test_quote_doublee_ne_ferme_pas_la_chaine():
    # 'c''est ; ici' est UN litteral : le ';' y reste, donc refus (jamais un decoupage)
    with pytest.raises(SqlScriptError):
        split_statements("INSERT INTO t VALUES ('c''est ; ici');", origin="t.sql")


def test_quote_doublee_conservee_dans_le_statement():
    assert split_statements("INSERT INTO t VALUES ('c''est ici');", origin="t.sql") == [
        "INSERT INTO t VALUES ('c''est ici')"
    ]


def test_chaine_e_le_backslash_echappe_le_quote():
    # Sans la regle E'...', le quote echappe fermerait la chaine et le ';' suivant
    # serait pris pour un separateur : decoupage silencieux, exactement le defaut #493.
    with pytest.raises(SqlScriptError):
        split_statements(r"INSERT INTO t VALUES (E'a\'b ; c');", origin="t.sql")


def test_dollar_quote_avec_semicolon_est_refuse():
    sql = (
        "CREATE FUNCTION f() RETURNS int AS $body$\n"
        "BEGIN\n"
        "  RETURN 1;\n"
        "END\n"
        "$body$ LANGUAGE plpgsql;\n"
    )
    with pytest.raises(SqlScriptError) as excinfo:
        split_statements(sql, origin="006_fonction.sql")
    assert str(excinfo.value).startswith("006_fonction.sql:3")


def test_dollar_double_avec_semicolon_est_refuse():
    with pytest.raises(SqlScriptError):
        split_statements("DO $$ BEGIN PERFORM 1; END $$;", origin="t.sql")


def test_dollar_placeholder_nest_pas_un_litteral():
    # `$1` n'ouvre pas un litteral dollar : le decoupage reste normal
    assert split_statements("SELECT $1;\nSELECT 2;", origin="t.sql") == ["SELECT $1", "SELECT 2"]


def test_commentaire_bloc_imbrique_est_retire():
    sql = "SELECT 1 /* note /* imbriquee ; ici */ fin */;\nSELECT 2;"
    assert split_statements(sql, origin="t.sql") == ["SELECT 1", "SELECT 2"]


def test_identifiant_quote_avec_semicolon_est_refuse():
    with pytest.raises(SqlScriptError):
        split_statements('CREATE TABLE "a;b" (x int);', origin="t.sql")


def test_chaine_non_fermee_est_refusee():
    with pytest.raises(SqlScriptError) as excinfo:
        split_statements("SELECT 'oups\n", origin="t.sql")
    assert "non ferme" in str(excinfo.value)


def test_commentaire_bloc_non_ferme_est_refuse():
    with pytest.raises(SqlScriptError) as excinfo:
        split_statements("SELECT 1 /* oups\n", origin="t.sql")
    assert "non ferme" in str(excinfo.value)


def test_les_migrations_du_depot_passent_le_garde_fou():
    fichiers = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert fichiers, "aucune migration trouvee"
    for path in fichiers:
        statements = split_statements(path.read_text(encoding="utf-8"), origin=path.name)
        assert statements, f"{path.name} : aucun statement"
        for statement in statements:
            assert ";" not in statement
            assert "--" not in statement  # commentaires retires, ou qu'ils soient
