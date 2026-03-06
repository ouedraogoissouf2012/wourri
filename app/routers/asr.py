"""
WOURI - Router ASR (Automatic Speech Recognition)
Reconnaissance vocale pour langues ivoiriennes via MMS-1B-ALL + NLLB-200
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
import re
from app.services.asr_ivorian import (
    transcribe_audio_bytes,
    get_supported_asr_languages,
    check_asr_status,
    IVORIAN_ASR_LANGUAGES
)
from app.services.asr_soloni_nemo import (
    transcribe_bambara_nemo,
    check_nemo_asr_status,
)
from app.services.tts_bambara import translate_to_french

router = APIRouter(prefix="/api/asr", tags=["ASR"])


def _run_nlu(bambara_text: str) -> dict:
    """Lance le NLU sur le texte bambara et retourne les infos NLU."""
    try:
        from app.services.nlu import get_nlu_service
        nlu = get_nlu_service()
        if nlu is None:
            return {}
        result = nlu.process(bambara_text)
        return {
            "nlu_intent": result.intent,
            "nlu_confidence": round(result.confidence, 2),
            "nlu_message": result.french_sentence,
            "nlu_concepts": list(result.concepts.keys()),
            "nlu_is_out_of_scope": result.is_out_of_scope,
            "nlu_has_greeting": result.has_greeting,
        }
    except Exception as e:
        print(f"[ASR] NLU erreur: {e}")
        return {}


# Nettoyage post-ASR : l'ASR MMS-1B-ALL fait des erreurs phonétiques récurrentes
# Ces corrections sont appliquées AVANT la traduction BAM→FR
_ASR_FIXES = {
    # ========== SALUTATIONS ==========
    "sɔrɔma": "sɔgɔma", "sorɔma": "sɔgɔma", "soroma": "sogoma",
    "sɔrɔ ma": "sɔgɔma", "sagɔma": "sɔgɔma", "sagoma": "sogoma",
    "sɔgɔ ma": "sɔgɔma", "sogo ma": "sogoma",
    "ani sɔgɔma": "i ni sɔgɔma", "ani sogoma": "i ni sogoma",
    "ani ce": "i ni ce", "anise": "i ni ce", "anice": "i ni ce",

    # ========== MOTS AGRICOLES ==========
    "malon": "malo",        # riz
    "kaban": "kaba",        # maïs
    "tigan": "tiga",        # arachide
    "foron": "foro",        # champ
    "jinan": "jina",        # légume
    "banan": "bana",        # maladie (des plantes)
    "sunan": "sunu",        # mil

    # Voyelles confondues (e/ɛ, o/ɔ)
    "senɛ": "sɛnɛ", "sene": "sɛnɛ",
    "kolo": "kɔlɔ", "kolɔ": "kɔlɔ",

    # ========== VERBES/MARQUEURS ==========
    " kan ": " ka ",
    " be ": " bɛ ",

    # ========== QUESTIONS AGRICOLES COURANTES ==========
    "malo sene": "malo sɛnɛ",
    "foro labɛn": "foro labɛn",
    "jii don": "ji don",
}


def clean_asr_transcription(text: str) -> str:
    """Corrige les erreurs ASR courantes de MMS-1B-ALL pour le bambara."""
    if not text:
        return text
    result = f" {text} "
    for wrong, correct in _ASR_FIXES.items():
        result = result.replace(wrong, correct)
    return result.strip()


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = Form(default="bam")
):
    """
    Transcrit un fichier audio en texte (sans traduction)

    - **audio**: Fichier audio (WAV, OGG, MP3, WEBM)
    - **language**: Code de la langue (bam, ati, dyi, myk, gud, adj, dnj, wob)
    """
    if language not in IVORIAN_ASR_LANGUAGES:
        supported = list(IVORIAN_ASR_LANGUAGES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Langue '{language}' non supportee. Langues disponibles: {supported}"
        )

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    filename = audio.filename or "audio.ogg"
    extension = filename.split(".")[-1].lower()
    if extension not in ["wav", "ogg", "mp3", "webm", "m4a"]:
        extension = "ogg"

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
    Transcrit un fichier audio ET traduit en français via MMS-1B-ALL + NLLB-200

    - **audio**: Fichier audio
    - **language**: Code de la langue source (bam par défaut)

    Traduction disponible uniquement pour bam (Bambara/Dioula)
    """
    if language not in IVORIAN_ASR_LANGUAGES:
        supported = list(IVORIAN_ASR_LANGUAGES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Langue '{language}' non supportee. Langues disponibles: {supported}"
        )

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    filename = audio.filename or "audio.ogg"
    extension = filename.split(".")[-1].lower()
    if extension not in ["wav", "ogg", "mp3", "webm", "m4a"]:
        extension = "ogg"

    lang_name = IVORIAN_ASR_LANGUAGES[language][0]

    # Transcription ASR
    print(f"[ASR] Transcription en {language}...")

    # Bambara : utiliser NeMo TDT (decodeur complet, meilleure qualite)
    if language == "bam":
        transcription = await transcribe_bambara_nemo(audio_bytes, extension)
        if transcription is None:
            print("[ASR] NeMo echoue, fallback MMS-1B-ALL...")
            transcription = await transcribe_audio_bytes(audio_bytes, language, extension)
    else:
        transcription = await transcribe_audio_bytes(audio_bytes, language, extension)

    if transcription is None:
        raise HTTPException(status_code=500, detail="Echec de la transcription")

    print(f"[ASR] Transcription brute: '{transcription}'")

    # Nettoyage post-ASR
    if language == "bam":
        cleaned = clean_asr_transcription(transcription)
        if cleaned != transcription:
            print(f"[ASR] Après nettoyage: '{cleaned}'")
            transcription = cleaned

    # Traduction BAM → FR (uniquement pour Bambara)
    french_translation = None
    translation_available = False

    if language == "bam":
        try:
            print(f"[ASR] Traduction Bambara -> Francais...")
            french_translation = translate_to_french(transcription)
            print(f"[ASR] Traduction: '{french_translation}'")
            translation_available = True
        except Exception as e:
            print(f"[ASR] Erreur traduction: {e}")

    # NLU: extraction de concepts + reconstruction de phrase française
    # nlu_message est la phrase française reconstruite (plus précise que french_translation)
    # Le serveur WhatsApp doit utiliser nlu_message en priorité s'il est non-null
    nlu_data = {}
    if language == "bam":
        nlu_data = _run_nlu(transcription)
        if nlu_data.get("nlu_message"):
            print(f"[ASR] NLU → phrase reconstruite: '{nlu_data['nlu_message']}'")

    return {
        "transcription": transcription,
        "french_translation": french_translation,
        "language": language,
        "language_name": lang_name,
        "translation_available": translation_available,
        "translation_model": "NeMo TDT + Dictionnaire + NLLB-200",
        # NLU: intent, message reconstruit, concepts
        "nlu_intent": nlu_data.get("nlu_intent"),
        "nlu_confidence": nlu_data.get("nlu_confidence", 0.0),
        "nlu_message": nlu_data.get("nlu_message"),          # ← UTILISER EN PRIORITÉ
        "nlu_concepts": nlu_data.get("nlu_concepts", []),
        "nlu_is_out_of_scope": nlu_data.get("nlu_is_out_of_scope", False),
        "nlu_has_greeting": nlu_data.get("nlu_has_greeting", False),
    }


@router.get("/languages")
async def list_asr_languages():
    """Liste les langues disponibles pour la reconnaissance vocale"""
    languages = get_supported_asr_languages()
    return {
        "languages": languages,
        "total": len(languages),
        "with_translation": {
            "languages": ["bam"],
            "model": "MMS-1B-ALL + NLLB-200",
            "description": "ASR + Traduction Bambara → Français"
        },
        "asr_only": {
            "languages": ["ati", "dyi", "myk", "gud", "adj", "dnj", "wob"],
            "description": "ASR uniquement (pas de traduction disponible)"
        }
    }


@router.get("/status")
async def asr_status():
    """Vérifie le statut du service ASR"""
    asr_info = check_asr_status()
    return {
        "local_asr": asr_info,
        "translation": {
            "model": "MMS-1B-ALL + NLLB-200",
            "supported_languages": ["bam"],
            "description": "Traduction Bambara <-> Français"
        },
        "summary": {
            "full_support": ["bam"],
            "asr_only": ["ati", "dyi", "myk", "gud", "adj", "dnj", "wob"]
        }
    }
