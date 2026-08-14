"""
WOURI - Router ASR (Automatic Speech Recognition)
Reconnaissance vocale pour langues ivoiriennes via MMS-1B-ALL + NLLB-200
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.data.constants import get_asr_languages
from app.middleware.admin_metrics import set_request_metric_context
from app.routers._audio_upload import read_audio_within_limits, resolve_extension
from app.security import limiter, require_api_key
from app.services.asr import ASRChain, get_asr_chain, get_generic_asr_chain
from app.services.tts_bambara import translate_to_french

logger = logging.getLogger(__name__)

IVORIAN_ASR_LANGUAGES = get_asr_languages()

router = APIRouter(prefix="/api/asr", tags=["ASR"])


def _validate_language(language: str) -> None:
    """Rejette une langue non supportée (400)."""
    if language not in IVORIAN_ASR_LANGUAGES:
        supported = list(IVORIAN_ASR_LANGUAGES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Langue '{language}' non supportee. Langues disponibles: {supported}",
        )


def _resolve_chain(language: str) -> ASRChain:
    """Chaîne ASR pour la langue : spécialisée bambara/dioula pour `bam`,
    générique pour les autres langues ivoiriennes."""
    if language == "bam":
        return get_asr_chain()
    return get_generic_asr_chain(language)


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
        logger.error("[ASR] NLU erreur: %s", e)
        return {}


# Post-ASR : la normalisation est maintenant dans ASRChain (asr_normalizer.py)
# Plus de dict _ASR_FIXES ici — source unique dans dictionnaires/asr_corrections.json


@router.post("/transcribe", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def transcribe_audio(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default="bam")
):
    """
    Transcrit un fichier audio en texte (sans traduction)

    - **audio**: Fichier audio (WAV, OGG, MP3, WEBM)
    - **language**: Code de la langue (bam, ati, dyi, myk, gud, adj, dnj, wob)
    """
    _validate_language(language)
    audio_bytes = await read_audio_within_limits(audio)
    extension = resolve_extension(audio.filename)
    chain = _resolve_chain(language)

    set_request_metric_context(request, asr_success=False)
    transcription = await chain.transcribe(audio_bytes, extension)

    if transcription is None:
        raise HTTPException(
            status_code=500,
            detail="Echec de la transcription. Verifiez que le modele ASR est charge."
        )

    set_request_metric_context(request, asr_success=True, source="asr")
    lang_name = IVORIAN_ASR_LANGUAGES[language][0]
    return {
        "transcription": transcription,
        "language": language,
        "language_name": lang_name
    }


@router.post("/transcribe-and-translate", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def transcribe_and_translate(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default="bam")
):
    """
    Transcrit un fichier audio ET traduit en français via MMS-1B-ALL + NLLB-200

    - **audio**: Fichier audio
    - **language**: Code de la langue source (bam par défaut)

    Traduction disponible uniquement pour bam (Bambara/Dioula)
    """
    _validate_language(language)
    audio_bytes = await read_audio_within_limits(audio)
    extension = resolve_extension(audio.filename)
    lang_name = IVORIAN_ASR_LANGUAGES[language][0]

    # Transcription ASR via chaîne de providers (Liskov : tous interchangeables)
    logger.info("[ASR] Transcription en %s...", language)

    chain = _resolve_chain(language)

    set_request_metric_context(request, asr_success=False)
    transcription = await chain.transcribe(audio_bytes, extension)

    if transcription is None:
        raise HTTPException(status_code=500, detail="Echec de la transcription")

    logger.info("[ASR] Transcription brute: '%s'", transcription)

    # Note: le nettoyage post-ASR est maintenant intégré dans ASRChain (asr_normalizer.py)

    # Traduction BAM → FR (uniquement pour Bambara)
    french_translation = None
    translation_available = False

    if language == "bam":
        try:
            logger.info("[ASR] Traduction Bambara -> Francais...")
            french_translation = await asyncio.to_thread(translate_to_french, transcription)
            logger.info("[ASR] Traduction: '%s'", french_translation)
            translation_available = True
        except Exception as e:
            logger.error("[ASR] Erreur traduction: %s", e)

    # NLU: extraction de concepts + reconstruction de phrase française
    # nlu_message est la phrase française reconstruite (plus précise que french_translation)
    # Le serveur WhatsApp doit utiliser nlu_message en priorité s'il est non-null
    nlu_data = {}
    if language == "bam":
        nlu_data = _run_nlu(transcription)
        if nlu_data.get("nlu_message"):
            logger.info("[ASR] NLU → phrase reconstruite: '%s'", nlu_data['nlu_message'])

    concepts = nlu_data.get("nlu_concepts", [])
    culture = next(
        (
            concept
            for concept in concepts
            if isinstance(concept, str) and concept.startswith("CULTURE_")
        ),
        None,
    )
    intent = nlu_data.get("nlu_intent")
    set_request_metric_context(
        request,
        asr_success=True,
        intent=intent,
        culture=culture,
        source="asr_nlu" if nlu_data else "asr",
        nlu_out_of_scope=nlu_data.get("nlu_is_out_of_scope") if nlu_data else None,
    )

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
    languages = {code: name for code, (name, _) in IVORIAN_ASR_LANGUAGES.items()}
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
    chain = get_asr_chain()
    asr_info = {
        "providers": [
            {"name": p.name, "available": p.is_available()}
            for p in chain.providers
        ],
    }
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
