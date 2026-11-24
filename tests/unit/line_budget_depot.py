"""Dépôt git jetable pour les tests du plafond de lignes logiques (ADR-0051, issue #621).

Partagé par test_check_line_budget.py et test_line_budget_cliquet.py. Le contrôle ne
mesure que les fichiers suivis par git, et son cliquet lit la politique de la base
avec `git show` : simuler git aurait testé la simulation, pas le contrôle.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_line_budget import POLICY_PATH, main  # noqa: E402

PLAFOND = 300


def source_python(n: int) -> str:
    """Source Python de exactement `n` lignes logiques, entrecoupée de bruit non compté."""
    lignes = []
    for i in range(n):
        lignes.append(f"x{i} = {i}")
        lignes.append("# commentaire, non compté")
        lignes.append("")
    return "\n".join(lignes) + "\n"


def politique(exemptions=None, plafond=PLAFOND, extensions=(".py", ".js", ".vue"), exclusions=()) -> dict:
    return {
        "_commentaire": "politique de test",
        "plafond_lignes_logiques": plafond,
        "extensions": list(extensions),
        "exclusions": list(exclusions),
        "exemptions": dict(exemptions or {}),
    }


class Depot:
    """Dépôt git jetable."""

    def __init__(self, racine: Path):
        self.racine = racine
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "test")
        self._git("config", "commit.gpgsign", "false")
        self._git("config", "core.autocrlf", "false")

    @classmethod
    def etabli(cls, racine: Path) -> "Depot":
        """Dépôt où le contrôle existe déjà : sa politique y est alors obligatoire."""
        depot = cls(racine)
        depot.etablir_controle()
        return depot

    def _git(self, *args: str) -> str:
        res = subprocess.run(
            ["git", *args], cwd=self.racine, check=True, capture_output=True, text=True
        )
        return res.stdout.strip()

    def ecrire(self, chemin: str, contenu: str) -> None:
        cible = self.racine / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8", newline="\n")

    def politique(self, exemptions=None, **kwargs) -> None:
        self.ecrire(POLICY_PATH, json.dumps(politique(exemptions, **kwargs), indent=2) + "\n")

    def etablir_controle(self) -> None:
        self.ecrire("scripts/check_line_budget.py", "x = 1\n")

    def supprimer(self, chemin: str) -> None:
        self._git("rm", "-q", chemin)

    def commit(self, message: str = "c") -> str:
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", message)
        return self._git("rev-parse", "HEAD")

    def lire_politique(self) -> dict:
        return json.loads((self.racine / POLICY_PATH).read_text(encoding="utf-8"))

    def texte_politique(self) -> str:
        return (self.racine / POLICY_PATH).read_text(encoding="utf-8")

    def controler(self, *args: str) -> int:
        return main(["--racine", str(self.racine), *args])
