"""
WOURI - Router Chat (routeur mince).

Toute la logique métier est dans ChatService.
Ce routeur ne fait que valider l'input et retourner le résultat.
"""
import logging

from fastapi import APIRouter, Depends, Request

from app.middleware.admin_metrics import set_request_metric_context
from app.models.schemas import ChatRequest, ChatResponse, Language
from app.security import require_api_key
from app.services.chat_service import get_chat_service
from app.services.deepseek import chat_with_deepseek
from app.services.weather import get_weather

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(request: Request, body: ChatRequest):
    """
    Envoie un message à l'assistant WOURI.

    Toute la logique est dans ChatService (SRP).
    """
    service = get_chat_service()
    result = await service.process(
        message=body.message,
        city=body.city,
        language=body.language,
        bambara_text=body.bambara_text,
        include_audio=body.include_audio,
        user_id=getattr(body, "user_id", None),
    )

    meta = result.meta or {}
    cultures = meta.get("cultures")
    culture = (
        cultures[0]
        if isinstance(cultures, list) and cultures and isinstance(cultures[0], str)
        else None
    )
    intent = meta.get("intent") if isinstance(meta.get("intent"), str) else None
    set_request_metric_context(
        request,
        intent=intent,
        culture=culture,
        source=meta.get("source"),
        nlu_out_of_scope=(intent == "HORS_SUJET") if intent else None,
    )

    return ChatResponse(
        response=result.response,
        response_dioula=result.response_dioula,
        response_local=None,
        audio_url=result.audio_url,
        city=result.city,
        language=result.language,
        audio_language=result.audio_language,
        meta=result.meta,
    )


@router.post("/simple", dependencies=[Depends(require_api_key)])
async def chat_simple(request: Request, message: str, city: str = "Abidjan"):
    """
    Version simple du chat (paramètres en query)

    - **message**: Question de l'utilisateur
    - **city**: Ville (défaut: Abidjan)
    """
    weather_data = await get_weather(city)

    response_text = await chat_with_deepseek(
        message=message,
        weather_data=weather_data,
        language=Language.FRENCH
    )

    return {"response": response_text, "city": city}


@router.get("/languages")
async def list_audio_languages():
    """
    Liste les langues disponibles pour le chat
    """
    return {
        "available_languages": {
            "french": "Français",
            "dioula": "Bambara/Dioula",
            "both": "Français + Dioula"
        },
        "default": "both",
        "full_support": {
            "languages": ["french", "dioula"],
            "description": "Texte + Traduction + Audio complet"
        },
        "note": "Seul le Bambara/Dioula dispose d'une traduction automatique via NLLB-200"
    }
