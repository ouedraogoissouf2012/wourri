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
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_dir: str | None = None) -> None:
    """Configure le logging pour toute l'application.

    - Console : format lisible avec couleurs (niveau, module, message)
    - Fichier  : format complet avec timestamp (si log_dir fourni)
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

    # Handler fichier (optionnel)
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path / "wourri.log",
            encoding="utf-8",
            mode="a",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(file_fmt)
        root.addHandler(file_handler)

    # Reduire le bruit des librairies tierces
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("nemo_logger").setLevel(logging.WARNING)
    logging.getLogger("pytorch_lightning").setLevel(logging.WARNING)

    root.info("Logging configure: level=%s, fichier=%s", log_level, log_dir or "non")
