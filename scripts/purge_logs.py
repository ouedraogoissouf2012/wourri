# -*- coding: utf-8 -*-
"""Wourri — Purge manuelle des logs PII (issue #215, ADR-0025).

Secours ops de la purge quotidienne in-app (app/core/log_retention.py) :
utilisable en cron hôte, en `docker exec`, ou à la main, quel que soit
l'orchestrateur (compose Scaleway ou Dokploy — ADR-0024).

Usage (depuis la racine wouri-api) :

    python scripts/purge_logs.py               # purge avec les rétentions du .env
    python scripts/purge_logs.py --dry-run     # liste sans supprimer
    python scripts/purge_logs.py --log-dir /app/logs \\
        --log-retention-days 30 --feedback-retention-days 365

Politique : docs/compliance/artci-logs.md.
"""
from __future__ import annotations

import argparse
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

from app.config import get_settings  # noqa: E402
from app.core.log_retention import purge_old_logs  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Purge des logs au-delà de la rétention (ADR-0025)."
    )
    parser.add_argument(
        "--log-dir",
        default=str(_HERE / "logs"),
        help="Dossier des logs (défaut: logs/ du repo ; /app/logs en conteneur)",
    )
    parser.add_argument(
        "--log-retention-days",
        type=int,
        default=settings.log_retention_days,
        help=f"Rétention logs applicatifs (défaut: {settings.log_retention_days} j)",
    )
    parser.add_argument(
        "--feedback-retention-days",
        type=int,
        default=settings.feedback_retention_days,
        help=f"Rétention feedback pseudonymisé (défaut: {settings.feedback_retention_days} j)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Liste les fichiers candidats sans les supprimer",
    )
    args = parser.parse_args()

    deleted = purge_old_logs(
        args.log_dir,
        log_retention_days=args.log_retention_days,
        feedback_retention_days=args.feedback_retention_days,
        dry_run=args.dry_run,
    )

    verbe = "candidat(s) à la purge" if args.dry_run else "fichier(s) purgé(s)"
    print(f"{len(deleted)} {verbe} dans {args.log_dir}")
    for f in deleted:
        print(f"  - {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
