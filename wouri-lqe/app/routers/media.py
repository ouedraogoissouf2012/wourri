"""Lecture des médias audio de l'atelier (ADR-0034 P3)."""
import os

from fastapi import APIRouter, Depends, HTTPException, Response

from app.routers.session import current_user
from app.services.audio_store import LocalAudioStore

router = APIRouter(prefix="/media")

_MIME = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}


@router.get("/{name}")
def get_media(name: str, _: dict = Depends(current_user)):
    """Sert un audio par son nom de fichier (référence `audio/<name>`, session requise)."""
    try:
        data = LocalAudioStore().load("audio/" + name)
    except OSError:
        raise HTTPException(status_code=404, detail="not_found")
    ext = os.path.splitext(name)[1].lower()
    return Response(content=data, media_type=_MIME.get(ext, "application/octet-stream"))
