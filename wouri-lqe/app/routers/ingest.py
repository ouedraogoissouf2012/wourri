from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.routers.session import require_role
from app.services.ingest import ingest, parse_upload

router = APIRouter(prefix="/ingest")


@router.post("/json")
async def ingest_json(request: Request, user: dict = Depends(require_role("ingest"))):
    payload = await request.json()
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        entries = payload["entries"]
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = [payload] if isinstance(payload, dict) else []
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
    result = ingest(entries, language=user["lang"], actor=user["u"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result

