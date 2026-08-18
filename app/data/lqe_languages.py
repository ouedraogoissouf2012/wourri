"""Langues LQE (atelier validation) — distinctes du chat WhatsApp.

ADR-0031 : 1 compte = 1 langue. Nouvelle langue = entrée ici + org console,
pas un if métier dans le handler dioula.

Codes :
- dyu : dioula CI (pilote)
- bci : baoulé (ISO 639-3 Baoulé — validé Issouf #443)
"""
from __future__ import annotations

LQE_LANGUAGES: dict[str, dict[str, str]] = {
    "dyu": {
        "code": "dyu",
        "display_name": "Dioula (Côte d'Ivoire)",
        "iso_639_3": "dyu",
        "role": "pilot",
    },
    "bci": {
        "code": "bci",
        "display_name": "Baoulé",
        "iso_639_3": "bci",
        "role": "provider_upload",
    },
}

BAOULE_CODE = "bci"


def is_lqe_language(code: str) -> bool:
    return (code or "").strip().lower() in LQE_LANGUAGES
