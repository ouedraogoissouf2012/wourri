"""
WOURI - Router ASR (Automatic Speech Recognition)
Reconnaissance vocale pour langues ivoiriennes
Traduction disponible uniquement pour Bambara/Dioula via NLLB-200
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
import re
from app.services.asr_ivorian import (
    transcribe_audio_bytes,
    get_supported_asr_languages,
    check_asr_status,
    IVORIAN_ASR_LANGUAGES
)
from app.services.tts_bambara import translate_to_french

router = APIRouter(prefix="/api/asr", tags=["ASR"])


# Nettoyage post-ASR : l'ASR MMS-1B-ALL fait des erreurs phonétiques récurrentes
# Ces corrections sont appliquées AVANT la traduction BAM→FR
_ASR_FIXES = {
    # Salutations déformées par l'ASR (toutes les variantes observées)
    "sɔrɔma": "sɔgɔma",       # r/g confusion
    "sorɔma": "sɔgɔma",
    "soroma": "sogoma",
    "sɔrɔ ma": "sɔgɔma",
    "sagɔma": "sɔgɔma",       # a/ɔ confusion (vu dans les logs)
    "sagoma": "sogoma",         # a/o confusion
    "sɔgɔ ma": "sɔgɔma",     # espace parasite
    "sogo ma": "sogoma",
    # Mots avec 'n' parasite ajouté par l'ASR
    "malon": "malo",            # "riz" avec n parasite
    "kaban": "kaba",            # "maïs" avec n parasite
    "tigan": "tiga",            # "arachide" avec n parasite
    "foron": "foro",            # "champ" avec n parasite
    "senɛ": "sɛnɛ",           # voyelle e au lieu de ɛ
    # ka/kan confusion (très fréquent avec MMS-1B-ALL)
    " kan ": " ka ",            # "kan" → "ka" (marqueur verbal)
    # Salutations collées fréquentes
    "ani sɔgɔma": "i ni sɔgɔma",
    "ani sogoma": "i ni sogoma",
    "ani ce": "i ni ce",
}


def clean_asr_transcription(text: str) -> str:
    """Corrige les erreurs ASR courantes de MMS-1B-ALL pour le bambara."""
    if not text:
        return text
    result = f" {text} "  # Ajouter espaces pour matcher les limites de mots
    for wrong, correct in _ASR_FIXES.items():
        result = result.replace(wrong, correct)
    return result.strip()


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = Form(default="bam")
):
    """
    Transcrit un fichier audio en texte

    - **audio**: Fichier audio (WAV, OGG, MP3, WEBM)
    - **language**: Code de la langue (bam, ati, dyi, myk, gud, adj, dnj, wob)

    Langues disponibles pour ASR:
    - bam: Bambara/Dioula
    - ati: Attie
    - dyi: Senoufo Djimini
    - myk: Senoufo Mamara
    - gud: Dida Yocoboue
    - adj: Adioukrou
    - dnj: Dan/Yacouba
    - wob: Wobe
    """
    # Verifier la langue
    if language not in IVORIAN_ASR_LANGUAGES:
        supported = list(IVORIAN_ASR_LANGUAGES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Langue '{language}' non supportee. Langues disponibles: {supported}"
        )

    # Lire le fichier audio
    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    # Determiner l'extension
    filename = audio.filename or "audio.ogg"
    extension = filename.split(".")[-1].lower()
    if extension not in ["wav", "ogg", "mp3", "webm", "m4a"]:
        extension = "ogg"  # Default

    # Transcrire
    transcription = await transcribe_audio_bytes(audio_bytes, language, extension)

    if transcription is None:
        raise HTTPException(
            status_code=500,
            detail="Echec de la transcription. Verifiez que le modele ASR est charge."
        )

    lang_name = IVORIAN_ASR_LANGUAGES[language][0]

    return {
        "transcription": transcription,
        "language": language,
        "language_name": lang_name
    }


@router.post("/transcribe-and-translate")
async def transcribe_and_translate(
    audio: UploadFile = File(...),
    language: str = Form(default="bam")
):
    """
    Transcrit un fichier audio ET traduit en francais

    - **audio**: Fichier audio
    - **language**: Code de la langue source

    IMPORTANT: Traduction disponible UNIQUEMENT pour:
    - bam: Bambara/Dioula (via NLLB-200)

    Pour les autres langues (ati, dyi, myk, gud, adj, dnj, wob):
    - La transcription fonctionne (ASR)
    - Mais PAS de traduction vers le français disponible
    """
    # Verifier la langue
    if language not in IVORIAN_ASR_LANGUAGES:
        supported = list(IVORIAN_ASR_LANGUAGES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Langue '{language}' non supportee. Langues disponibles: {supported}"
        )

    # Lire le fichier audio
    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    # Determiner l'extension
    filename = audio.filename or "audio.ogg"
    extension = filename.split(".")[-1].lower()
    if extension not in ["wav", "ogg", "mp3", "webm", "m4a"]:
        extension = "ogg"

    # Transcrire
    print(f"[ASR] Debut transcription en {language}...")
    transcription = await transcribe_audio_bytes(audio_bytes, language, extension)

    if transcription is None:
        print(f"[ASR] Transcription echouee - None retourne")
        raise HTTPException(
            status_code=500,
            detail="Echec de la transcription"
        )

    print(f"[ASR] Transcription Bambara brute: '{transcription}'")

    # Nettoyage post-ASR : corriger les erreurs phonétiques courantes
    if language == "bam" and transcription:
        cleaned = clean_asr_transcription(transcription)
        if cleaned != transcription:
            print(f"[ASR] Après nettoyage: '{cleaned}'")
            transcription = cleaned

    lang_name = IVORIAN_ASR_LANGUAGES[language][0]

    # Traduire en francais - UNIQUEMENT pour Bambara
    french_translation = None
    translation_model = None
    translation_available = False

    if transcription and language == "bam":
        try:
            print(f"[ASR] Traduction Bambara -> Francais...")
            french_translation = translate_to_french(transcription)
            print(f"[ASR] Traduction Francais: '{french_translation}'")
            translation_model = "NLLB-200"
            translation_available = True
        except Exception as e:
            print(f"[ASR] Erreur traduction: {e}")

    return {
        "transcription": transcription,
        "french_translation": french_translation,
        "language": language,
        "language_name": lang_name,
        "translation_available": translation_available,
        "translation_model": translation_model
    }


@router.get("/languages")
async def list_asr_languages():
    """
    Liste les langues disponibles pour la reconnaissance vocale

    Retourne les codes ISO et noms des langues supportees
    """
    languages = get_supported_asr_languages()

    return {
        "languages": languages,
        "total": len(languages),
        "with_translation": {
            "languages": ["bam"],
            "model": "NLLB-200",
            "description": "ASR + Traduction Français complète"
        },
        "asr_only": {
            "languages": ["ati", "dyi", "myk", "gud", "adj", "dnj", "wob"],
            "description": "ASR uniquement (pas de traduction disponible)"
        },
        "note": "Seul le Bambara/Dioula dispose d'une traduction automatique vers le français"
    }


@router.get("/status")
async def asr_status():
    """
    Verifie le statut du service ASR

    Retourne si le modele est charge et les langues supportees
    """
    asr_info = check_asr_status()

    return {
        "asr": asr_info,
        "translation": {
            "model": "NLLB-200",
            "supported_languages": ["bam"],
            "description": "Traduction Bambara <-> Français"
        },
        "summary": {
            "full_support": ["bam"],
            "asr_only": ["ati", "dyi", "myk", "gud", "adj", "dnj", "wob"]
        }
    }
