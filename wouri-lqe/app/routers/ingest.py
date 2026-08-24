from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.routers.session import require_role
from app.services.assignments import parity_ok
from app.services.audio_store import LocalAudioStore
from app.services.ingest import ingest, ingest_response, parse_upload
from app.services.pg_catalog import PgCorpusCatalog

router = APIRouter(prefix="/ingest")


def _guard_parity(entries: list, language: str) -> None:
    """Parite avant extension (ADR-0034) : refuse un lot contenant de la saisie LIBRE
    (extension) tant que la langue n'est pas a jour (100 % couverte). Une entree n'est
    exemptee que si son `concept_id` est un concept REEL du corpus — un id arbitraire ne
    contourne PAS la garde. Les reponses d'assignation doivent etre envoyees sans melanger
    d'entree libre dans le meme lot (sinon le lot entier est refuse)."""
    catalog = PgCorpusCatalog()
    known_ids = {c.id for c in catalog.list_concepts()}
    has_extension = any(
        not (isinstance(e, dict) and str(e.get("concept_id") or "").strip() in known_ids)
        for e in entries
    )
    if has_extension and not parity_ok(catalog, language=language):
        raise HTTPException(status_code=409, detail="parity_required")


@router.post("/json")
async def ingest_json(request: Request, user: dict = Depends(require_role("ingest"))):
    payload = await request.json()
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        entries = payload["entries"]
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = [payload] if isinstance(payload, dict) else []
    _guard_parity(entries, user["lang"])
    result = ingest(entries, language=user["lang"], actor=user["u"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/file")
async def ingest_file(file: UploadFile = File(...), user: dict = Depends(require_role("ingest"))):
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=400, detail="too_large")
    try:
        entries = parse_upload(file.filename or "", raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _guard_parity(entries, user["lang"])
    result = ingest(entries, language=user["lang"], actor=user["u"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


_ALLOWED_AUDIO = {"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4"}


@router.post("/audio")
async def ingest_audio(
    concept_id: str = Form(...),
    text_fr: str = Form(...),
    text_local: str = Form(""),
    audio: UploadFile = File(...),
    user: dict = Depends(require_role("ingest")),
):
    """Réponse d'un locuteur à une assignation : audio natif requis + texte optionnel.
    Stocke l'audio (audio_store) puis crée la production bronze rattachée au concept."""
    mime = (audio.content_type or "audio/webm").split(";")[0].strip()
    if mime not in _ALLOWED_AUDIO:
        raise HTTPException(status_code=400, detail="format_audio_non_supporte")
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="audio_vide")
    if len(raw) > 15_000_000:
        raise HTTPException(status_code=400, detail="audio_trop_grand")
    ref = LocalAudioStore().save(raw, mime=mime)
    result = ingest_response(
        concept_id=concept_id, text_local=text_local, text_fr=text_fr,
        audio_url=ref, language=user["lang"], actor=user["u"],
    )
    if not result.get("ok") and not result.get("duplicate"):
        raise HTTPException(status_code=400, detail=result)
    return result

