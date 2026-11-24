"""Controles communs d'un audio envoye a l'atelier : la dictee et la voix d'une fiche
(ADR-0035, ADR-0045 revision du 2026-11-24).

Une seule definition des formats et de la taille admis : deux limites qui divergeraient
feraient accepter un fichier d'un cote et refuser de l'autre, sans que personne ne
comprenne pourquoi.
"""
from __future__ import annotations

from fastapi import UploadFile

ALLOWED_AUDIO = frozenset({"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4"})
MAX_AUDIO = 15_000_000  # octets


class AudioRefuse(ValueError):
    """L'audio envoye est refuse ; `detail` est le code renvoye au client."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def lire_audio(upload: UploadFile) -> tuple[bytes, str]:
    """Octets et type MIME (sans parametres) d'un audio envoye, ou `AudioRefuse`.

    Le type est lu avant les octets : un format refuse ne coute pas la lecture du corps.
    Le navigateur envoie souvent `audio/webm;codecs=opus` : les parametres sont ignores."""
    mime = (upload.content_type or "audio/webm").split(";")[0].strip()
    if mime not in ALLOWED_AUDIO:
        raise AudioRefuse("format_audio_non_supporte")
    raw = await upload.read()
    if not raw:
        raise AudioRefuse("audio_vide")
    if len(raw) > MAX_AUDIO:
        raise AudioRefuse("audio_trop_grand")
    return raw, mime
