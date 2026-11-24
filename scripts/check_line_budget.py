#!/usr/bin/env python
"""
Wouri — Plafond de lignes logiques par fichier, vérifié en CI (ADR-0051, issue #621).

Mesure chaque fichier de code suivi par git (règle de comptage : logical_lines.py)
et le confronte à la politique `scripts/line_budget.json` :

  - un fichier NON exempté échoue au-dessus du plafond ;
  - un fichier exempté échoue s'il dépasse sa valeur inscrite, mais aussi s'il est
    passé SOUS elle sans que la valeur soit abaissée : la dette doit descendre ;
  - une exemption dont le fichier a disparu ou est revenu sous le plafond échoue.

Avec `--baseline REF`, le cliquet (ADR-0051 §6.5) compare la politique à celle de
REF et refuse tout relâchement : exemption ajoutée, valeur relevée, plafond relevé,
extension retirée, exclusion ajoutée. Sans lui, il suffirait de relever le chiffre
inscrit dans la PR même qui allonge le fichier. Si REF ne porte pas la politique,
c'est toléré au seul premier établissement — quand REF ne porte pas non plus ce
script — et refusé sinon.

`--resserrer` réécrit la politique en abaissant les valeurs au réel et en retirant
les exemptions périmées. Il n'ajoute ni ne relève jamais rien.

## Usage

    python scripts/check_line_budget.py                      # contrôle local
    python scripts/check_line_budget.py --baseline HEAD^1    # CI, avec cliquet
    python scripts/check_line_budget.py --resserrer          # après un découpage

Code retour : 0 conforme, 1 violation, 2 configuration ou base illisible.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from logical_lines import SUPPORTED_EXTENSIONS, LogicalLineError, count_logical_lines

POLICY_PATH = "scripts/line_budget.json"
CONTROL_SCRIPT_PATH = "scripts/check_line_budget.py"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK, EXIT_VIOLATION, EXIT_CONFIG = 0, 1, 2

_COMMENT_KEY = "_commentaire"
_REQUIRED_KEYS = ("plafond_lignes_logiques", "extensions", "exclusions", "exemptions")


class PolicyError(ValueError):
    """La politique est mal formée."""


class ControlError(RuntimeError):
    """Le contrôle ne peut pas s'exécuter : politique introuvable, git ou base illisible."""


@dataclass(frozen=True)
class Policy:
    ceiling: int
    extensions: tuple[str, ...]
    exclusions: tuple[str, ...]  # motifs fnmatch sur le chemin posix : `*` traverse les dossiers
    exemptions: Mapping[str, int]
    comment: str = field(default="", compare=False)


# ─────────────────────────────────────────────
# Politique
# ─────────────────────────────────────────────


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_exemption_path(path: object) -> None:
    if not isinstance(path, str) or not path:
        raise PolicyError(f"chemin d'exemption invalide : {path!r}")
    posix = PurePosixPath(path)
    if "\\" in path or posix.is_absolute() or posix.as_posix() != path or ".." in posix.parts:
        raise PolicyError(f"chemin d'exemption non canonique (posix, relatif à la racine) : {path!r}")


