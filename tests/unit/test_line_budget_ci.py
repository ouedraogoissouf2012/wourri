"""Le plafond de lignes logiques est réellement appelé par la CI — ADR-0051 §6.5, issue #621.

Un contrôle qu'aucune chaîne d'intégration n'appelle ne contrôle rien. Ces tests
lisent les trois workflows et vérifient :
  - que chacun porte un job qui lance le contrôle AVEC son cliquet (`--baseline`) ;
  - que ce job dispose de la base selon l'événement : sur `pull_request`, HEAD est
    la fusion de test et HEAD^1 la pointe de la base (il faut donc fetch-depth ≥ 2) ;
    sur `push`, la base est `github.event.before`, à récupérer explicitement ;
  - que l'UNION des filtres de chemin `pull_request` des trois workflows couvre
    chaque fichier du périmètre suivi par git. Un fichier ajouté demain dans un
    répertoire qu'aucun filtre ne couvre fait échouer ce test.

PyYAML n'est pas déclaré dans requirements-dev.txt : il arrive par
huggingface_hub (requirements.txt). L'import est volontairement inconditionnel —
s'il disparaît, ce test échoue bruyamment au lieu d'être sauté.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_line_budget import POLICY_PATH, in_scope, parse_policy  # noqa: E402

PROJECT_ROOT = SCRIPTS_DIR.parent
WORKFLOWS = ("ci-api.yml", "ci-lqe.yml", "ci-lqe-web.yml")
CONTROLE = "scripts/check_line_budget.py"


def _charger(nom: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / nom).read_text(encoding="utf-8"))


def _declencheurs(workflow: dict) -> dict:
    # PyYAML (YAML 1.1) lit la clé `on` comme le booléen True.
    return workflow.get("on", workflow.get(True))


def _job_du_controle(workflow: dict) -> dict:
    jobs = [
        job
        for job in workflow["jobs"].values()
        if any(CONTROLE in step.get("run", "") for step in job.get("steps", []))
    ]
    assert len(jobs) == 1, f"attendu exactement un job lançant {CONTROLE}, trouvé {len(jobs)}"
    return jobs[0]


def _motif_github(motif: str) -> re.Pattern:
    """Traduit un filtre de chemin GitHub : `**` traverse les dossiers, `*` et `?` non."""
    assert not motif.startswith("!"), f"motif négatif non pris en charge par ce test : {motif}"
    morceaux = re.split(r"(\*\*|\*|\?)", motif)
    traduction = {"**": ".*", "*": "[^/]*", "?": "[^/]"}
    return re.compile("".join(traduction.get(m, re.escape(m)) for m in morceaux) + r"\Z")


@pytest.mark.parametrize("nom", WORKFLOWS)
class TestJobDuControle:
    def test_lance_le_controle_avec_son_cliquet(self, nom):
        job = _job_du_controle(_charger(nom))
        commandes = " ".join(step.get("run", "") for step in job["steps"])
        assert f"python {CONTROLE} --baseline" in commandes

    def test_la_base_existe_dans_le_clone(self, nom):
        job = _job_du_controle(_charger(nom))
        checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
        profondeur = (checkout.get("with") or {}).get("fetch-depth", 1)
        assert profondeur == 0 or profondeur >= 2, "HEAD^1 absent du clone : le cliquet échouerait"

    def test_une_base_par_type_devenement(self, nom):
        workflow = _charger(nom)
        job = _job_du_controle(workflow)
        etape = next(s for s in job["steps"] if CONTROLE in s.get("run", ""))
        base = str((etape.get("env") or {}).get("BASELINE", ""))
        assert "github.event_name == 'pull_request'" in base and "'HEAD^1'" in base
        assert "github.event.before" in base
        if "push" in _declencheurs(workflow):
            recuperation = [
                s for s in job["steps"]
                if "git fetch" in s.get("run", "") and s.get("if") == "github.event_name == 'push'"
            ]
            assert recuperation, "sur push, github.event.before doit être récupéré explicitement"


def test_les_filtres_couvrent_tout_le_perimetre():
    filtres: list[re.Pattern] = []
    for nom in WORKFLOWS:
        pull_request = _declencheurs(_charger(nom))["pull_request"]
        chemins = pull_request.get("paths")
        if chemins is None:  # aucun filtre : tout fichier déclenche
            return
        filtres.extend(_motif_github(m) for m in chemins)

    politique = parse_policy((PROJECT_ROOT / POLICY_PATH).read_text(encoding="utf-8"))
    suivis = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, check=True, capture_output=True
    ).stdout.decode("utf-8").split("\0")
    a_couvrir = [f for f in suivis if f and in_scope(f, politique)]
    a_couvrir.append(POLICY_PATH)  # modifier la politique doit aussi déclencher le cliquet

    assert len(a_couvrir) > 400, "la liste des fichiers suivis semble incomplète"
    orphelins = [f for f in a_couvrir if not any(r.match(f) for r in filtres)]
    assert not orphelins, f"fichiers qu'aucun workflow ne déclenche : {orphelins}"


@pytest.mark.parametrize(
    ("motif", "chemin", "attendu"),
    [
        ("app/**", "app/services/x.py", True),
        ("*.py", "run.py", True),
        ("*.py", "app/x.py", False),
        ("wouri-lqe/**", "wouri-lqe-web/src/a.js", False),
        ("alembic.ini", "alembic.ini", True),
    ],
)
def test_traduction_des_filtres_github(motif, chemin, attendu):
    assert bool(_motif_github(motif).match(chemin)) is attendu
