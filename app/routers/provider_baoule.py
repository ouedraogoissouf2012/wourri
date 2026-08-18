"""API provider Baoulé (#443) — upload JSON → Bronze.

Auth : X-API-Key (même garde-fou moteur). Pas de publish corpus.
UI console Marcel pourra appeler ces routes plus tard.
"""
from __future__ import annotations

import json

from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.data.lqe_languages import BAOULE_CODE
from app.security import require_api_key
from app.services.baoule_provider import ingest_baoule_json, parse_json_bytes
from app.services.improvement_queue import list_tasks

router = APIRouter(prefix="/api/provider/baoule", tags=["Provider Baoulé"])


@router.get("/schema", dependencies=[Depends(require_api_key)])
def baoule_schema():
    """Schéma minimal pour les providers (documentation machine)."""
    return {
        "language_code": BAOULE_CODE,
        "iso_639_3": "bci",
        "display_name": "Baoulé",
        "status_on_upload": "bronze",
        "required_fields": ["text_local", "text_fr"],
        "optional_fields": [
            "id",
            "language",
            "intent",
            "cultures",
            "region",
            "notes",
        ],
        "example": [
            {
                "id": "bci_001",
                "language": "bci",
                "text_local": "(phrase baoulé fournie par le provider)",
                "text_fr": "(équivalent français fourni par le provider)",
                "intent": "CONSEIL_PRODUCTION",
                "cultures": ["CULTURE_MAIS"],
                "region": "CI",
            }
        ],
        "rules": [
            "status client ignoré — toujours bronze",
            "aucune écriture pgvector / WhatsApp",
            "ADC valide avant Or/Production",
        ],
    }


@router.get("/tasks", dependencies=[Depends(require_api_key)])
def baoule_tasks():
    """File Bronze baoulé (lecture provider / ADC)."""
    bronze = list_tasks(status="bronze", language=BAOULE_CODE)
    spoken = list_tasks(status="speaker_accepted", language=BAOULE_CODE)
    return {"language": BAOULE_CODE, "tasks": bronze + spoken}


@router.post("/upload", dependencies=[Depends(require_api_key)])
async def baoule_upload_json(file: UploadFile = File(...)):
    """Upload d'un fichier .json (liste d'entrées) → Bronze uniquement."""
    name = (file.filename or "").lower()
    if name and not name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Fichier .json requis")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 2 Mo)")
    try:
        payload = parse_json_bytes(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"JSON invalide: {exc}") from exc

    result = ingest_baoule_json(payload, provider_id="provider_baoule_upload")
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@router.post("/upload-json", dependencies=[Depends(require_api_key)])
async def baoule_upload_body(payload: Any = Body(...)):
    """Même chose avec body JSON brut (sans multipart)."""
    result = ingest_baoule_json(payload, provider_id="provider_baoule_api")
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)
