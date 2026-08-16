"""Démo Console — passe par le chat/corpus, pas la seule traduction NLLB.

Le site Vercel appelait POST /api/tts/ (dico+NLLB+voix) → « suman » hors IVR.
Ce routeur expose le même pipeline que WhatsApp : NLU → corpus → fallback.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.models.schemas import Language
from app.security import require_api_key
from app.services.chat_service import get_chat_service

router = APIRouter(prefix="/api/demo", tags=["Demo"])

_CORPUS_SOURCES = frozenset({
    "ivr_exact",
    "ivr_fallback",
    "ivr_concept",
    "ivr_semantic",
})


class DemoAgriRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    city: str = "Bouaké"
    include_audio: bool = True


class DemoAgriResponse(BaseModel):
    text_fr: str
    text_dioula: str | None = None
    audio_url: str | None = None
    city: str
    source: str
    badge: str
    intent: str | None = None
    cultures: list | None = None


def _badge(source: str) -> str:
    if source in _CORPUS_SOURCES:
        return "CORPUS_VALIDE"
    if source.startswith("deepseek"):
        return "FALLBACK_OUVERT"
    return "AUTRE"


@router.post("/agri", response_model=DemoAgriResponse, dependencies=[Depends(require_api_key)])
async def demo_agri(body: DemoAgriRequest):
    """Conseil agricole démo : ChatService (corpus d'abord), audio dioula si dispo."""
    service = get_chat_service()
    result = await service.process(
        message=body.message.strip(),
        city=body.city.strip() or "Bouaké",
        language=Language.BOTH,
        include_audio=body.include_audio,
        user_id="demo-console",
    )
    meta = result.meta or {}
    source = str(meta.get("source") or "unknown")
    return DemoAgriResponse(
        text_fr=result.response,
        text_dioula=result.response_dioula,
        audio_url=result.audio_url,
        city=result.city,
        source=source,
        badge=_badge(source),
        intent=meta.get("intent") if isinstance(meta.get("intent"), str) else None,
        cultures=meta.get("cultures") if isinstance(meta.get("cultures"), list) else None,
    )
