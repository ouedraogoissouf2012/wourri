"""
WOURI - Routes Speech-to-Text (Whisper)
"""
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from app.services import stt_whisper
from app.services.deepseek import correct_stt_transcription
from app.security import require_api_key, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stt", tags=["Speech-to-Text"])


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

    # Correction intelligente via DeepSeek (corrige villes et termes agricoles)
    raw_text = result["text"]
    corrected_text = await correct_stt_transcription(raw_text)

    # Vérifier si l'audio était probablement en Dioula
    likely_dioula = result.get("likely_dioula_input", False)
    if likely_dioula:
        logger.info(f"[STT] Audio détecté comme Dioula - transcription peut être incorrecte")

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
