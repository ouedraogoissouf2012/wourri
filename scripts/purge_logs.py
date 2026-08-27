# -*- coding: utf-8 -*-
"""Wourri — Purge manuelle des logs PII (issue #215, ADR-0025).

Secours ops de la purge quotidienne in-app (app/core/log_retention.py) :
utilisable en cron hôte, en `docker exec`, ou à la main, quel que soit
l'orchestrateur (compose Scaleway ou Dokploy — ADR-0026).

N'importe QUE app/core/log_retention.py (module feuille) : pas de dépendance
à app/config.py, dont l'import exécute get_settings() (sys.exit possible si
ENV=production sans clé) et un makedirs relatif au CWD — inacceptable pour un
outil de secours lancé depuis un cron. Les rétentions viennent des flags, des
env vars LOG_RETENTION_DAYS / FEEDBACK_RETENTION_DAYS, ou des défauts ADR-0025.

Usage (depuis la racine wouri-api) :

    python scripts/purge_logs.py               # purge avec env vars ou défauts
    python scripts/purge_logs.py --dry-run     # liste sans supprimer
    python scripts/purge_logs.py --log-dir /app/logs \\
        --log-retention-days 30 --feedback-retention-days 365

Politique : docs/compliance/artci-logs.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# UTF-8 stdout/stderr (Windows console) — pattern projet, cf. import_corpus_ivr.py
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from app.core.log_retention import (  # noqa: E402
    DEFAULT_FEEDBACK_RETENTION_DAYS,
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_RETENTION_DAYS,
    purge_old_logs,
)


def _env_int(name: str, default: int) -> int:
    """Entier depuis l'env, défaut si absent/invalide (signalé sur stderr)."""
    raw = os.getenv(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(
            f"AVERTISSEMENT : {name}={raw!r} invalide, défaut {default} utilisé",
            file=sys.stderr,
        )
        return default


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Purge des logs au-delà de la rétention (ADR-0025)."
    )
    parser.add_argument(
        "--log-dir",
        default=os.fspath(DEFAULT_LOG_DIR),
        help="Dossier des logs (défaut: logs/ du repo ; /app/logs en conteneur)",
    )
    parser.add_argument(
        "--log-retention-days",
        type=int,
        default=_env_int("LOG_RETENTION_DAYS", DEFAULT_LOG_RETENTION_DAYS),
        help="Rétention logs applicatifs en jours (défaut: env "
        f"LOG_RETENTION_DAYS ou {DEFAULT_LOG_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--feedback-retention-days",
        type=int,
        default=_env_int("FEEDBACK_RETENTION_DAYS", DEFAULT_FEEDBACK_RETENTION_DAYS),
        help="Rétention feedback pseudonymisé en jours (défaut: env "
        f"FEEDBACK_RETENTION_DAYS ou {DEFAULT_FEEDBACK_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Liste les fichiers candidats sans les supprimer",
    )
    args = parser.parse_args()

    try:
        deleted = purge_old_logs(
            args.log_dir,
            log_retention_days=args.log_retention_days,
            feedback_retention_days=args.feedback_retention_days,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        return 2

    verbe = "candidat(s) à la purge" if args.dry_run else "fichier(s) purgé(s)"
    print(f"{len(deleted)} {verbe} dans {args.log_dir}")
    for f in deleted:
        print(f"  - {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
