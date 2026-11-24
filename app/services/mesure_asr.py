"""Mesure de chaque transcription (#650) : ce que coûte l'ASR, pour quel audio.

Vit HORS de `app/services/asr/` (gelé) : le routeur enveloppe `chain.transcribe` sans entrer
dans la chaîne. Conséquence déclarée : ni le fournisseur retenu ni l'usage du repli ne
sont mesurés ici — la chaîne ne les expose pas.

La durée de l'audio est LUE dans l'en-tête Ogg Opus, jamais estimée depuis la taille : le
débit d'un vocal WhatsApp réel n'est pas mesuré (les .ogg du dépôt, encodés par ffmpeg,
font ~8,5 Ko/s ; l'issue annonce 1 à 2 Ko/s pour WhatsApp). La taille brute est journalisée
à côté. Hors Ogg Opus lisible : « inconnue ».

Une ligne par transcription, faite pour être agrégée (`grep` puis découpage) :
    [ASR-MESURE] endpoint=… langue=… extension=… octets=… duree_audio_s=… duree_appel_s=…
    rapport=… resultat=texte|vide|aucun|exception
"""
from __future__ import annotations

import logging
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)

PREFIXE = "[ASR-MESURE] "
_PAGE = b"OggS"
_ENTETE_OPUS = b"OpusHead"
_HORLOGE_OPUS = 48_000  # le granule Opus compte toujours en échantillons à 48 kHz (RFC 7845)


def duree_ogg_opus(octets: bytes) -> Optional[float]:
    """Durée en secondes d'un Ogg Opus, lue sans décoder ; None si elle ne peut pas l'être.

    Durée = granule de la dernière page qui en porte un, moins le pre-skip de l'OpusHead.
    Un fichier réduit à ses pages d'en-tête (granule 0) n'a pas de durée connue.
    """
    try:
        if not octets.startswith(_PAGE):
            return None
        entete = octets.find(_ENTETE_OPUS)
        if entete < 0:
            return None
        pre_skip = struct.unpack_from("<H", octets, entete + 10)[0]
        page = octets.rfind(_PAGE)
        while page >= 0:
            granule = struct.unpack_from("<q", octets, page + 6)[0]
            if octets[page + 4] == 0 and granule >= 0:  # version 0 ; -1 = page sans fin de paquet
                echantillons = granule - pre_skip
                return echantillons / _HORLOGE_OPUS if echantillons > 0 else None
            page = octets.rfind(_PAGE, 0, page)
    except struct.error:  # en-tête tronqué
        return None
    return None


def _resultat(transcription: Optional[str]) -> str:
    if transcription is None:
        return "aucun"
    return "texte" if transcription.strip() else "vide"


async def transcrire_mesure(chain, audio_bytes: bytes, extension: str, *, endpoint: str,
                            langue: str) -> Optional[str]:
    """`chain.transcribe(audio_bytes, extension)`, inchangé, plus une ligne de mesure."""
    debut = time.perf_counter()
    resultat = "exception"
    try:
        transcription = await chain.transcribe(audio_bytes, extension)
        resultat = _resultat(transcription)
        return transcription
    finally:
        duree_appel = time.perf_counter() - debut
        duree_audio = duree_ogg_opus(audio_bytes)
        logger.info(
            "%sendpoint=%s langue=%s extension=%s octets=%d duree_audio_s=%s duree_appel_s=%.2f "
            "rapport=%s resultat=%s",
            PREFIXE, endpoint, langue, extension or "inconnue", len(audio_bytes),
            f"{duree_audio:.2f}" if duree_audio else "inconnue", duree_appel,
            f"{duree_appel / duree_audio:.2f}" if duree_audio else "inconnu", resultat,
        )
