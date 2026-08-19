"""Écran Baoulé (#443) — routes minces ; UI = templates Jinja + static.

Compte : BAOULE_PROVIDER_USER / BAOULE_PROVIDER_PASSWORD.
Aucune publication corpus dioula.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.data.lqe_languages import BAOULE_CODE
from app.services.baoule_auth import (
    COOKIE_NAME,
    is_configured,
    read_session,
    sign_session,
    verify_password,
)
from app.services.baoule_corpus import corpus_stats, list_corpus, promote_task
from app.services.baoule_provider import ingest_baoule_json, parse_upload
from app.services.improvement_queue import decide_task, list_tasks

router = APIRouter(prefix="/admin/baoule", tags=["Admin Baoulé"])
templates = Jinja2Templates(directory="templates")


def _session_user(request: Request) -> str | None:
    sess = read_session(request.cookies.get(COOKIE_NAME))
    return sess.get("u") if sess else None


def require_baoule_session(request: Request) -> str:
    user = _session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return user


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


class PromoteBody(BaseModel):
    id: str = Field(min_length=1)


@router.get("/", response_class=HTMLResponse)
def baoule_home(request: Request):
    if not is_configured():
        return templates.TemplateResponse(
            "admin/baoule_login.html",
            {
                "request": request,
                "err": "Compte non configuré. Dokploy : BAOULE_PROVIDER_USER et BAOULE_PROVIDER_PASSWORD (min 8 car.).",
            },
            status_code=503,
        )
    if not _session_user(request):
        return templates.TemplateResponse(
            "admin/baoule_login.html",
            {"request": request, "err": ""},
        )
    return templates.TemplateResponse(
        "admin/baoule.html",
        {"request": request},
    )


@router.post("/login")
async def baoule_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not verify_password(username, password):
        return templates.TemplateResponse(
            "admin/baoule_login.html",
            {"request": request, "err": "Identifiants incorrects."},
            status_code=401,
        )
    resp = RedirectResponse("/admin/baoule/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        sign_session(username),
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
        secure=False,
    )
    return resp


@router.get("/logout")
def baoule_logout():
    resp = RedirectResponse("/admin/baoule/", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/api/tasks")
def baoule_api_tasks(user: str = Depends(require_baoule_session)):
    bronze = list_tasks(status="bronze", language=BAOULE_CODE)
    accepted = list_tasks(status="admin_accepted", language=BAOULE_CODE)
    spoken = list_tasks(status="speaker_accepted", language=BAOULE_CODE)
    return {
        "language": BAOULE_CODE,
        "user": user,
        "bronze": bronze,
        "accepted": accepted + spoken,
        "tasks": bronze + accepted + spoken,
        "corpus": corpus_stats(),
    }


@router.get("/api/corpus")
def baoule_api_corpus(user: str = Depends(require_baoule_session)):
    return {"language": BAOULE_CODE, "entries": list_corpus(), "stats": corpus_stats()}


@router.post("/api/promote")
def baoule_api_promote(
    body: PromoteBody,
    user: str = Depends(require_baoule_session),
):
    result = promote_task(body.id, promoted_by=user)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "error"))
    return result


@router.post("/api/upload-json")
async def baoule_api_upload_json(
    request: Request,
    user: str = Depends(require_baoule_session),
):
    payload = await request.json()
    result = ingest_baoule_json(payload, provider_id=f"baoule:{user}")
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


@router.post("/api/upload")
async def baoule_api_upload_file(
    file: UploadFile = File(...),
    user: str = Depends(require_baoule_session),
):
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 5 Mo)")
    try:
        payload = parse_upload(file.filename or "", raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = ingest_baoule_json(payload, provider_id=f"baoule:{user}")
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


@router.post("/api/decision")
def baoule_api_decision(
    body: DecisionBody,
    user: str = Depends(require_baoule_session),
):
    result = decide_task(body.id, body.decision)
    if not result.get("ok"):
        detail = result.get("reason", "error")
        if result.get("path"):
            detail = f"{detail} (path={result['path']})"
        raise HTTPException(status_code=400, detail=detail)
    return result
