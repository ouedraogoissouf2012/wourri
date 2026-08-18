"""Écran admin Baoulé (#443) — upload JSON + file Bronze bci.

Même modèle que /admin/lqe/ (clé API, FR). Aucune publication corpus.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.data.lqe_languages import BAOULE_CODE
from app.security import require_api_key
from app.services.improvement_queue import decide_task, list_tasks

router = APIRouter(prefix="/admin/baoule", tags=["Admin Baoulé"])

_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>WOURI — Provider Baoulé</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.25rem; }
    h2 { font-size: 1.05rem; margin-top: 1.5rem; }
    .hint { color: #444; font-size: .9rem; }
    .card { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin: .75rem 0; background: #fafafa; }
    .local { font-size: 1.05rem; margin: .4rem 0; }
    .fr { color: #333; }
    button, .btn { margin-right: .5rem; padding: .4rem .75rem; cursor: pointer; }
    #keybox, #uploadbox { margin: 1rem 0; padding: 1rem; border: 1px dashed #aaa; border-radius: 8px; }
    input[type=password] { width: 18rem; max-width: 100%; }
    textarea { width: 100%; min-height: 8rem; font-family: ui-monospace, monospace; font-size: .85rem; }
    .ok { color: #1b6b2a; }
    .err { color: #9b2c2c; }
    .meta { font-size: .85rem; color: #555; }
  </style>
</head>
<body>
  <h1>Provider / admin — Baoulé (<code>bci</code>)</h1>
  <p class="hint">
    Interface en français. Upload JSON → file <strong>Bronze</strong> uniquement.
    Valider ici <strong>ne publie pas</strong> le corpus (ADR-0031 / #443).
    Séparé de la file dioula.
  </p>

  <div id="keybox">
    <label>Clé API (<code>API_SECRET_KEY</code>)<br/>
      <input id="key" type="password" autocomplete="off"/>
    </label>
    <button type="button" id="load">Charger la file</button>
  </div>

  <h2>1. Ajouter des phrases (JSON)</h2>
  <div id="uploadbox">
    <p class="hint">Liste d’objets avec au minimum <code>text_local</code> et <code>text_fr</code>.</p>
    <textarea id="json">[
  {
    "id": "bci_001",
    "language": "bci",
    "text_local": "(phrase baoulé fournie par le provider)",
    "text_fr": "(équivalent français fourni par le provider)",
    "intent": "CONSEIL_PRODUCTION"
  }
]</textarea>
    <p>
      <button type="button" id="sendJson">Envoyer vers Bronze</button>
      <label class="btn">Ou fichier
        <input id="file" type="file" accept=".json,application/json" style="display:none"/>
      </label>
    </p>
    <p id="uploadMsg" class="meta"></p>
  </div>

  <h2>2. File Bronze baoulé</h2>
  <div id="list" class="hint">Charge la file avec ta clé.</div>

  <script>
    const list = document.getElementById("list");
    const keyInput = document.getElementById("key");
    const uploadMsg = document.getElementById("uploadMsg");
    const jsonArea = document.getElementById("json");

    async function api(path, opt) {
      const headers = Object.assign({"X-API-Key": keyInput.value}, (opt && opt.headers) || {});
      const r = await fetch(path, Object.assign({}, opt, {headers}));
      const data = await r.json().catch(() => ({}));
      if (r.status === 401 || r.status === 403)
        throw new Error("Clé refusée — utilise API_SECRET_KEY de wouri-api");
      if (!r.ok) throw new Error(data.detail || JSON.stringify(data.errors || data) || ("Erreur " + r.status));
      return data;
    }

    function esc(s) {
      return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    async function refresh() {
      list.textContent = "Chargement…";
      const data = await api("/api/provider/baoule/tasks");
      const tasks = data.tasks || [];
      if (!tasks.length) {
        list.innerHTML = "<p class='hint'>Aucune tâche Bronze baoulé (<code>bci</code>).</p>";
        return;
      }
      list.innerHTML = tasks.map(t => `
        <article class="card" data-id="${esc(t.id)}">
          <div class="meta"><strong>${esc(t.intent || "—")}</strong> · ${esc(t.source || "")} · ${esc(t.status || "")}</div>
          <p class="local"><strong>Baoulé :</strong> ${esc(t.text_local || t.excerpt || "")}</p>
          <p class="fr"><strong>FR :</strong> ${esc(t.text_fr || "")}</p>
          <button data-d="admin_accepted">Accepter (sas ADC)</button>
          <button data-d="admin_rejected">Rejeter</button>
        </article>`).join("");
    }

    async function sendPayload(payload) {
      uploadMsg.textContent = "Envoi…";
      uploadMsg.className = "meta";
      const data = await api("/api/provider/baoule/upload-json", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      uploadMsg.className = "ok";
      uploadMsg.textContent = "OK — acceptées: " + data.accepted + (data.errors && data.errors.length ? " · erreurs: " + data.errors.join("; ") : "");
      await refresh();
    }

    document.getElementById("load").onclick = () => refresh().catch(e => { list.textContent = e.message; });
    document.getElementById("sendJson").onclick = () => {
      try {
        const payload = JSON.parse(jsonArea.value);
        sendPayload(payload).catch(e => { uploadMsg.className = "err"; uploadMsg.textContent = e.message; });
      } catch (e) {
        uploadMsg.className = "err";
        uploadMsg.textContent = "JSON invalide: " + e.message;
      }
    };
    document.getElementById("file").onchange = async (ev) => {
      const f = ev.target.files && ev.target.files[0];
      if (!f) return;
      try {
        const text = await f.text();
        jsonArea.value = text;
        const payload = JSON.parse(text);
        await sendPayload(payload);
      } catch (e) {
        uploadMsg.className = "err";
        uploadMsg.textContent = e.message;
      }
    };
    list.onclick = async (ev) => {
      const btn = ev.target.closest("button[data-d]");
      if (!btn) return;
      const id = btn.closest("[data-id]").dataset.id;
      try {
        await api("/admin/baoule/decision", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({id, decision: btn.dataset.d}),
        });
        await refresh();
      } catch (e) {
        list.textContent = e.message;
      }
    };
  </script>
</body>
</html>
"""


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


@router.get("/", response_class=HTMLResponse)
def baoule_admin_page():
    return HTMLResponse(_PAGE)


@router.post("/decision", dependencies=[Depends(require_api_key)])
def baoule_decision(body: DecisionBody):
    result = decide_task(body.id, body.decision)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "error"))
    return result


@router.get("/summary", dependencies=[Depends(require_api_key)])
def baoule_summary():
    bronze = list_tasks(status="bronze", language=BAOULE_CODE)
    accepted = list_tasks(status="admin_accepted", language=BAOULE_CODE)
    return {
        "language": BAOULE_CODE,
        "bronze": len(bronze),
        "admin_accepted": len(accepted),
    }
