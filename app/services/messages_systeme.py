"""Messages système validés d'une langue (ADR-0049).

Un **message système** est une phrase que Wourri prononce de lui-même : le repli
quand il n'a pas compris, l'accusé d'escalade, la salutation. Aucune question de
l'agriculteur ne le déclenche par ressemblance — ce n'est donc pas une entrée de
corpus, et il lui faut sa propre source.

Jusqu'ici ces phrases étaient **en français, en dur dans le code**, pour le baoulé
comme pour le dioula (dette tracée par ADR-0039 puis ADR-0043). Elles vivent
désormais dans `dictionnaires/messages_systeme_<langue>.json`, construit depuis ce
que le locuteur natif a validé dans l'atelier. Rien n'est inventé (ADR-0031).

Format ::

    {
     "version": "bci-2026-11-03",
     "langue": "bci",
     "messages": {
       "_SYSTEME_REPLI": {
         "texte":    "<phrase validée dans la langue>",
         "texte_fr": "<sa traduction française>",
         "audio":    "audio/<uuid>.webm"     // facultatif
       }
     }
    }

**L'audio est facultatif, et c'est voulu.** Le baoulé n'a pas de synthèse vocale :
sa voix est un enregistrement du locuteur, publié par `scripts/publier_audios.py`.
Le dioula, lui, a un TTS. Imposer une seule source d'audio forcerait l'un des deux
cas ; le fichier porte donc l'enregistrement quand il existe, et l'appelant reste
libre de synthétiser quand sa langue sait le faire.

**Dégradation définie** (ADR-0049) : sans message validé pour la langue, l'appelant
sert le français. Jamais un texte généré, jamais une langue voisine — une tournure
dioula n'est pas du baoulé (ADR-0046).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

DOSSIER = Path(__file__).resolve().parents[2] / "dictionnaires"

# Rôles connus. Les identifiants sont ceux du catalogue assignable : un message
# système est produit comme n'importe quel contenu de l'atelier.
REPLI = "_SYSTEME_REPLI"
SALUTATION = "_SYSTEME_SALUTATION"
HORS_SUJET = "_SYSTEME_HORS_SUJET"


class MessageSysteme(NamedTuple):
    texte: str          # la phrase dans la langue, validée par le locuteur
    texte_fr: str       # sa traduction, servie en complément écrit
    audio: Optional[str]  # référence d'atelier (`audio/<uuid>.<ext>`), ou None


def _chemin(langue: str) -> Path:
    return DOSSIER / f"messages_systeme_{(langue or '').strip().lower()}.json"


@lru_cache(maxsize=8)
def _charger(chemin: str) -> dict:
    """Messages d'un fichier. Un fichier absent n'est pas une erreur : la langue
    n'a simplement pas encore de message validé, et l'appelant sert le français."""
    p = Path(chemin)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Un fichier illisible ne doit jamais priver l'agriculteur de sa réponse :
        # on retombe sur le français, en le disant dans les journaux.
        logger.error("[MSG-SYS] %s illisible (%s) — repli français", p.name, exc)
        return {}
    return data.get("messages") or {}


def message(langue: str, role: str) -> Optional[MessageSysteme]:
    """Message validé de `langue` pour ce `role`, ou None s'il n'y en a pas."""
    brut = _charger(str(_chemin(langue))).get(role)
    if not isinstance(brut, dict):
        return None
    texte = (brut.get("texte") or "").strip()
    if not texte:
        # Une entrée sans texte ne sert à rien : mieux vaut le français que du vide.
        return None
    audio = (brut.get("audio") or "").strip() or None
    return MessageSysteme(texte=texte, texte_fr=(brut.get("texte_fr") or "").strip(), audio=audio)


def url_audio(message_: MessageSysteme, base: str) -> Optional[str]:
    """URL servie pour l'enregistrement, selon la convention du serveur voix.

    Même règle que pour les réponses du corpus : `<base>/<stem>.ogg`. C'est ce que
    `scripts/publier_audios.py` publie — les deux côtés doivent rester d'accord.
    """
    base = (base or "").rstrip("/")
    if not base or not message_.audio:
        return None
    return f"{base}/{PurePosixPath(message_.audio).stem}.ogg"


def vider_cache() -> None:
    """Oublie les fichiers lus (tests, et rechargement sans redémarrage)."""
    _charger.cache_clear()
