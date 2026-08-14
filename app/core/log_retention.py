# -*- coding: utf-8 -*-
"""
WOURI - Rétention et purge des logs PII (issue #215, ADR-0025).

Politique complète : docs/compliance/artci-logs.md. Résumé :
- logs applicatifs `wourri-YYYY-MM-DD.log` : purgés au-delà de
  LOG_RETENTION_DAYS (défaut 30 j — contiennent des transcriptions en clair) ;
- feedback `feedback-YYYY-MM.jsonl` : purgés au-delà de
  FEEDBACK_RETENTION_DAYS (défaut 365 j — pseudonymisés, finalité C5) ;
- fichiers legacy (`wourri.log`, `feedback.jsonl`, pré-ADR-0025) : purgés sur
  leur mtime avec la rétention de leur catégorie.

Le nommage par date évite tout rename de rotation : les 2 workers uvicorn
écrivent le même fichier du jour en append, sans course. La purge est une
suppression de fichiers entiers — idempotente, exécutable par chaque worker.

Planification : scheduler 24 h démarré dans le lifespan FastAPI (même pattern
que app/services/audio_cleanup.py) + script ops scripts/purge_logs.py.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Fichiers datés (ADR-0025) — les regex n'acceptent que des dates plausibles ;
# un nom invalide est ignoré (jamais supprimé par erreur).
_DATED_LOG_RE = re.compile(r"^wourri-(\d{4})-(\d{2})-(\d{2})\.log$")
_MONTHLY_FEEDBACK_RE = re.compile(r"^feedback-(\d{4})-(\d{2})\.jsonl$")

# Fichiers legacy pré-ADR-0025, purgés sur mtime pendant la transition.
_LEGACY_LOG = "wourri.log"
_LEGACY_FEEDBACK = "feedback.jsonl"

_retention_task: asyncio.Task | None = None


def dated_log_filename(day: date) -> str:
    """Nom du fichier de log applicatif du jour donné."""
    return f"wourri-{day.isoformat()}.log"


def monthly_feedback_filename(day: date) -> str:
    """Nom du fichier feedback du mois du jour donné."""
    return f"feedback-{day.year:04d}-{day.month:02d}.jsonl"


def _last_day_of_month(year: int, month: int) -> date:
    """Dernier jour du mois — âge de référence d'un fichier mensuel."""
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _parse_date(y: str, m: str, d: str) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def purge_old_logs(
    log_dir: str | Path,
    *,
    log_retention_days: int,
    feedback_retention_days: int,
    today: date | None = None,
    dry_run: bool = False,
) -> list[Path]:
    """Supprime les fichiers de log au-delà de leur rétention (ADR-0025).

    Args:
        log_dir: dossier des logs (``logs/`` du repo, ``/app/logs`` en prod).
        log_retention_days: rétention des logs applicatifs (jours).
        feedback_retention_days: rétention des feedbacks pseudonymisés (jours).
        today: date de référence (injectable pour les tests ; défaut = aujourd'hui).
        dry_run: si True, liste les fichiers candidats sans les supprimer.

    Returns:
        Liste des fichiers supprimés (ou candidats en dry_run). Le fichier du
        jour/mois courant n'est jamais candidat (comparaison stricte).
    """
    log_path = Path(log_dir)
    if not log_path.is_dir():
        return []

    today = today or date.today()
    log_cutoff = today - timedelta(days=log_retention_days)
    feedback_cutoff = today - timedelta(days=feedback_retention_days)
    now = time.time()

    to_delete: list[Path] = []
    for f in log_path.iterdir():
        if not f.is_file():
            continue
        name = f.name

        if m := _DATED_LOG_RE.match(name):
            file_day = _parse_date(*m.groups())
            if file_day and file_day < log_cutoff:
                to_delete.append(f)
        elif m := _MONTHLY_FEEDBACK_RE.match(name):
            month_end = None
            try:
                month_end = _last_day_of_month(int(m.group(1)), int(m.group(2)))
            except ValueError:
                pass  # mois invalide (ex: 99) → ignoré
            if month_end and month_end < feedback_cutoff:
                to_delete.append(f)
        elif name == _LEGACY_LOG:
            if now - f.stat().st_mtime > log_retention_days * 24 * 3600:
                to_delete.append(f)
        elif name == _LEGACY_FEEDBACK:
            if now - f.stat().st_mtime > feedback_retention_days * 24 * 3600:
                to_delete.append(f)

    deleted: list[Path] = []
    for f in to_delete:
        if dry_run:
            deleted.append(f)
            continue
        try:
            f.unlink()
            deleted.append(f)
        except OSError:
            # Fichier déjà supprimé (purge concurrente de l'autre worker) ou
            # verrouillé (Windows) : la prochaine passe le reprendra.
            pass

    if deleted and not dry_run:
        logger.info(
            "[RETENTION] %d fichier(s) de log purgé(s) (ADR-0025) : %s",
            len(deleted),
            ", ".join(f.name for f in deleted),
        )
    return deleted


def _purge_from_settings(log_dir: str | Path) -> list[Path]:
    """Purge avec les rétentions lues depuis Settings (usage scheduler)."""
    from app.config import get_settings

    s = get_settings()
    return purge_old_logs(
        log_dir,
        log_retention_days=s.log_retention_days,
        feedback_retention_days=s.feedback_retention_days,
    )


async def _retention_loop(log_dir: str | Path) -> None:
    """Boucle de purge toutes les 24 h."""
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            await asyncio.to_thread(_purge_from_settings, log_dir)
        except Exception:
            logger.exception("[RETENTION] Échec de la purge des logs")


def start_log_retention_scheduler(log_dir: str | Path) -> None:
    """Purge immédiate + planification 24 h.
    À appeler dans le lifespan FastAPI (idempotent entre workers).
    """
    global _retention_task
    try:
        _purge_from_settings(log_dir)
    except Exception:
        logger.exception("[RETENTION] Échec de la purge initiale des logs")
    _retention_task = asyncio.create_task(_retention_loop(log_dir))
    logger.info("[RETENTION] Planificateur de purge des logs actif (24h, ADR-0025)")


def stop_log_retention_scheduler() -> None:
    """Annule la tâche de purge (graceful shutdown)."""
    global _retention_task
    if _retention_task and not _retention_task.done():
        _retention_task.cancel()
    _retention_task = None
