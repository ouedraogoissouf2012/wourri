"""Sas admin LQE — file dyu (ADR-0031). UI = templates Jinja + static."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.security import require_api_key
from app.services.improvement_queue import decide_task, list_tasks

router = APIRouter(prefix="/admin/lqe", tags=["LQE"])
templates = Jinja2Templates(directory="templates")


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


@router.get("/", response_class=HTMLResponse)
def lqe_page(request: Request):
    return templates.TemplateResponse("admin/lqe.html", {"request": request})


@router.get("/tasks", dependencies=[Depends(require_api_key)])
def lqe_tasks():
    bronze = list_tasks(status="bronze", language="dyu")
    spoken = list_tasks(status="speaker_accepted", language="dyu")
    return {"language": "dyu", "tasks": bronze + spoken}


@router.post("/decision", dependencies=[Depends(require_api_key)])
def lqe_decision(body: DecisionBody):
    result = decide_task(body.id, body.decision)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "error"))
    return result
