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

Convention d'horloge : tous les noms de fichiers et les bornes de purge
utilisent la DATE LOCALE du process (`date.today()`). En prod, les conteneurs
sont en TZ=UTC (docker-compose) → dates UTC ; en dev, date locale du poste.
Une seule horloge partout : writer, handler et purge restent alignés.

Le nommage par date évite tout rename de rotation : les 2 workers uvicorn
écrivent le même fichier du jour en append, sans course. La purge est une
suppression de fichiers entiers — idempotente, exécutable par chaque worker.

Planification : scheduler 24 h démarré dans le lifespan FastAPI (même pattern
que app/services/audio_cleanup.py) + script ops scripts/purge_logs.py.
Désactivable via LOG_RETENTION_ENABLED=false (suite de tests, gel ops).
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Valeurs par défaut de la politique (ADR-0025) — source unique partagée par
# app/config.py (Settings) et scripts/purge_logs.py (CLI sans import Settings).
DEFAULT_LOG_RETENTION_DAYS = 30
DEFAULT_FEEDBACK_RETENTION_DAYS = 365

# Dossier logs/ canonique du repo (= /app/logs en conteneur). Source unique
# pour main.py (handler + scheduler), feedback.py (writer), rapport_c5.py et
# scripts/purge_logs.py : la conformité exige que writer et purge visent le
# MÊME dossier.
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

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


def feedback_log_files(log_dir: str | Path) -> list[Path]:
    """Fichiers feedback à lire, du plus ancien au plus récent.

    Contrat de nommage unique pour les consommateurs (rapport_c5.py) :
    l'éventuel legacy `feedback.jsonl` d'abord, puis les fichiers mensuels
    STRICTEMENT conformes à `feedback-YYYY-MM.jsonl` (un glob permissif
    compterait double un `feedback-2025-07.bak.jsonl` que la purge, elle,
    ignorerait).
    """
    log_path = Path(log_dir)
    if not log_path.is_dir():
        return []
    files = [f for f in sorted(log_path.iterdir())
             if f.is_file() and _MONTHLY_FEEDBACK_RE.match(f.name)]
    legacy = log_path / _LEGACY_FEEDBACK
    if legacy.is_file():
        files.insert(0, legacy)
    return files


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
        log_retention_days: rétention des logs applicatifs (jours, ≥ 0).
        feedback_retention_days: rétention des feedbacks pseudonymisés (jours, ≥ 0).
        today: date de référence (injectable pour les tests ; défaut = aujourd'hui).
            S'applique aussi aux fichiers legacy (cutoff mtime = minuit de
            ``today - rétention``).
        dry_run: si True, liste les fichiers candidats sans les supprimer.

    Returns:
        Liste des fichiers supprimés (ou candidats en dry_run). Le fichier du
        jour/mois courant n'est jamais candidat (comparaison stricte).

    Raises:
        ValueError: si une rétention est négative — un cutoff dans le futur
            rendrait le fichier du jour candidat (perte des logs actifs).
    """
    if log_retention_days < 0 or feedback_retention_days < 0:
        raise ValueError(
            "Rétention négative interdite (le fichier du jour deviendrait "
            f"candidat) : log={log_retention_days}, feedback={feedback_retention_days}"
        )

    log_path = Path(log_dir)
    if not log_path.is_dir():
        return []

    today = today or date.today()
    log_cutoff = today - timedelta(days=log_retention_days)
    feedback_cutoff = today - timedelta(days=feedback_retention_days)
    # Cutoff mtime des legacy : minuit LOCAL du jour de cutoff — même horloge
    # que date.today(), et déterministe vis-à-vis du paramètre `today`.
    log_mtime_cutoff = datetime.combine(log_cutoff, time.min).timestamp()
    feedback_mtime_cutoff = datetime.combine(feedback_cutoff, time.min).timestamp()

    to_delete: list[Path] = []
    for f in log_path.iterdir():
        # Chaque fichier est évalué sous protection OSError : l'autre worker
        # (ou un opérateur) peut le supprimer entre iterdir() et stat().
        try:
            if not f.is_file():
                continue
            name = f.name

            if m := _DATED_LOG_RE.match(name):
                file_day = _parse_date(*m.groups())
                if file_day and file_day < log_cutoff:
                    to_delete.append(f)
            elif m := _MONTHLY_FEEDBACK_RE.match(name):
                # Valide le mois via date() (rejette 00 comme 13/99) avant de
                # calculer la fin de mois.
                first_day = _parse_date(m.group(1), m.group(2), "1")
                if first_day is None:
                    continue
                month_end = _last_day_of_month(first_day.year, first_day.month)
                if month_end < feedback_cutoff:
                    to_delete.append(f)
            elif name == _LEGACY_LOG:
                if f.stat().st_mtime < log_mtime_cutoff:
                    to_delete.append(f)
            elif name == _LEGACY_FEEDBACK:
                if f.stat().st_mtime < feedback_mtime_cutoff:
                    to_delete.append(f)
        except OSError:
            continue  # disparu/inaccessible pendant le scan → passe suivante

    deleted: list[Path] = []
    for f in to_delete:
        if dry_run:
            deleted.append(f)
            continue
        try:
            f.unlink()
            deleted.append(f)
        except OSError as e:
            # Purge concurrente de l'autre worker (déjà supprimé) ou fichier
            # verrouillé (Windows). Tracé : un fichier PII qui resterait
            # insupprimable au-delà de la rétention doit se voir (ARTCI).
            logger.warning("[RETENTION] Impossible de purger %s : %s", f.name, e)

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
    No-op si LOG_RETENTION_ENABLED=false (tests, gel ops).
    """
    global _retention_task
    from app.config import get_settings

    if not get_settings().log_retention_enabled:
        logger.info("[RETENTION] Purge désactivée (LOG_RETENTION_ENABLED=false)")
        return
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
