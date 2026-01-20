"""
WOURI - Router TTS (Text-to-Speech)
"""
from fastapi import APIRouter, HTTPException
from app.services.tts_french import synthesize_french, get_available_voices
from app.services.tts_bambara import synthesize_bambara, synthesize_bambara_text, translate_to_bambara
from app.models.schemas import TTSRequest, TTSResponse, TranslateRequest, TranslateResponse, Language

router = APIRouter(prefix="/api/tts", tags=["TTS"])


@router.post("/", response_model=TTSResponse)
async def text_to_speech(request: TTSRequest):
    """
    Convertit du texte en audio

    - **text**: Texte à convertir
    - **language**: Langue (french ou dioula)
    """
    if not request.text:
        raise HTTPException(status_code=400, detail="Le texte est requis")

    audio_url = None
    output_text = request.text

    if request.language == Language.DIOULA:
        # Traduire en Bambara et générer l'audio
        audio_url, bambara_text = await synthesize_bambara(request.text)
        if bambara_text:
            output_text = bambara_text
    else:
        # Générer l'audio en français
        audio_url = await synthesize_french(request.text)

    if not audio_url:
        raise HTTPException(status_code=500, detail="Échec de la génération audio")

    return TTSResponse(
        audio_url=audio_url,
        text=output_text,
        language=request.language.value
    )


@router.post("/french", response_model=TTSResponse)
async def tts_french(text: str):
    """TTS en français uniquement"""
    audio_url = await synthesize_french(text)

    if not audio_url:
        raise HTTPException(status_code=500, detail="Échec TTS français")

    return TTSResponse(audio_url=audio_url, text=text, language="french")


@router.post("/bambara", response_model=TTSResponse)
async def tts_bambara(text: str, is_french: bool = True):
    """
    TTS en Bambara

    - **text**: Texte (français ou bambara)
    - **is_french**: True si le texte est en français (sera traduit)
    """
    if is_french:
        audio_url, bambara_text = await synthesize_bambara(text)
        output_text = bambara_text or text
    else:
        audio_url = synthesize_bambara_text(text)
        output_text = text

    if not audio_url:
        raise HTTPException(status_code=500, detail="Échec TTS Bambara")

    return TTSResponse(audio_url=audio_url, text=output_text, language="dioula")


@router.get("/voices")
async def list_voices():
    """Liste les voix disponibles pour le français"""
    voices = await get_available_voices()
    return {"voices": voices}


# ============ TRADUCTION ============

@router.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest):
    """
    Traduit du texte vers le Bambara

    - **text**: Texte à traduire
    - **source**: Langue source (défaut: fra_Latn)
    - **target**: Langue cible (défaut: bam_Latn)
    """
    if request.source != "fra_Latn" or request.target != "bam_Latn":
        raise HTTPException(
            status_code=400,
            detail="Seule la traduction français->bambara est supportée"
        )

    try:
        translated = translate_to_bambara(request.text)
        return TranslateResponse(
            original=request.text,
            translated=translated,
            source=request.source,
            target=request.target
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traduction: {str(e)}")
