"""Tests du comptage des lignes logiques (scripts/logical_lines.py) — ADR-0051 §6.1, issue #621.

Une ligne logique est une ligne physique qui porte du code : ni commentaire, ni
ligne vide, ni chaîne de documentation. Ces tests fixent la règle langage par
langage, en particulier les pièges où un comptage naïf se trompe :
  - Python : une requête SQL en triple guillemets est du code, pas une docstring
    (c'est l'erreur qui faisait mesurer corpus_service.py à 327 au lieu de 364) ;
  - JavaScript : un `//` ou un `/*` dans une chaîne, un gabarit ou une regex
    n'ouvre pas de commentaire ;
  - Vue : chaque bloc a sa propre syntaxe de commentaire.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Le module vit dans scripts/ (hors package), comme prevalidation_rules.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from logical_lines import (  # noqa: E402
    LogicalLineError,
    count_logical_lines,
    javascript_logical_lines,
    python_logical_lines,
    vue_logical_lines,
)


# ─────────────────────────────────────────────
# Python
# ─────────────────────────────────────────────


class TestPython:
    def test_lignes_vides_et_commentaires_exclus(self):
        source = "# en-tete\n\nx = 1  # commentaire en fin de ligne\n\n    \n# fin\ny = 2\n"
        assert python_logical_lines(source) == 2

    def test_docstrings_de_module_classe_fonction_exclues(self):
        source = (
            '"""Module.\n\nSur plusieurs lignes.\n"""\n'
            "class A:\n"
            '    """Classe."""\n'
            "    def f(self):\n"
            '        """Methode,\n        sur deux lignes."""\n'
            "        return 1\n"
            "async def g():\n"
            "    '''Coroutine.'''\n"
            "    return 2\n"
        )
        # class A / def f / return 1 / async def g / return 2
        assert python_logical_lines(source) == 5

    def test_requete_sql_en_triple_guillemets_compte(self):
        source = (
            "def charger(conn):\n"
            '    """Docstring exclue."""\n'
            '    requete = """\n'
            "        SELECT id\n"
            "        FROM corpus_entries\n"
            "        WHERE intent = %s\n"
            '    """\n'
            "    return conn.execute(requete)\n"
        )
        # def + 5 lignes de la chaine SQL + return
        assert python_logical_lines(source) == 7

    def test_chaine_qui_nest_pas_la_premiere_instruction_compte(self):
        source = 'x = 1\n"""pas une docstring : ce n est pas la premiere instruction"""\n'
        assert python_logical_lines(source) == 2

    def test_docstring_sur_la_meme_ligne_que_le_def(self):
        # La ligne porte du code (def f():) : elle compte, la docstring seule non.
        assert python_logical_lines('def f(): """doc"""\n') == 1

    def test_fstring_multiligne_compte(self):
        source = 'nom = "x"\nmessage = f"""\nBonjour {nom}\n"""\n'
        assert python_logical_lines(source) == 4

    def test_continuation_de_ligne_compte(self):
        source = "total = (1 +\n         2)\nautre = 3 + \\\n    4\n"
        assert python_logical_lines(source) == 4

    def test_crlf_compte_comme_lf(self):
        assert python_logical_lines("x = 1\r\n\r\n# c\r\ny = 2\r\n") == 2

    def test_caracteres_non_ascii_avant_la_docstring(self):
        # ast donne des colonnes en octets UTF-8, tokenize en caractères.
        source = 'class Été:\n    """Docstring."""\n    a = "é"\n'
        assert python_logical_lines(source) == 2

    def test_source_invalide_leve_une_erreur(self):
        with pytest.raises(LogicalLineError):
            python_logical_lines("def f(:\n    pass\n")


# ─────────────────────────────────────────────
# JavaScript
# ─────────────────────────────────────────────


