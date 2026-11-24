"""Le cliquet du plafond de lignes logiques, et `--resserrer` — ADR-0051 §6.5, issue #621.

La politique ne peut que se resserrer par rapport à la branche de base. Sans ce
cliquet, une PR pourrait allonger un fichier exempté en relevant dans le même
commit sa valeur inscrite : le critère 2 de #621 ne vaudrait rien.

`--resserrer` abaisse les valeurs au réel et retire les exemptions périmées. Il
n'ajoute ni ne relève jamais rien — sinon il deviendrait lui-même le contournement.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from .line_budget_depot import SCRIPTS_DIR, Depot, source_python

from check_line_budget import POLICY_PATH  # noqa: E402  (scripts/ ajouté au path par line_budget_depot)


@pytest.fixture
def depot(tmp_path) -> Depot:
    return Depot.etabli(tmp_path)


class TestCliquet:
    def _base(self, depot: Depot, **kwargs) -> str:
        depot.politique(**kwargs)
        depot.ecrire("app/long.py", source_python(320))
        return depot.commit("base")

    def test_allonger_et_relever_la_valeur_dans_la_meme_pr_echoue(self, depot, capsys):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.politique(exemptions={"app/long.py": 330})
        depot.ecrire("app/long.py", source_python(330))
        depot.commit("pr")
        assert depot.controler() == 0  # sans cliquet, le contournement passerait…
        assert depot.controler("--baseline", base) == 1  # …le cliquet le refuse
        err = capsys.readouterr().err
        assert "app/long.py" in err and "330" in err and "320" in err

    def test_ajouter_une_exemption_echoue(self, depot, capsys):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.ecrire("app/nouveau.py", source_python(310))
        depot.politique(exemptions={"app/long.py": 320, "app/nouveau.py": 310})
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 1
        assert "app/nouveau.py" in capsys.readouterr().err

    def test_renommer_un_fichier_exempte_echoue(self, depot, capsys):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.supprimer("app/long.py")
        depot.ecrire("app/renomme.py", source_python(320))
        depot.politique(exemptions={"app/renomme.py": 320})
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 1
        assert "app/renomme.py" in capsys.readouterr().err

    def test_relever_le_plafond_echoue(self, depot, capsys):
        # Relever le plafond à 400 rend l'exemption inutile : seul le cliquet voit le contournement.
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.politique(plafond=400)
        depot.commit("pr")
        assert depot.controler() == 0
        assert depot.controler("--baseline", base) == 1
        assert "400" in capsys.readouterr().err

    def test_retirer_une_extension_echoue(self, depot, capsys):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.politique(exemptions={"app/long.py": 320}, extensions=(".py", ".js"))
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 1
        assert ".vue" in capsys.readouterr().err

    def test_ajouter_une_exclusion_echoue(self, depot, capsys):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.politique(exemptions={"app/long.py": 320}, exclusions=["app/*"])
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 1
        assert "app/*" in capsys.readouterr().err

    def test_abaisser_une_valeur_passe(self, depot):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.politique(exemptions={"app/long.py": 310})
        depot.ecrire("app/long.py", source_python(310))
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 0

    def test_retirer_une_exemption_passe(self, depot):
        base = self._base(depot, exemptions={"app/long.py": 320})
        depot.politique()
        depot.ecrire("app/long.py", source_python(250))
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 0

    def test_ref_de_base_illisible_echoue(self, depot, capsys):
        depot.politique()
        depot.commit()
        assert depot.controler("--baseline", "0" * 40) == 2
        assert "0" * 40 in capsys.readouterr().err

    def test_premier_etablissement_tolere(self, tmp_path, capsys):
        # Base sans contrôle ni politique : c'est la PR qui établit le contrôle.
        depot = Depot(tmp_path)
        depot.ecrire("app/a.py", source_python(10))
        base = depot.commit("base")
        depot.etablir_controle()
        depot.politique()
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 0
        assert "premier établissement" in capsys.readouterr().out

    def test_politique_supprimee_de_la_base_ou_le_controle_existe_echoue(self, tmp_path, capsys):
        # Le contrôle existe dans la base mais pas sa politique : contournement, pas établissement.
        depot = Depot.etabli(tmp_path)
        base = depot.commit("base sans politique")
        depot.politique()
        depot.commit("pr")
        assert depot.controler("--baseline", base) == 2
        assert POLICY_PATH in capsys.readouterr().err


class TestResserrer:
    def test_abaisse_et_retire(self, depot):
        depot.politique(
            {"app/raccourci.py": 340, "app/sous_plafond.py": 320, "app/disparu.py": 330, "app/stable.py": 310}
        )
        depot.ecrire("app/raccourci.py", source_python(325))
        depot.ecrire("app/sous_plafond.py", source_python(200))
        depot.ecrire("app/stable.py", source_python(310))
        depot.commit()
        assert depot.controler("--resserrer") == 0
        assert depot.lire_politique()["exemptions"] == {"app/raccourci.py": 325, "app/stable.py": 310}
        assert depot.controler() == 0

    def test_najoute_jamais_un_fichier_au_dessus_du_plafond(self, depot):
        depot.politique()
        depot.ecrire("app/neuf.py", source_python(301))
        depot.commit()
        assert depot.controler("--resserrer") == 1
        assert depot.lire_politique()["exemptions"] == {}

    def test_ne_releve_jamais_une_valeur(self, depot):
        depot.politique({"app/long.py": 320})
        depot.ecrire("app/long.py", source_python(321))
        depot.commit()
        assert depot.controler("--resserrer") == 1
        assert depot.lire_politique()["exemptions"] == {"app/long.py": 320}

    def test_conserve_le_reste_de_la_politique(self, depot):
        depot.politique({"app/long.py": 340}, exclusions=["convex/_generated/*"])
        depot.ecrire("app/long.py", source_python(330))
        depot.commit()
        avant = depot.lire_politique()
        assert depot.controler("--resserrer") == 0
        apres = depot.lire_politique()
        avant["exemptions"] = {"app/long.py": 330}
        assert apres == avant
        texte = depot.texte_politique()
        assert texte.endswith("}\n") and "\r" not in texte

    def test_ligne_de_commande_sur_une_console_non_utf8(self, depot):
        # Console Windows (cp1252) : un caractère non représentable ne doit pas faire
        # planter le compte rendu APRÈS l'écriture de la politique (état incohérent).
        depot.politique({"app/long.py": 340})
        depot.ecrire("app/long.py", source_python(330))
        depot.commit()
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        res = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "check_line_budget.py"), "--racine", str(depot.racine), "--resserrer"],
            capture_output=True, env=env,
        )
        assert res.returncode == 0, res.stderr.decode("cp1252", errors="replace")
        assert depot.lire_politique()["exemptions"] == {"app/long.py": 330}
