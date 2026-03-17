"""
WOURI — Utilitaire FFmpeg centralisé

Résolution du chemin FFmpeg dans cet ordre :
  1. Variable d'environnement FFMPEG_PATH
  2. Commande 'ffmpeg' dans le PATH système (Linux/Mac/Windows avec ffmpeg installé)

Configuration dans .env :
  FFMPEG_PATH=/usr/bin/ffmpeg          # Linux
  FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe # Windows (si pas dans PATH)
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


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


# ── loudnorm support ──────────────────────────────────────────────────────────
# Vérifie une seule fois si ffmpeg supporte le filtre loudnorm (ebur128)
_loudnorm_supported: bool | None = None


def _check_loudnorm_support(ffmpeg: str) -> bool:
    """Retourne True si ffmpeg dispose du filtre loudnorm."""
    global _loudnorm_supported
    if _loudnorm_supported is not None:
        return _loudnorm_supported
    try:
        result = subprocess.run(
            [ffmpeg, "-filters"],
            capture_output=True, text=True, timeout=5,
        )
        _loudnorm_supported = "loudnorm" in result.stdout
    except Exception:
        _loudnorm_supported = False
    return _loudnorm_supported


def wav_to_ogg_normalized(wav_path: str, ogg_path: str) -> bool:
    """Convertit WAV → OGG Opus avec normalisation loudnorm EBU R128.

    Pipeline audio :
      1. loudnorm I=-16 TP=-1.5 LRA=11  — volume perçu homogène (standard podcast/radio)
      2. libopus 64k VBR                — codec WhatsApp compatible

    Si loudnorm n'est pas disponible (ffmpeg léger), conversion directe sans filtre.
    Retourne True si le fichier OGG a été créé avec succès.
    """
    try:
        ffmpeg = get_ffmpeg()
    except RuntimeError as e:
        logger.error("[AUDIO] %s", e)
        return False

    use_loudnorm = _check_loudnorm_support(ffmpeg)

    # Construire la commande ffmpeg
    cmd = [ffmpeg, "-y", "-i", wav_path]
    if use_loudnorm:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    cmd += ["-c:a", "libopus", "-b:a", "64k", "-vbr", "on", "-compression_level", "10", ogg_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 0:
            try:
                os.remove(wav_path)
            except OSError:
                pass
            logger.debug("[AUDIO] OGG généré%s : %s", " (loudnorm)" if use_loudnorm else "", ogg_path)
            return True
        logger.warning("[AUDIO] ffmpeg rc=%d : %s", result.returncode, result.stderr[-200:])
    except subprocess.TimeoutExpired:
        logger.error("[AUDIO] ffmpeg timeout sur %s", wav_path)
    except Exception as e:
        logger.error("[AUDIO] ffmpeg erreur : %s", e)

    return False
