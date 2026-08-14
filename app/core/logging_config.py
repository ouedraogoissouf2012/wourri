"""
WOURI - Configuration logging centralisee.

Remplace tous les print() par un logger structure avec niveaux.
Usage dans chaque fichier :
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[ASR] Transcription: '%s'", text)
"""
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable

from app.core.log_retention import dated_log_filename


class DatedFileHandler(logging.FileHandler):
    """FileHandler écrivant dans le fichier du jour (`wourri-YYYY-MM-DD.log`).

    Au changement de date, réouvre simplement le fichier du nouveau jour —
    AUCUN rename de rotation. C'est ce qui rend le handler sûr avec les
    2 workers uvicorn de prod (Dockerfile.prod) : chaque process append dans
    le même fichier du jour, comme un FileHandler classique (ADR-0025).
    La purge des anciens fichiers est assurée par app/core/log_retention.py.
    """

    def __init__(self, log_dir: str | Path, today_fn: Callable[[], date] = date.today):
        # Résolu UNE fois à l'init (comme FileHandler.baseFilename via abspath,
        # cf. stdlib) : un os.chdir() ultérieur ne déplace pas les logs.
        self._log_dir = Path(os.path.abspath(os.fspath(log_dir)))
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._today_fn = today_fn
        self._current_day = today_fn()
        super().__init__(
            self._log_dir / dated_log_filename(self._current_day),
            mode="a",
            encoding="utf-8",
        )

    def emit(self, record: logging.LogRecord) -> None:
        # handle() détient déjà le verrou (RLock) du handler → la bascule de
        # fichier est atomique vis-à-vis des autres threads du process.
        try:
            day = self._today_fn()
            if day != self._current_day:
                if self.stream:
                    self.stream.close()
                    self.stream = None
                self.baseFilename = os.fspath(self._log_dir / dated_log_filename(day))
                # Engagé APRÈS la bascule réussie : si close() lève (ENOSPC,
                # verrou), le jour n'est pas avancé et la bascule sera
                # retentée au prochain emit (close d'un stream fermé = no-op).
                self._current_day = day
        except Exception:
            # Convention stdlib (cf. BaseRotatingHandler.emit) : les erreurs
            # de rotation passent par handleError, jamais chez l'appelant.
            self.handleError(record)
            return
        super().emit(record)  # FileHandler réouvre le stream si None


def setup_logging(log_level: str = "INFO", log_dir: str | None = None) -> None:
    """Configure le logging pour toute l'application.

    - Console : format lisible avec couleurs (niveau, module, message)
    - Fichier  : format complet avec timestamp (si log_dir fourni),
      un fichier par jour purgé selon ADR-0025 (issue #215)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Format console : concis, lisible
    console_fmt = logging.Formatter(
        fmt="%(levelname)-8s %(name)s — %(message)s",
    )

    # Format fichier : complet avec timestamp
    file_fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Eviter les doublons si setup_logging() est appele plusieurs fois (--reload)
    # On verifie la presence de NOTRE handler (pas ceux de pytest ou autres)
    _MARKER = "_wourri_logging_configured"
    if getattr(root, _MARKER, False):
        return
    setattr(root, _MARKER, True)

    # Handler console
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(console_fmt)
    root.addHandler(console)

    # Handler fichier (optionnel) — un fichier par jour, purgé selon la
    # politique de rétention (issue #215, ADR-0025).
    if log_dir:
        file_handler = DatedFileHandler(log_dir)
        file_handler.setLevel(level)
        file_handler.setFormatter(file_fmt)
        root.addHandler(file_handler)

    # Reduire le bruit des librairies tierces
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("nemo_logger").setLevel(logging.WARNING)
    logging.getLogger("pytorch_lightning").setLevel(logging.WARNING)

    root.info("Logging configure: level=%s, fichier=%s", log_level, log_dir or "non")
