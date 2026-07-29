"""
WOURI - Routes Speech-to-Text (Whisper)
"""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.middleware.admin_metrics import set_request_metric_context
from app.models.schemas import Language
from app.security import limiter, require_api_key
from app.services import stt_whisper
from app.services.deepseek import correct_stt_transcription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stt", tags=["Speech-to-Text"])


# Mapping ISO 639 (code court) → Language enum interne.
# Registre OCP : ajouter une langue future = 1 entrée dans ce dict.
# Si le code n'est pas mappé → fallback Language.FRENCH (compat existant).
_ISO_TO_LANGUAGE: dict[str, Language] = {
    "fr": Language.FRENCH,
    "en": Language.ENGLISH,
    "bam": Language.DIOULA,  # codes ISO bambara
    "dyu": Language.DIOULA,  # codes ISO dioula
}


def _map_iso_to_language(iso_code: str) -> Language:
    """Mappe un code ISO 639 ('fr', 'en', 'bam', 'dyu') vers Language enum.

    Fallback sur FRENCH si le code n'est pas reconnu (defense en profondeur :
    permet l'ajout d'un code futur sans crash, juste avec correction FR par défaut).
    """
    return _ISO_TO_LANGUAGE.get(iso_code, Language.FRENCH)


@router.post("/transcribe", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def transcribe_audio(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default="fr")
):
    """
    Transcrit un fichier audio en texte.

    - **audio**: Fichier audio (mp3, wav, ogg, webm, etc.)
    - **language**: Code langue (fr, en, bam, etc.) - defaut: fr
    """
    if not stt_whisper.WHISPER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Service STT non disponible. Installez: pip install openai-whisper"
        )

    # Lire le fichier
    audio_bytes = await audio.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    if len(audio_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier audio trop volumineux (max 10 MB)")

    # Transcrire
    logger.info(f"[STT] Transcription demandee: {len(audio_bytes)} bytes, langue={language}, fichier={audio.filename}")

    set_request_metric_context(request, asr_success=False)
    try:
        result = await stt_whisper.transcribe_audio_bytes(
            audio_bytes,
            filename=audio.filename or "audio.ogg",
            language=language
        )
    except Exception as e:
        logger.error(f"[STT] Erreur exception: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur transcription: {str(e)}")

    if result is None:
        logger.error("[STT] Resultat None - transcription echouee")
        raise HTTPException(status_code=500, detail="Erreur lors de la transcription - resultat vide")

    set_request_metric_context(request, asr_success=True, source="whisper")

    # Correction intelligente via DeepSeek (corrige villes et termes agricoles).
    # Passe `language` au correcteur : si la langue n'a pas de prompt
    # enregistré dans STT_CORRECTION_PROMPTS (ex: ENGLISH), la correction
    # est skippée silencieusement (le texte brut Whisper est conservé).
    # Fix anti-hardcoding 2026-06-02 (cf. feedback_no_hardcoding).
    raw_text = result["text"]
    user_language = _map_iso_to_language(language)
    corrected_text = await correct_stt_transcription(raw_text, language=user_language)

    # Vérifier si l'audio était probablement en Dioula
    likely_dioula = result.get("likely_dioula_input", False)
    if likely_dioula:
        logger.info("[STT] Audio détecté comme Dioula - transcription peut être incorrecte")

    return JSONResponse(content={
        "success": True,
        "text": corrected_text,  # Texte corrigé par DeepSeek
        "raw_text": raw_text,    # Texte brut pour debug
        "language": result["language"],
        "language_probability": result.get("language_probability", 0),
        "likely_dioula_input": likely_dioula,  # Indique si audio probablement en Dioula
        "segments": result["segments"]
    })


@router.get("/status")
async def get_stt_status():
    """Retourne le statut du service STT"""
    return stt_whisper.check_whisper_status()


@router.get("/languages")
async def get_supported_languages():
    """Liste des langues supportees"""
    return {
        "languages": [
            {"code": "fr", "name": "Francais"},
            {"code": "en", "name": "English"},
            {"code": "bam", "name": "Bambara"},
            {"code": "wo", "name": "Wolof"},
            {"code": "ff", "name": "Fulfulde"},
            {"code": "auto", "name": "Detection automatique"}
        ]
    }
