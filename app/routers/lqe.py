"""Sas admin LQE — écran français, file dyu (ADR-0031 / #433).

Pas d'auth locuteur ici (Better Auth #372 : écran locuteur plus tard).
Protégé par X-API-Key. Aucune publication pgvector.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.security import require_api_key
from app.services.improvement_queue import decide_task, list_tasks

router = APIRouter(prefix="/admin/lqe", tags=["LQE"])

_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>WOURI — File dioula CI</title>
  <style>
    body { font-family: sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.25rem; }
    .hint { color: #444; font-size: .9rem; }
    .card { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin: .75rem 0; }
    .excerpt { font-size: 1.05rem; margin: .5rem 0; }
    button { margin-right: .5rem; padding: .35rem .7rem; }
    #keybox { margin: 1rem 0; }
    input[type=password] { width: 16rem; }
  </style>
</head>
<body>
  <h1>File admin — dioula de Côte d’Ivoire</h1>
  <p class="hint">Interface en français. Phrases à revoir : dioula CI. La validation ici ne publie pas le corpus (sas admin, ADR-0031).</p>
  <div id="keybox">
    <label>Clé API <input id="key" type="password" autocomplete="off"/></label>
    <button type="button" id="load">Charger la file</button>
  </div>
  <div id="list"></div>
  <script>
    const list = document.getElementById("list");
    const keyInput = document.getElementById("key");
    async function api(path, opt) {
      const headers = Object.assign({"X-API-Key": keyInput.value}, (opt && opt.headers) || {});
      const r = await fetch(path, Object.assign({}, opt, {headers}));
      if (r.status === 401) throw new Error("Clé refusée");
      return r.json();
    }
    async function refresh() {
      list.textContent = "Chargement…";
      const data = await api("/admin/lqe/tasks");
      if (!data.tasks.length) { list.textContent = "Aucune tâche Bronze dyu."; return; }
      list.innerHTML = data.tasks.map(t => `
        <article class="card" data-id="${t.id}">
          <div><strong>${t.intent || "—"}</strong> · ${t.source || ""}</div>
          <p class="excerpt">${(t.excerpt || "").replace(/</g, "")}</p>
          <button data-d="admin_accepted">Accepter (file admin)</button>
          <button data-d="admin_rejected">Rejeter</button>
        </article>`).join("");
    }
    document.getElementById("load").onclick = () => refresh().catch(e => { list.textContent = e.message; });
    list.onclick = async (ev) => {
      const btn = ev.target.closest("button[data-d]");
      if (!btn) return;
      const id = btn.closest("[data-id]").dataset.id;
      await api("/admin/lqe/decision", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({id, decision: btn.dataset.d})});
      await refresh();
    };
  </script>
</body>
</html>
"""


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


@router.get("/", response_class=HTMLResponse)
def lqe_page():
    return HTMLResponse(_PAGE)


@router.get("/tasks", dependencies=[Depends(require_api_key)])
def lqe_tasks():
    return {"language": "dyu", "tasks": list_tasks(status="bronze", language="dyu")}


@router.post("/decision", dependencies=[Depends(require_api_key)])
def lqe_decision(body: DecisionBody):
    result = decide_task(body.id, body.decision)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "error"))
    return result
