#!/usr/bin/env python
"""
Wouri — Verification de coherence des variables d'environnement (issue #219).

Sprint J prerequisite. Detecte les drifts silencieux entre :
  - docker-compose.prod.yml  (consommateur runtime)
  - .env.prod.template       (declaration des secrets utilisateur)

Trois verifications :

1. Toutes les variables utilisees dans le compose (`${VAR:?...}` ou `${VAR:-...}`)
   doivent etre declarees dans `.env.prod.template` → sinon la prod casse au
   `docker compose up` avec un message d'erreur peu lisible.

2. Aucune variable declaree dans `.env.prod.template` ne doit etre inutilisee
   par le compose (warning, pas erreur — peut etre legitime pour des outils
   externes comme cron, healthchecks ping, etc.).

3. Les noms de variables critiques sont stables entre les fichiers (POSTGRES_*,
   WOURI_API_KEY) — verification implicite via la 1ere check.

## Usage

    python scripts/check_env_consistency.py

Exit code :
    0  → consistance OK
    1  → drift detecte (erreurs sur stderr)

## Whitelist

Certaines variables existent legitimement dans `.env.prod.template` sans
etre dans le compose (cf. `_WHITELIST_TEMPLATE_ONLY` ci-dessous) :
  - HEALTHCHECKS_*  → cron de ping VM (PR #225)
  - POSTGRES_DB     → utilisee dans le default `${POSTGRES_DB:-wourri_prod}`
                      (parse YAML peut ne pas la detecter)

## Refs

  - Issue #219 (Sprint I.c.1 review DRY/SOLID MAJOR M2)
  - PR #212 (livraison Sprint I.c.1 compose + template)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml  # pyyaml deja installe (dependance transitive ou requirements)

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.prod.yml"
TEMPLATE_PATH = PROJECT_ROOT / ".env.prod.template"

# Variables qui peuvent legitimement etre dans `.env.prod.template` sans etre
# referencees par le compose (consommees par d'autres outils sur la VM :
# cron de backup, healthchecks ping, rotation secrets, etc.).
_WHITELIST_TEMPLATE_ONLY: frozenset[str] = frozenset(
    {
        "HEALTHCHECKS_BACKUP_URL",
        "HEALTHCHECKS_API_URL",
        "HEALTHCHECKS_WA_URL",
    }
)

# Variables utilisees par le compose mais qui n'ont pas a etre dans le template
# (injectees par la CI au runtime, cf. PR #234 / #235 pin SHA).
_WHITELIST_COMPOSE_DYNAMIC: frozenset[str] = frozenset(
    {
        # API_IMAGE_TAG / WA_IMAGE_TAG : sont dans le template MAIS aussi
        # injectees dynamiquement par CI. Pas de probleme.
    }
)


# ─────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────

# Regex pour extraire ${VAR} | ${VAR:-default} | ${VAR:?msg} d'une valeur YAML.
# Volontairement strict : la VAR doit etre [A-Z_][A-Z0-9_]* (convention shell).
_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?:[:][-?][^}]*)?\}")


def _collect_vars_from_value(value, vars_set: set[str]) -> None:
    """Walk recursif sur une valeur YAML (str / list / dict) pour collecter
    les references `${VAR}`."""
    if isinstance(value, str):
        for match in _VAR_PATTERN.finditer(value):
            vars_set.add(match.group(1))
    elif isinstance(value, list):
        for item in value:
            _collect_vars_from_value(item, vars_set)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_vars_from_value(v, vars_set)


def parse_compose_vars(compose_path: Path) -> set[str]:
    """Retourne l'ensemble des noms de variables `${VAR}` utilisees dans le
    docker-compose.yml. Ignore naturellement les commentaires (parse YAML)."""
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    vars_set: set[str] = set()
    _collect_vars_from_value(data, vars_set)
    return vars_set


def parse_env_template(template_path: Path) -> set[str]:
    """Retourne l'ensemble des noms de variables declarees dans
    `.env.prod.template` (lignes `NAME=...` non commentees)."""
    vars_set: set[str] = set()
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Format attendu : NAME=value (value peut etre vide ou contenir des =)
        if "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        # Filtrer : convention shell (lettres maj / chiffres / _)
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
            vars_set.add(name)
    return vars_set


# ─────────────────────────────────────────────
# Verifications
# ─────────────────────────────────────────────


def check_consistency(
    compose_vars: set[str],
    template_vars: set[str],
) -> tuple[list[str], list[str]]:
    """Retourne (erreurs, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # Verification 1 (erreur) : compose utilise une var absente du template
    missing_in_template = (compose_vars - template_vars) - _WHITELIST_COMPOSE_DYNAMIC
    for var in sorted(missing_in_template):
        errors.append(
            f"Variable '{var}' utilisee dans docker-compose.prod.yml mais "
            f"ABSENTE de .env.prod.template (la prod cassera au demarrage)"
        )

    # Verification 2 (warning) : template declare une var non utilisee
    unused_in_compose = (template_vars - compose_vars) - _WHITELIST_TEMPLATE_ONLY
    for var in sorted(unused_in_compose):
        warnings.append(
            f"Variable '{var}' declaree dans .env.prod.template mais "
            f"non utilisee par docker-compose.prod.yml"
        )

    return errors, warnings


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────


def main() -> int:
    if not COMPOSE_PATH.exists():
        print(f"[ERROR] {COMPOSE_PATH} introuvable", file=sys.stderr)
        return 1
    if not TEMPLATE_PATH.exists():
        print(f"[ERROR] {TEMPLATE_PATH} introuvable", file=sys.stderr)
        return 1

    compose_vars = parse_compose_vars(COMPOSE_PATH)
    template_vars = parse_env_template(TEMPLATE_PATH)
    errors, warnings = check_consistency(compose_vars, template_vars)

    # Output : warnings d'abord (stdout), erreurs ensuite (stderr)
    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[ERROR] {e}", file=sys.stderr)

    if errors:
        print(
            f"\n[FAIL] {len(errors)} erreur(s) de coherence env. Voir messages ci-dessus.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[OK] {len(compose_vars)} var(s) compose / "
        f"{len(template_vars)} var(s) template, coherence validee."
        + (f" ({len(warnings)} warning(s))" if warnings else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
