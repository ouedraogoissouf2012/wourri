"""
WOURI - Router TTS (Text-to-Speech)
Support multi-langues ivoiriennes
"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request
from app.services.tts_french import synthesize_french, get_available_voices
from app.services.tts_bambara import synthesize_bambara, synthesize_bambara_text, translate_to_bambara
from app.services.tts_ivoirian import (
    synthesize_ivorian,
    synthesize_ivorian_text,
    get_supported_languages,
    check_models_status,
    resolve_language_code,
    IVORIAN_LANGUAGES
)
from app.models.schemas import TTSRequest, TTSResponse, TranslateRequest, TranslateResponse, Language
from app.security import require_api_key, limiter

router = APIRouter(prefix="/api/tts", tags=["TTS"])


@router.post("/", response_model=TTSResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def text_to_speech(request: Request, body: TTSRequest):
    """
    Convertit du texte en audio

    - **text**: Texte à convertir
    - **language**: Langue (french ou dioula)
    """
    if not body.text:
        raise HTTPException(status_code=400, detail="Le texte est requis")

    audio_url = None
    output_text = body.text

    if body.language == Language.DIOULA:
        # Traduire en Bambara et générer l'audio
        audio_url, bambara_text = await synthesize_bambara(body.text)
        if bambara_text:
            output_text = bambara_text
    else:
        # Générer l'audio en français
        audio_url = await synthesize_french(body.text)

    if not audio_url:
        raise HTTPException(status_code=500, detail="Échec de la génération audio")

    return TTSResponse(
        audio_url=audio_url,
        text=output_text,
        language=body.language.value
    )


@router.post("/french", response_model=TTSResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def tts_french(request: Request, text: str):
    """TTS en français uniquement"""
    audio_url = await synthesize_french(text)

    if not audio_url:
        raise HTTPException(status_code=500, detail="Échec TTS français")

    return TTSResponse(audio_url=audio_url, text=text, language="french")


@router.post("/bambara", response_model=TTSResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def tts_bambara(request: Request, text: str, is_french: bool = True):
    """
    TTS en Bambara

    - **text**: Texte (français ou bambara)
    - **is_french**: True si le texte est en français (sera traduit)
    """
    if is_french:
        audio_url, bambara_text = await synthesize_bambara(text)
        output_text = bambara_text or text
    else:
        audio_url = await asyncio.to_thread(synthesize_bambara_text, text)
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

@router.post("/translate", response_model=TranslateResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def translate(request: Request, body: TranslateRequest):
    """
    Traduit du texte vers le Bambara

    - **text**: Texte à traduire
    - **source**: Langue source (défaut: fra_Latn)
    - **target**: Langue cible (défaut: bam_Latn)
    """
    if body.source != "fra_Latn" or body.target != "bam_Latn":
        raise HTTPException(
            status_code=400,
            detail="Seule la traduction français->bambara est supportée"
        )

    try:
        translated = await asyncio.to_thread(translate_to_bambara, body.text)
        return TranslateResponse(
            original=body.text,
            translated=translated,
            source=body.source,
            target=body.target
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traduction: {str(e)}")


# ============ LANGUES IVOIRIENNES ============

@router.get("/ivorian/languages")
async def list_ivorian_languages():
    """
    Liste toutes les langues ivoiriennes supportées pour le TTS

    Retourne les codes ISO et noms des langues disponibles
    """
    languages = get_supported_languages()
    return {
        "languages": languages,
        "total": len(languages),
        "note": "Utilisez le code ISO (ex: 'ati' pour Attié) dans les requêtes TTS"
    }


@router.get("/ivorian/status")
async def ivorian_tts_status():
    """
    Vérifie le statut des modèles TTS ivoiriens

    Retourne quels modèles sont chargés en mémoire
    """
    return check_models_status()


@router.post("/ivorian/{language_code}", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def tts_ivorian_language(request: Request, language_code: str, text: str):
    """
    TTS pour une langue ivoirienne spécifique

    - **language_code**: Code ISO de la langue (bam, ati, dyi, myk, gud, adj, dnj, wob)
    - **text**: Texte à synthétiser (dans la langue cible)

    Langues disponibles:
    - bam: Bambara/Dioula
    - ati: Attié
    - dyi: Sénoufo Djimini
    - myk: Sénoufo Mamara
    - gud: Dida Yocoboué
    - adj: Adioukrou
    - dnj: Dan/Yacouba
    - wob: Wobé
    """
    # Vérifier que la langue est supportée
    resolved = resolve_language_code(language_code)
    if not resolved:
        supported = get_supported_languages()
        raise HTTPException(
            status_code=400,
            detail=f"Langue '{language_code}' non supportée. Langues disponibles: {list(supported.keys())}"
        )

    # Générer l'audio
    audio_url = synthesize_ivorian_text(text, resolved)

    if not audio_url:
        raise HTTPException(
            status_code=500,
            detail=f"Échec de la synthèse TTS pour {IVORIAN_LANGUAGES[resolved][0]}"
        )

    return TTSResponse(
        audio_url=audio_url,
        text=text,
        language=IVORIAN_LANGUAGES[resolved][0]
    )


@router.post("/ivorian", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def tts_ivorian_auto(request: Request, text: str, language: str = "bam"):
    """
    TTS ivoirien avec détection automatique de langue par alias

    - **text**: Texte à synthétiser
    - **language**: Code ou nom de la langue (ex: "bambara", "attie", "senoufo")

    Alias supportés:
    - bambara, dioula, jula → bam
    - attie → ati
    - senoufo, senoufo_djimini → dyi
    - senoufo_mamara → myk
    - dida → gud
    - adioukrou → adj
    - dan, yacouba → dnj
    - wobe → wob
    """
    audio_url, lang_name = await synthesize_ivorian(text, language)

    if not audio_url:
        supported = get_supported_languages()
        raise HTTPException(
            status_code=500,
            detail=f"Échec TTS. Vérifiez que la langue est supportée: {list(supported.keys())}"
        )

    return TTSResponse(
        audio_url=audio_url,
        text=text,
        language=lang_name
    )
