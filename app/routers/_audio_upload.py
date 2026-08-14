"""WOURI - Helpers partagés de validation d'upload audio (#312).

Factorise le code dupliqué entre les routes ASR (`/api/asr/transcribe` et
`/api/asr/transcribe-and-translate`) qui partageaient ~35 lignes identiques
(lecture, gardes taille/vide, résolution d'extension). Les constantes de limite
sont aussi partagées avec `stt.py` (source unique).
"""
from __future__ import annotations

from fastapi import HTTPException, UploadFile

# Taille max d'un upload audio. Source unique partagée par les routes asr.py et
# stt.py (avant #312 : `10 * 1024 * 1024` recopié à 3 endroits). Publique : elle
# traverse les frontières de module (importée par stt.py).
MAX_AUDIO_BYTES: int = 10 * 1024 * 1024

# Extensions audio reconnues par la chaîne ASR. Toute extension hors liste est
# repliée sur "ogg" (défaut historique des vocaux WhatsApp).
ALLOWED_EXTENSIONS: tuple[str, ...] = ("wav", "ogg", "mp3", "webm", "m4a")

_DEFAULT_EXTENSION = "ogg"


async def read_audio_within_limits(audio: UploadFile) -> bytes:
    """Lit un upload audio en validant taille et non-vacuité.

    Gardes (dans l'ordre) :
      - lecture → 400 si l'I/O échoue,
      - taille > _MAX_AUDIO_BYTES → 413,
      - contenu vide → 400.

    Returns:
        Les octets bruts de l'audio.

    Raises:
        HTTPException: 400 (lecture / vide) ou 413 (trop volumineux).
    """
    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Fichier audio trop volumineux (max 10 MB)")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    return audio_bytes


def resolve_extension(filename: str | None) -> str:
    """Extrait une extension audio normalisée du nom de fichier.

    Replie sur `_DEFAULT_EXTENSION` ("ogg") si le nom est absent ou porte une
    extension hors `_ALLOWED_EXTENSIONS`.
    """
    name = filename or f"audio.{_DEFAULT_EXTENSION}"
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else _DEFAULT_EXTENSION
    if extension not in ALLOWED_EXTENSIONS:
        extension = _DEFAULT_EXTENSION
    return extension
