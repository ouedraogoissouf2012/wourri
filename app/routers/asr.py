"""
WOURI - Router ASR (Automatic Speech Recognition)
Reconnaissance vocale pour langues ivoiriennes via MMS-1B-ALL + NLLB-200
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
import re
from app.services.asr import get_asr_chain, get_generic_asr_chain
from app.data.constants import get_asr_languages

IVORIAN_ASR_LANGUAGES = get_asr_languages()
from app.services.tts_bambara import translate_to_french
from app.security import require_api_key, limiter
import logging

logger = logging.getLogger(__name__)

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
        logger.error("[ASR] NLU erreur: %s", e)
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
    # Soir (wulafɛ) — NeMo fragmente ou déforme
    "wulari": "wulafɛ", "wulafe": "wulafɛ", "wula fe": "wulafɛ",
    "ani wula": "a ni wulafɛ", "ani wulafe": "a ni wulafɛ",
    # Nuit (sufɛ) — NeMo fragmente "sufɛ" en morceaux absurdes
    "su ani so": "a ni sufɛ", "an ni sa kɔnɔ": "a ni sufɛ",
    "an ni su": "a ni sufɛ", "a ni su": "a ni sufɛ",
    "sufe": "sufɛ", "su fe": "sufɛ",
    # Midi (tilefɛ)
    "tile fe": "tilefɛ", "tilefe": "tilefɛ", "tile fɛ": "tilefɛ",

    # ========== MOTS AGRICOLES ==========
    "malon": "malo",        # riz
    "kaban": "kaba",        # maïs
    "ka ba": "kaba",        # maïs (fragmenté)
    "kabal": "kaba",        # maïs (déformé)
    "kab ": "kaba ",        # maïs (tronqué)
    "walakaba": "kaba",     # maïs (variante longue)
    "tigan": "tiga",        # arachide
    "foron": "foro",        # champ
    "jinan": "jina",        # légume
    "banan": "bana",        # maladie (des plantes)
    "sunan": "sunu",        # mil
    "bananku": "bananku",   # manioc (déjà correct)
    "manioku": "bananku",   # manioc (loanword FR)

    # ========== TEMPS / SAISON ==========
    "wagati jumen": "wagati jumɛn",   # à quel moment
    "wagati jumin": "wagati jumɛn",
    "wagatijumen": "wagati jumɛn",
    "min na ": "jumɛn na ",           # confusion min/jumɛn
    "tuma jumen": "wagati jumɛn",     # synonyme tuma = wagati
    "tuma jumin": "wagati jumɛn",
    "san jumen": "san jumɛn",         # quelle année
    "kalo jumen": "kalo jumɛn",       # quel mois

    # Voyelles confondues (e/ɛ, o/ɔ)
    "senɛ": "sɛnɛ", "sene": "sɛnɛ",
    "kolo": "kɔlɔ", "kolɔ": "kɔlɔ",

    # ========== VERBES/MARQUEURS ==========
    " kan ": " ka ",
    " be ": " bɛ ",

    # ========== QUESTIONS AGRICOLES COURANTES ==========
    "malo sene": "malo sɛnɛ",
    "kaba sene": "kaba sɛnɛ",        # planter le maïs
    "kaba dan": "kaba dan",           # planter le maïs (variante)
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

    if len(audio_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier audio trop volumineux (max 10 MB)")

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

    if len(audio_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier audio trop volumineux (max 10 MB)")

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    filename = audio.filename or "audio.ogg"
    extension = filename.split(".")[-1].lower()
    if extension not in ["wav", "ogg", "mp3", "webm", "m4a"]:
        extension = "ogg"

    lang_name = IVORIAN_ASR_LANGUAGES[language][0]

    # Transcription ASR via chaîne de providers (Liskov : tous interchangeables)
    logger.info("[ASR] Transcription en %s...", language)

    if language == "bam":
        chain = get_asr_chain()
    else:
        chain = get_generic_asr_chain(language)

    transcription = await chain.transcribe(audio_bytes, extension)

    if transcription is None:
        raise HTTPException(status_code=500, detail="Echec de la transcription")

    logger.info("[ASR] Transcription brute: '%s'", transcription)

    # Nettoyage post-ASR
    if language == "bam":
        cleaned = clean_asr_transcription(transcription)
        if cleaned != transcription:
            logger.info("[ASR] Après nettoyage: '%s'", cleaned)
            transcription = cleaned

    # Traduction BAM → FR (uniquement pour Bambara)
    french_translation = None
    translation_available = False

    if language == "bam":
        try:
            logger.info("[ASR] Traduction Bambara -> Francais...")
            french_translation = translate_to_french(transcription)
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
