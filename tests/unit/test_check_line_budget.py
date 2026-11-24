"""Tests du contrôle du plafond de lignes logiques (scripts/check_line_budget.py) — ADR-0051, issue #621.

Chaque test monte un vrai dépôt git jetable (line_budget_depot.py).

Critères d'acceptation de l'issue #621, couverts ici :
  1. un fichier neuf à 301 lignes logiques échoue ;
  2. un fichier exempté qui s'allonge échoue ;
  3. un fichier exempté qui raccourcit passe, une fois sa valeur inscrite abaissée ;
et le contrôle passe sur le dépôt réel en se mesurant lui-même.
Le cliquet contre la base et `--resserrer` : test_line_budget_cliquet.py.
"""
from __future__ import annotations

import json

import pytest

from .line_budget_depot import SCRIPTS_DIR, Depot, politique, source_python

import check_line_budget  # noqa: E402  (scripts/ ajouté au path par line_budget_depot)
from check_line_budget import POLICY_PATH, PolicyError, main, parse_policy  # noqa: E402

PROJECT_ROOT = SCRIPTS_DIR.parent


@pytest.fixture
def depot(tmp_path) -> Depot:
    return Depot.etabli(tmp_path)


# ─────────────────────────────────────────────
# Lecture et validation de la politique
# ─────────────────────────────────────────────


class TestPolitique:
    def test_politique_valide(self):
        p = parse_policy(json.dumps(politique({"a.py": 320})))
        assert p.ceiling == 300
        assert p.extensions == (".py", ".js", ".vue")
        assert dict(p.exemptions) == {"a.py": 320}

    @pytest.mark.parametrize(
        "alteration",
        [
            lambda d: d.pop("exemptions"),
            lambda d: d.update(inconnue=1),
            lambda d: d.update(plafond_lignes_logiques="300"),
            lambda d: d.update(plafond_lignes_logiques=True),
            lambda d: d.update(plafond_lignes_logiques=0),
            lambda d: d.update(extensions=[".ts"]),
            lambda d: d.update(extensions=[]),
            lambda d: d.update(exclusions="convex/_generated/*"),
            lambda d: d.update(exemptions={"a.py": 300}),
            lambda d: d.update(exemptions={"a.py": "320"}),
            lambda d: d.update(exemptions={"a\\b.py": 320}),
            lambda d: d.update(exemptions={"./a.py": 320}),
        ],
    )
    def test_politique_invalide_refusee(self, alteration):
        donnees = politique()
        alteration(donnees)
        with pytest.raises(PolicyError):
            parse_policy(json.dumps(donnees))

    def test_json_illisible_refuse(self):
        with pytest.raises(PolicyError):
            parse_policy("{pas du json")

    def test_politique_absente_echec_de_configuration(self, depot, capsys):
        depot.commit()
        assert depot.controler() == 2
        assert POLICY_PATH in capsys.readouterr().err


# ─────────────────────────────────────────────
# Critère 1 — aucun fichier non listé au-dessus du plafond
# ─────────────────────────────────────────────


class TestPlafond:
    def test_fichier_neuf_a_301_lignes_echoue(self, depot, capsys):
        depot.politique()
        depot.ecrire("app/neuf.py", source_python(301))
        depot.commit()
        assert depot.controler() == 1
        err = capsys.readouterr().err
        assert "app/neuf.py" in err and "301" in err

    def test_fichier_a_300_lignes_passe(self, depot):
        depot.politique()
        depot.ecrire("app/neuf.py", source_python(300))
        depot.commit()
        assert depot.controler() == 0

    def test_front_mesure_aussi(self, depot, capsys):
        depot.politique()
        depot.ecrire("web/Vue.vue", "<script>\n" + "const a = 1\n" * 300 + "</script>\n")
        depot.commit()
        assert depot.controler() == 1
        assert "web/Vue.vue" in capsys.readouterr().err

    def test_hors_perimetre_ignores(self, depot):
        depot.politique(exclusions=["convex/_generated/*"])
        depot.ecrire("convex/schema.ts", "const a = 1\n" * 500)  # extension hors périmètre
        depot.ecrire("convex/_generated/api.js", "const a = 1\n" * 500)  # fichier engendré
        depot.ecrire("dictionnaires/corpus.json", "[]\n" * 500)  # donnée
        depot.commit()
        depot.ecrire("brouillon_non_suivi.py", source_python(500))  # non suivi par git
        assert depot.controler() == 0

    def test_fichier_illisible_echoue(self, depot, capsys):
        depot.politique()
        depot.ecrire("app/casse.py", "def f(:\n")
        depot.commit()
        assert depot.controler() == 1
        assert "app/casse.py" in capsys.readouterr().err


# ─────────────────────────────────────────────
# Critères 2 et 3 — les fichiers exemptés
# ─────────────────────────────────────────────


class TestExemptions:
    def test_fichier_exempte_a_sa_valeur_passe(self, depot):
        depot.politique({"app/long.py": 320})
        depot.ecrire("app/long.py", source_python(320))
        depot.commit()
        assert depot.controler() == 0

    def test_fichier_exempte_qui_sallonge_echoue(self, depot, capsys):
        depot.politique({"app/long.py": 320})
        depot.ecrire("app/long.py", source_python(321))
        depot.commit()
        assert depot.controler() == 1
        err = capsys.readouterr().err
        assert "app/long.py" in err and "321" in err and "320" in err

    def test_fichier_exempte_qui_raccourcit_sans_mise_a_jour_echoue(self, depot, capsys):
        depot.politique({"app/long.py": 320})
        depot.ecrire("app/long.py", source_python(310))
        depot.commit()
        assert depot.controler() == 1
        err = capsys.readouterr().err
        assert "app/long.py" in err and "310" in err

    def test_fichier_exempte_qui_raccourcit_avec_mise_a_jour_passe(self, depot):
        depot.politique({"app/long.py": 310})
        depot.ecrire("app/long.py", source_python(310))
        depot.commit()
        assert depot.controler() == 0

    def test_fichier_revenu_sous_le_plafond_doit_sortir_de_la_liste(self, depot, capsys):
        depot.politique({"app/long.py": 320})
        depot.ecrire("app/long.py", source_python(290))
        depot.commit()
        assert depot.controler() == 1
        assert "app/long.py" in capsys.readouterr().err

    def test_exemption_dun_fichier_disparu_echoue(self, depot, capsys):
        depot.politique({"app/disparu.py": 320})
        depot.commit()
        assert depot.controler() == 1
        assert "app/disparu.py" in capsys.readouterr().err


# ─────────────────────────────────────────────
# Le dépôt réel
# ─────────────────────────────────────────────


class TestDepotReel:
    def test_le_depot_respecte_sa_politique(self, capsys):
        assert main(["--racine", str(PROJECT_ROOT)]) == 0, capsys.readouterr().err

    def test_le_controle_se_mesure_lui_meme_sans_exemption(self):
        regles = parse_policy((PROJECT_ROOT / POLICY_PATH).read_text(encoding="utf-8"))
        mesures, erreurs = check_line_budget.measure(PROJECT_ROOT, regles)
        assert not erreurs
        for script in ("scripts/check_line_budget.py", "scripts/logical_lines.py"):
            assert script in mesures, f"{script} échappe à sa propre mesure"
            assert mesures[script] <= regles.ceiling
            assert script not in regles.exemptions