def parse_policy(text: str) -> Policy:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PolicyError(f"JSON illisible : {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError("la politique doit être un objet JSON")
    unknown = set(data) - set(_REQUIRED_KEYS) - {_COMMENT_KEY}
    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if unknown or missing:
        raise PolicyError(f"clés inconnues {sorted(unknown)} ou manquantes {missing}")

    ceiling = data["plafond_lignes_logiques"]
    if not _is_int(ceiling) or ceiling <= 0:
        raise PolicyError(f"plafond_lignes_logiques doit être un entier positif : {ceiling!r}")

    extensions = data["extensions"]
    if not isinstance(extensions, list) or not extensions or len(set(extensions)) != len(extensions):
        raise PolicyError("extensions doit être une liste non vide, sans doublon")
    if not set(extensions) <= SUPPORTED_EXTENSIONS:
        raise PolicyError(f"extensions non mesurables : {sorted(set(extensions) - SUPPORTED_EXTENSIONS)}")

    exclusions = data["exclusions"]
    if not isinstance(exclusions, list) or not all(isinstance(p, str) and p for p in exclusions):
        raise PolicyError("exclusions doit être une liste de motifs non vides")

    exemptions = data["exemptions"]
    if not isinstance(exemptions, dict):
        raise PolicyError("exemptions doit être un objet {chemin: lignes logiques}")
    for path, value in exemptions.items():
        _check_exemption_path(path)
        if not _is_int(value) or value <= ceiling:
            raise PolicyError(
                f"{path} : valeur inscrite {value!r} invalide — une exemption n'existe qu'au-dessus du plafond"
            )

    comment = data.get(_COMMENT_KEY, "")
    if not isinstance(comment, str):
        raise PolicyError(f"{_COMMENT_KEY} doit être un texte")
    return Policy(ceiling, tuple(extensions), tuple(exclusions), dict(exemptions), comment)


def render_policy(policy: Policy) -> str:
    data: dict[str, object] = {_COMMENT_KEY: policy.comment} if policy.comment else {}
    data.update(
        {
            "plafond_lignes_logiques": policy.ceiling,
            "extensions": list(policy.extensions),
            "exclusions": list(policy.exclusions),
            "exemptions": dict(sorted(policy.exemptions.items())),
        }
    )
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def in_scope(path: str, policy: Policy) -> bool:
    return PurePosixPath(path).suffix in policy.extensions and not any(
        fnmatch.fnmatchcase(path, pattern) for pattern in policy.exclusions
    )


# ─────────────────────────────────────────────
# Git
# ─────────────────────────────────────────────


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    except OSError as exc:
        raise ControlError(f"git introuvable : {exc}") from exc


def tracked_files(root: Path) -> list[str]:
    result = _git(root, "ls-files", "-z")
    if result.returncode != 0:
        raise ControlError(f"git ls-files a échoué dans {root} : {result.stderr.decode(errors='replace')}")
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def load_baseline(root: Path, ref: str) -> Policy | None:
    """Politique de la base ; None au seul premier établissement (ni politique ni contrôle dans la base)."""
    verified = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if verified.returncode != 0:
        raise ControlError(
            f"base « {ref} » introuvable dans le clone — en CI, vérifier fetch-depth et la récupération de la base"
        )
    commit = verified.stdout.decode().strip()

    def present(path: str) -> bool:
        return _git(root, "cat-file", "-e", f"{commit}:{path}").returncode == 0

    if not present(POLICY_PATH):
        if present(CONTROL_SCRIPT_PATH):
            raise ControlError(
                f"la base « {ref} » porte {CONTROL_SCRIPT_PATH} mais pas {POLICY_PATH} : "
                "politique supprimée ou déplacée, le cliquet ne peut pas être contourné ainsi"
            )
        return None
    shown = _git(root, "show", f"{commit}:{POLICY_PATH}")
    try:
        return parse_policy(shown.stdout.decode("utf-8"))
    except PolicyError as exc:
        raise ControlError(f"politique de la base « {ref} » illisible : {exc}") from exc


# ─────────────────────────────────────────────
# Mesure et règles
# ─────────────────────────────────────────────


def measure(root: Path, policy: Policy) -> tuple[dict[str, int], list[str]]:
    """Lignes logiques de chaque fichier suivi du périmètre, et les fichiers non mesurables."""
    counts: dict[str, int] = {}
    errors: list[str] = []
    for path in tracked_files(root):
        file = root / path
        if not in_scope(path, policy) or not file.is_file():
            continue
        try:
            counts[path] = count_logical_lines(path, file.read_text(encoding="utf-8-sig"))
        except (LogicalLineError, UnicodeDecodeError) as exc:
            errors.append(f"{path} : mesure impossible — {exc}")
    return counts, errors


def budget_violations(policy: Policy, counts: Mapping[str, int]) -> list[str]:
    violations = []
    redo = "corriger l'exemption, ou lancer --resserrer"
    for path, lines in sorted(counts.items()):
        listed = policy.exemptions.get(path)
        if listed is None:
            if lines > policy.ceiling:
                violations.append(
                    f"{path} : {lines} lignes logiques, au-dessus du plafond de {policy.ceiling} — à découper"
                )
        elif lines > listed:
            violations.append(
                f"{path} : {lines} lignes logiques pour {listed} inscrites — un fichier exempté ne peut pas s'allonger"
            )
        elif lines <= policy.ceiling:
            violations.append(f"{path} : {lines} lignes logiques, revenu sous le plafond — retirer son exemption ({redo})")
        elif lines < listed:
            violations.append(f"{path} : {lines} lignes logiques pour {listed} inscrites — inscrire {lines} ({redo})")
    for path in sorted(set(policy.exemptions) - set(counts)):
        violations.append(f"{path} : exempté mais absent du périmètre mesuré — retirer son exemption ({redo})")
    return violations


def ratchet_violations(base: Policy, head: Policy) -> list[str]:
    violations = []
    if head.ceiling > base.ceiling:
        violations.append(f"plafond relevé de {base.ceiling} à {head.ceiling} par rapport à la base — interdit")
    for extension in sorted(set(base.extensions) - set(head.extensions)):
        violations.append(f"extension {extension} retirée du périmètre par rapport à la base — interdit")
    for pattern in sorted(set(head.exclusions) - set(base.exclusions)):
        violations.append(f"exclusion {pattern} ajoutée par rapport à la base — interdit")
    for path, value in sorted(head.exemptions.items()):
        before = base.exemptions.get(path)
        if before is None:
            violations.append(f"{path} : exemption ajoutée — la liste ne peut jamais s'agrandir")
        elif value > before:
            violations.append(f"{path} : valeur inscrite relevée de {before} à {value} — interdit")
    return violations


def tighten(policy: Policy, counts: Mapping[str, int]) -> Policy:
    """Abaisse chaque valeur au réel et retire les exemptions périmées. Ne relève ni n'ajoute jamais."""
    kept = {
        path: min(value, counts[path])
        for path, value in policy.exemptions.items()
        if counts.get(path, 0) > policy.ceiling
    }
    return replace(policy, exemptions=kept)


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plafond de lignes logiques par fichier (ADR-0051).")
    parser.add_argument("--racine", default=str(DEFAULT_ROOT), help="racine du dépôt git (défaut : ce dépôt)")
    parser.add_argument("--baseline", metavar="REF", help="ref git de la base, pour le cliquet")
    parser.add_argument(
        "--resserrer",
        action="store_true",
        help=(
            "abaisser les valeurs inscrites au réel et retirer les exemptions périmées. "
            "La politique resserrée est écrite même si le contrôle signale par ailleurs une "
            "violation : le resserrement ne fait que baisser des valeurs, il est toujours "
            "valide, et le code 1 signale la violation restante."
        ),
    )
    return parser.parse_args(argv)


def _load_head_policy(root: Path) -> Policy:
    path = root / POLICY_PATH
    if not path.is_file():
        raise ControlError(f"{POLICY_PATH} introuvable dans {root}")
    return parse_policy(path.read_text(encoding="utf-8"))


def _write_tightened(root: Path, before: Policy, after: Policy) -> None:
    (root / POLICY_PATH).write_text(render_policy(after), encoding="utf-8", newline="\n")
    for path, value in sorted(before.exemptions.items()):
        new = after.exemptions.get(path)
        if new != value:
            print(f"resserré : {path} {value} → {new if new is not None else 'retiré'}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = Path(args.racine).resolve()
    try:
        written = _load_head_policy(root)
        counts, violations = measure(root, written)
        policy = tighten(written, counts) if args.resserrer else written
        violations += budget_violations(policy, counts)
        if args.baseline:
            base = load_baseline(root, args.baseline)
            if base is None:
                print(f"Base « {args.baseline} » sans contrôle ni politique : premier établissement, cliquet non appliqué.")
            else:
                violations += ratchet_violations(base, policy)
    except (PolicyError, ControlError) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return EXIT_CONFIG

    # L'écriture vient en dernier : un contrôle qui échoue en route (base illisible…)
    # ne laisse jamais derrière lui une politique déjà réécrite.
    if policy != written:
        _write_tightened(root, written, policy)

    if violations:
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            f"{len(violations)} violation(s) du plafond de {policy.ceiling} lignes logiques (ADR-0051).",
            file=sys.stderr,
        )
        return EXIT_VIOLATION
    print(
        f"OK : {len(counts)} fichiers mesurés, aucun au-dessus de {policy.ceiling} lignes logiques "
        f"hors {len(policy.exemptions)} exemption(s) inscrite(s)."
    )
    return EXIT_OK


if __name__ == "__main__":
    # Console Windows en cp1252 : un caractère non représentable (« → », un chemin
    # accentué) est remplacé au lieu de faire planter le compte rendu après
    # l'écriture de la politique par --resserrer.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    sys.exit(main())
