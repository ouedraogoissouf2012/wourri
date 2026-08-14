"""Tests de la rétention/purge des logs PII (issue #215, ADR-0025).

Contrats testés :
- Nommage daté : `wourri-YYYY-MM-DD.log` (quotidien), `feedback-YYYY-MM.jsonl`
  (mensuel) — aucun rename, append-only (sûr avec 2 workers uvicorn).
- `purge_old_logs()` supprime les fichiers datés au-delà de la rétention,
  les fichiers legacy (`wourri.log`, `feedback.jsonl`) sur leur mtime,
  ignore les noms invalides, ne touche jamais le fichier du jour.
- `--dry-run` liste sans supprimer.
- `DatedFileHandler` bascule sur le fichier du nouveau jour sans rename.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta

from app.core.log_retention import (
    dated_log_filename,
    monthly_feedback_filename,
    purge_old_logs,
)
from app.core.logging_config import DatedFileHandler

TODAY = date(2026, 8, 14)


# ─────────────────────────────────────────────
# Nommage
# ─────────────────────────────────────────────


def test_dated_log_filename_format():
    assert dated_log_filename(date(2026, 8, 14)) == "wourri-2026-08-14.log"


def test_monthly_feedback_filename_format():
    assert monthly_feedback_filename(date(2026, 8, 14)) == "feedback-2026-08.jsonl"


# ─────────────────────────────────────────────
# purge_old_logs — logs applicatifs datés
# ─────────────────────────────────────────────


def _touch(path, content="x"):
    path.write_text(content, encoding="utf-8")
    return path


def test_purge_supprime_log_date_au_dela_retention(tmp_path):
    old = _touch(tmp_path / "wourri-2026-07-01.log")  # 44 j avant TODAY
    recent = _touch(tmp_path / "wourri-2026-08-01.log")  # 13 j avant TODAY

    deleted = purge_old_logs(
        tmp_path, log_retention_days=30, feedback_retention_days=365, today=TODAY
    )

    assert not old.exists()
    assert recent.exists()
    assert old in deleted


def test_purge_borne_stricte_30_jours(tmp_path):
    # Exactement 30 j → conservé (la purge cible STRICTEMENT > rétention)
    at_limit = _touch(tmp_path / f"wourri-{TODAY - timedelta(days=30)}.log")
    beyond = _touch(tmp_path / f"wourri-{TODAY - timedelta(days=31)}.log")

    purge_old_logs(
        tmp_path, log_retention_days=30, feedback_retention_days=365, today=TODAY
    )

    assert at_limit.exists()
    assert not beyond.exists()


def test_purge_ne_touche_jamais_le_fichier_du_jour(tmp_path):
    today_file = _touch(tmp_path / dated_log_filename(TODAY))

    purge_old_logs(
        tmp_path, log_retention_days=0, feedback_retention_days=0, today=TODAY
    )

    assert today_file.exists()


def test_purge_ignore_nom_invalide(tmp_path):
    invalid = _touch(tmp_path / "wourri-9999-99-99.log")
    other = _touch(tmp_path / "autre-fichier.txt")

    deleted = purge_old_logs(
        tmp_path, log_retention_days=30, feedback_retention_days=365, today=TODAY
    )

    assert invalid.exists()
    assert other.exists()
    assert deleted == []


def test_purge_dossier_absent_retourne_vide(tmp_path):
    assert (
        purge_old_logs(
            tmp_path / "inexistant",
            log_retention_days=30,
            feedback_retention_days=365,
            today=TODAY,
        )
        == []
    )


# ─────────────────────────────────────────────
# purge_old_logs — feedback mensuel
# ─────────────────────────────────────────────


def test_purge_feedback_mensuel_au_dela_retention(tmp_path):
    # Fin de mois 2025-07 = 2025-07-31, soit 379 j avant TODAY (> 365)
    old = _touch(tmp_path / "feedback-2025-07.jsonl")
    # Fin de mois 2025-09 = 2025-09-30, soit 318 j avant TODAY (< 365)
    recent = _touch(tmp_path / "feedback-2025-09.jsonl")
    current = _touch(tmp_path / monthly_feedback_filename(TODAY))

    purge_old_logs(
        tmp_path, log_retention_days=30, feedback_retention_days=365, today=TODAY
    )

    assert not old.exists()
    assert recent.exists()
    assert current.exists()


# ─────────────────────────────────────────────
# purge_old_logs — fichiers legacy (mtime)
# ─────────────────────────────────────────────


def test_purge_legacy_wourri_log_par_mtime(tmp_path):
    legacy = _touch(tmp_path / "wourri.log")
    vieux = time.time() - 31 * 24 * 3600
    os.utime(legacy, (vieux, vieux))

    purge_old_logs(
        tmp_path, log_retention_days=30, feedback_retention_days=365, today=TODAY
    )

    assert not legacy.exists()


def test_purge_legacy_recent_conserve(tmp_path):
    legacy_log = _touch(tmp_path / "wourri.log")  # mtime = maintenant
    legacy_fb = _touch(tmp_path / "feedback.jsonl")

    purge_old_logs(
        tmp_path, log_retention_days=30, feedback_retention_days=365, today=TODAY
    )

    assert legacy_log.exists()
    assert legacy_fb.exists()


# ─────────────────────────────────────────────
# dry-run
# ─────────────────────────────────────────────


def test_purge_dry_run_ne_supprime_rien(tmp_path):
    old = _touch(tmp_path / "wourri-2026-01-01.log")

    deleted = purge_old_logs(
        tmp_path,
        log_retention_days=30,
        feedback_retention_days=365,
        today=TODAY,
        dry_run=True,
    )

    assert old.exists()
    assert deleted == [old]


# ─────────────────────────────────────────────
# DatedFileHandler
# ─────────────────────────────────────────────


def _make_record(msg="hello"):
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_dated_handler_ecrit_dans_fichier_du_jour(tmp_path):
    handler = DatedFileHandler(tmp_path, today_fn=lambda: TODAY)
    handler.emit(_make_record("ligne1"))
    handler.close()

    content = (tmp_path / dated_log_filename(TODAY)).read_text(encoding="utf-8")
    assert "ligne1" in content


def test_dated_handler_bascule_au_changement_de_jour(tmp_path):
    jours = [TODAY, TODAY, TODAY + timedelta(days=1)]
    it = iter(jours)
    handler = DatedFileHandler(tmp_path, today_fn=lambda: next(it))

    handler.emit(_make_record("jour1"))
    handler.emit(_make_record("jour2"))
    handler.close()

    f1 = tmp_path / dated_log_filename(TODAY)
    f2 = tmp_path / dated_log_filename(TODAY + timedelta(days=1))
    assert "jour1" in f1.read_text(encoding="utf-8")
    assert "jour2" in f2.read_text(encoding="utf-8")
    assert "jour2" not in f1.read_text(encoding="utf-8")


def test_dated_handler_aucun_rename_append_seulement(tmp_path):
    """Le fichier du jour précédent reste intact après bascule (pas de rotation
    par rename → pas de course entre workers)."""
    jours = iter([TODAY, TODAY, TODAY + timedelta(days=1)])
    handler = DatedFileHandler(tmp_path, today_fn=lambda: next(jours))
    handler.emit(_make_record("avant"))
    contenu_avant = (tmp_path / dated_log_filename(TODAY)).read_text(encoding="utf-8")

    handler.emit(_make_record("apres"))
    handler.close()

    assert (tmp_path / dated_log_filename(TODAY)).read_text(encoding="utf-8") == contenu_avant
