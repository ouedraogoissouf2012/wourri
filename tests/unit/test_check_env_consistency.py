"""
Tests pour scripts/check_env_consistency.py (issue #219).

Couvre :
    - parse_compose_vars : extraction des `${VAR}` depuis YAML (ignore commentaires)
    - parse_env_template : extraction des `NAME=...` depuis .env (ignore lignes vides + #)
    - check_consistency : detection des drifts (erreurs + warnings)
    - main : code retour sur projet reel
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Charger le script via importlib (pas un package "scripts" reel)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_env_consistency.py"
_spec = importlib.util.spec_from_file_location("check_env_consistency", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ─────────────────────────────────────────────
# parse_compose_vars
# ─────────────────────────────────────────────


def test_parse_compose_vars_required_et_optional(tmp_path):
    """Detecte ${VAR:?msg} (required) et ${VAR:-default} (optional)."""
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  api:
    image: foo
    environment:
      A: ${REQUIRED_VAR:?msg}
      B: ${OPTIONAL_VAR:-default}
      C: ${PLAIN_VAR}
""",
        encoding="utf-8",
    )
    result = _mod.parse_compose_vars(compose)
    assert result == {"REQUIRED_VAR", "OPTIONAL_VAR", "PLAIN_VAR"}


def test_parse_compose_vars_ignore_commentaires(tmp_path):
    """YAML parser ignore naturellement les commentaires
    → ${VAR_IN_COMMENT} ne doit PAS etre detecte."""
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
# Documentation : utiliser ${VAR_IN_COMMENT:?...} pour les secrets
services:
  api:
    environment:
      A: ${REAL_VAR}
""",
        encoding="utf-8",
    )
    result = _mod.parse_compose_vars(compose)
    assert result == {"REAL_VAR"}
    assert "VAR_IN_COMMENT" not in result


def test_parse_compose_vars_walk_recursif(tmp_path):
    """Detecte les vars dans listes et dicts imbriques."""
    compose = tmp_path / "compose.yml"
    compose.write_text(
        """
services:
  api:
    volumes:
      - ${VOLUME_PATH}:/data
    healthcheck:
      test:
        - CMD
        - curl
        - ${HEALTH_URL}/api
""",
        encoding="utf-8",
    )
    result = _mod.parse_compose_vars(compose)
    assert "VOLUME_PATH" in result
    assert "HEALTH_URL" in result


# ─────────────────────────────────────────────
# parse_env_template
# ─────────────────────────────────────────────


def test_parse_env_template_lignes_simples(tmp_path):
    """Format NAME=value standard."""
    env = tmp_path / ".env.template"
    env.write_text(
        "POSTGRES_USER=wourri\n"
        "POSTGRES_PASSWORD=secret123\n"
        "POSTGRES_DB=mydb\n",
        encoding="utf-8",
    )
    result = _mod.parse_env_template(env)
    assert result == {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}


def test_parse_env_template_ignore_commentaires_et_vides(tmp_path):
    env = tmp_path / ".env.template"
    env.write_text(
        "# Commentaire de section\n"
        "\n"
        "VAR_A=value_a\n"
        "# Autre commentaire\n"
        "VAR_B=\n"
        "\n"
        "  # Indentation commentaire ignoree\n",
        encoding="utf-8",
    )
    result = _mod.parse_env_template(env)
    assert result == {"VAR_A", "VAR_B"}


def test_parse_env_template_filtre_noms_invalides(tmp_path):
    """Convention shell : seules les vars UPPER_SNAKE_CASE retenues."""
    env = tmp_path / ".env.template"
    env.write_text(
        "VALID_VAR=ok\n"
        "lowercase=ignored\n"
        "Mixed_Case=ignored\n"
        "1STARTS_WITH_DIGIT=ignored\n"
        "ANOTHER_OK=ok\n",
        encoding="utf-8",
    )
    result = _mod.parse_env_template(env)
    assert result == {"VALID_VAR", "ANOTHER_OK"}


# ─────────────────────────────────────────────
# check_consistency
# ─────────────────────────────────────────────


def test_check_consistency_drift_compose_sans_template():
    """Var dans compose mais absente du template → erreur."""
    errors, warnings = _mod.check_consistency(
        compose_vars={"DECLARED", "NEW_VAR_FORGOT"},
        template_vars={"DECLARED"},
    )
    assert len(errors) == 1
    assert "NEW_VAR_FORGOT" in errors[0]
    assert "ABSENTE" in errors[0]


def test_check_consistency_var_template_inutilisee_est_warning():
    """Var dans template mais non utilisee par compose → warning, pas erreur."""
    errors, warnings = _mod.check_consistency(
        compose_vars={"USED"},
        template_vars={"USED", "ORPHANED_TEMPLATE_VAR"},
    )
    assert errors == []
    assert len(warnings) == 1
    assert "ORPHANED_TEMPLATE_VAR" in warnings[0]


def test_check_consistency_whitelist_template_only():
    """Variables de la whitelist (HEALTHCHECKS_*) ne generent pas de warning."""
    errors, warnings = _mod.check_consistency(
        compose_vars={"USED"},
        template_vars={"USED", "HEALTHCHECKS_BACKUP_URL", "HEALTHCHECKS_API_URL"},
    )
    assert errors == []
    assert warnings == []


def test_check_consistency_coherence_totale():
    """Cas nominal : compose et template alignes exactement."""
    vars_set = {"POSTGRES_USER", "POSTGRES_PASSWORD", "WOURI_API_KEY"}
    errors, warnings = _mod.check_consistency(
        compose_vars=vars_set,
        template_vars=vars_set,
    )
    assert errors == []
    assert warnings == []


# ─────────────────────────────────────────────
# main() sur les fichiers reels du projet
# ─────────────────────────────────────────────


def test_main_retourne_0_sur_projet_reel():
    """Verifie que le script s'execute sans drift sur les vrais fichiers."""
    # main() lit COMPOSE_PATH et TEMPLATE_PATH (vrais fichiers du projet)
    # On ne peut pas easily monkeypatcher car ils sont resolus a l'import.
    # On execute juste main() et on verifie le code retour.
    return_code = _mod.main()
    assert return_code == 0, "Le projet a un drift env detecte par le check"
