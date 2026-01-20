"""
WOURI - Routes Speech-to-Text (Whisper)
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from app.services import stt_whisper

router = APIRouter(prefix="/api/stt", tags=["Speech-to-Text"])


@router.post("/transcribe")
async def transcribe_audio(
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

    # Transcrire
    result = await stt_whisper.transcribe_audio_bytes(
        audio_bytes,
        filename=audio.filename,
        language=language
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Erreur lors de la transcription")

    return JSONResponse(content={
        "success": True,
        "text": result["text"],
        "language": result["language"],
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