class TestJavaScript:
    def test_commentaires_ligne_et_bloc_exclus(self):
        source = (
            "// en-tete\n"
            "const a = 1; // fin de ligne\n"
            "/* bloc\n"
            "   sur plusieurs\n"
            "   lignes */\n"
            "\n"
            "const b = 2;\n"
            "/** doc */ const c = 3;\n"
        )
        assert javascript_logical_lines(source) == 3

    def test_double_barre_dans_une_chaine_nest_pas_un_commentaire(self):
        source = "const url = 'https://exemple.ci'\nconst s = \"/* pas un bloc */\"\nconst n = 1\n"
        assert javascript_logical_lines(source) == 3

    def test_gabarit_multiligne_compte_et_protege_ses_commentaires(self):
        source = (
            "const t = `debut\n"
            "// ceci est du texte du gabarit\n"
            "/* aussi */\n"
            "fin`\n"
            "// vrai commentaire\n"
        )
        assert javascript_logical_lines(source) == 4

    def test_gabarit_imbrique_avec_accolades(self):
        source = (
            "const t = `a ${ { cle: `b ${x}` }.cle } c\n"
            "// texte du gabarit\n"
            "`\n"
            "// vrai commentaire\n"
            "const z = 1\n"
        )
        assert javascript_logical_lines(source) == 4

    def test_regex_contenant_barre_etoile_nest_pas_un_bloc(self):
        source = "const r = /a\\/*b/g;\nconst x = 1;\n// commentaire\nconst y = 2;\n"
        assert javascript_logical_lines(source) == 3

    def test_regex_contenant_double_barre(self):
        source = "if (/^https?:\\/\\//.test(u)) go(u);\nconst x = 1;\n"
        assert javascript_logical_lines(source) == 2

    def test_regex_apres_mot_cle_return(self):
        source = "function f() {\n  return /\\/*x/.test(s)\n}\nconst y = 1\n"
        assert javascript_logical_lines(source) == 4

    def test_division_nest_pas_une_regex(self):
        # Après un opérande, `/` est une division : le `//` qui suit est un commentaire.
        source = "const r = a / b; // moyenne\nconst s = (a) / 2 / c;\n// fin\n"
        assert javascript_logical_lines(source) == 2

    def test_chaine_non_terminee_sarrete_a_la_fin_de_ligne(self):
        # Une apostrophe orpheline ne doit pas avaler les lignes suivantes.
        source = "const s = 'orpheline\n// commentaire\nconst t = 1\n"
        assert javascript_logical_lines(source) == 2


# ─────────────────────────────────────────────
# Vue
# ─────────────────────────────────────────────


class TestVue:
    def test_chaque_bloc_a_sa_syntaxe(self):
        source = (
            "<template>\n"
            "  <!-- commentaire HTML -->\n"
            "  <div>\n"
            "    <!-- sur\n"
            "         deux lignes -->\n"
            "    <a href=\"https://exemple.ci\">lien</a>\n"
            "  </div>\n"
            "</template>\n"
            "\n"
            "<script setup>\n"
            "// commentaire JS\n"
            "const a = 1 /* fin */\n"
            "</script>\n"
            "\n"
            "<style scoped>\n"
            "/* commentaire CSS */\n"
            ".a { color: red; }\n"
            "</style>\n"
        )
        # template: <template>, <div>, <a ...>, </div>, </template> = 5
        # script: <script setup>, const a, </script> = 3
        # style: <style scoped>, .a, </style> = 3
        assert vue_logical_lines(source) == 11

    def test_template_imbrique_ne_ferme_pas_le_bloc(self):
        source = (
            "<template>\n"
            "  <template v-if=\"ok\">\n"
            "    <p>oui</p>\n"
            "  </template>\n"
            "  <!-- toujours dans le template -->\n"
            "</template>\n"
            "<script>\n"
            "// commentaire\n"
            "export default {}\n"
            "</script>\n"
        )
        assert vue_logical_lines(source) == 8

    def test_double_barre_dans_le_template_est_du_contenu(self):
        source = "<template>\n  <p>// texte affiche</p>\n</template>\n"
        assert vue_logical_lines(source) == 3

    def test_contenu_hors_bloc_compte_selon_les_regles_html(self):
        source = "<!-- en-tete -->\n<i18n>\n{ \"fr\": {} }\n</i18n>\n<script>\nconst a = 1\n</script>\n"
        assert vue_logical_lines(source) == 6

    def test_bloc_non_ferme_leve_une_erreur(self):
        with pytest.raises(LogicalLineError):
            vue_logical_lines("<script>\nconst a = 1\n")


# ─────────────────────────────────────────────
# Aiguillage par extension
# ─────────────────────────────────────────────


class TestAiguillage:
    @pytest.mark.parametrize(
        ("nom", "source", "attendu"),
        [
            ("a/b.py", "# c\nx = 1\n", 1),
            ("a/b.js", "// c\nconst x = 1\n", 1),
            ("a/B.vue", "<script>\n// c\n</script>\n", 2),
        ],
    )
    def test_aiguillage(self, nom, source, attendu):
        assert count_logical_lines(nom, source) == attendu

    def test_extension_non_prise_en_charge(self):
        with pytest.raises(LogicalLineError):
            count_logical_lines("a/b.ts", "const x: number = 1\n")
