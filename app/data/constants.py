"""
WOURI - Source unique pour les villes et langues ivoiriennes.

TOUTES les définitions de villes et langues doivent être importées depuis ce fichier.
Aucun autre fichier ne doit contenir de listes hardcodées de villes ou langues.

Usage :
    from app.data.constants import IVORIAN_CITY_NAMES, SUPPORTED_LANGUAGES, LANGUAGE_ALIASES
"""
from app.data.cities import IVORIAN_CITIES


# ---------------------------------------------------------------------------
# VILLES — dérivées de cities.py (source avec coordonnées)
# ---------------------------------------------------------------------------

IVORIAN_CITY_NAMES: list[str] = sorted(IVORIAN_CITIES.keys())
"""Liste simple des 60 noms de villes CI (pour protection NLLB, prompts Whisper, etc.)."""


# ---------------------------------------------------------------------------
# LANGUES IVOIRIENNES — source unique pour ASR, TTS, et schemas
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: dict[str, dict] = {
    "bam": {
        "display_name": "Bambara/Dioula",
        "iso_code": "bam",
        "tts_model": "facebook/mms-tts-bam",
        "nllb_code": "bam_Latn",
    },
    "ati": {
        "display_name": "Attié",
        "iso_code": "ati",
        "tts_model": "facebook/mms-tts-ati",
        "nllb_code": None,
    },
    "dyi": {
        "display_name": "Sénoufo Djimini",
        "iso_code": "dyi",
        "tts_model": "facebook/mms-tts-dyi",
        "nllb_code": None,
    },
    "myk": {
        "display_name": "Sénoufo Mamara",
        "iso_code": "myk",
        "tts_model": "facebook/mms-tts-myk",
        "nllb_code": None,
    },
    "gud": {
        "display_name": "Dida Yocoboué",
        "iso_code": "gud",
        "tts_model": "facebook/mms-tts-gud",
        "nllb_code": None,
    },
    "adj": {
        "display_name": "Adioukrou",
        "iso_code": "adj",
        "tts_model": "facebook/mms-tts-adj",
        "nllb_code": None,
    },
    "dnj": {
        "display_name": "Dan/Yacouba",
        "iso_code": "dnj",
        "tts_model": "facebook/mms-tts-dnj",
        "nllb_code": None,
    },
    "wob": {
        "display_name": "Wobé",
        "iso_code": "wob",
        "tts_model": "facebook/mms-tts-wob",
        "nllb_code": None,
    },
}

LANGUAGE_ALIASES: dict[str, str] = {
    "bambara": "bam",
    "dioula": "bam",
    "jula": "bam",
    "attie": "ati",
    "senoufo": "dyi",
    "senoufo_djimini": "dyi",
    "senoufo_mamara": "myk",
    "dida": "gud",
    "adioukrou": "adj",
    "dan": "dnj",
    "yacouba": "dnj",
    "wobe": "wob",
}


# ---------------------------------------------------------------------------
# Helpers dérivés — pour compatibilité avec l'ancien format
# ---------------------------------------------------------------------------

def get_asr_languages() -> dict[str, tuple[str, str]]:
    """Retourne le format attendu par asr_ivorian.py : {code: (display_name, iso_code)}."""
    return {
        code: (lang["display_name"], lang["iso_code"])
        for code, lang in SUPPORTED_LANGUAGES.items()
    }


def get_tts_languages() -> dict[str, tuple[str, str, str | None]]:
    """Retourne le format attendu par tts_ivoirian.py : {code: (display_name, tts_model, nllb_code)}."""
    return {
        code: (lang["display_name"], lang["tts_model"], lang["nllb_code"])
        for code, lang in SUPPORTED_LANGUAGES.items()
    }


def resolve_language_alias(name: str) -> str | None:
    """Résout un alias de langue vers son code. Retourne None si non trouvé."""
    name_lower = name.lower().strip()
    if name_lower in SUPPORTED_LANGUAGES:
        return name_lower
    return LANGUAGE_ALIASES.get(name_lower)
