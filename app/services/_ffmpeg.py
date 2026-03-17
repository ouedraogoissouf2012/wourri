"""
WOURI — Utilitaire FFmpeg centralisé

Résolution du chemin FFmpeg dans cet ordre :
  1. Variable d'environnement FFMPEG_PATH
  2. Commande 'ffmpeg' dans le PATH système (Linux/Mac/Windows avec ffmpeg installé)

Configuration dans .env :
  FFMPEG_PATH=/usr/bin/ffmpeg          # Linux
  FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe # Windows (si pas dans PATH)
"""
import os
import subprocess


def find_ffmpeg() -> str:
    """Retourne le chemin ffmpeg utilisable sur ce système.

    Cherche d'abord FFMPEG_PATH dans l'environnement, puis 'ffmpeg' dans le PATH.
    Lève RuntimeError si ffmpeg est introuvable.
    """
    candidates = []

    env_path = os.getenv("FFMPEG_PATH", "").strip()
    if env_path:
        candidates.append(env_path)

    candidates.append("ffmpeg")

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "-version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    raise RuntimeError(
        "FFmpeg introuvable. Installez ffmpeg et ajoutez-le au PATH, "
        "ou configurez FFMPEG_PATH dans .env."
    )


# Cache — résolu une seule fois au démarrage
_ffmpeg_path: str | None = None


def get_ffmpeg() -> str:
    """Version cachée de find_ffmpeg() — résout une seule fois."""
    global _ffmpeg_path
    if _ffmpeg_path is None:
        _ffmpeg_path = find_ffmpeg()
    return _ffmpeg_path
