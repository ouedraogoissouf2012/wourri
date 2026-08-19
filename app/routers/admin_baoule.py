"""Écran Baoulé (#443) — login user/mdp + upload JSON/CSV/XLSX + file Bronze.

Compte : BAOULE_PROVIDER_USER / BAOULE_PROVIDER_PASSWORD (Dokploy).
Aucune publication corpus.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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


def _session_user(request: Request) -> str | None:
    sess = read_session(request.cookies.get(COOKIE_NAME))
    return sess.get("u") if sess else None


def require_baoule_session(request: Request) -> str:
    user = _session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return user


_LOGIN = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>WOURI — Connexion Baoulé</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 28rem; margin: 3rem auto; padding: 0 1rem; }}
    input {{ width: 100%; padding: .5rem; margin: .35rem 0 0.8rem; box-sizing: border-box; }}
    button {{ padding: .5rem 1rem; }}
    .err {{ color: #9b2c2c; }}
    .hint {{ color: #555; font-size: .9rem; }}
  </style>
</head>
<body>
  <h1>Provider Baoulé</h1>
  <p class="hint">Compte utilisateur + mot de passe (pas la clé API moteur).</p>
  {err}
  <form method="post" action="/admin/baoule/login">
    <label>Utilisateur<br/><input name="username" autocomplete="username" required/></label>
    <label>Mot de passe<br/><input name="password" type="password" autocomplete="current-password" required minlength="8"/></label>
    <button type="submit">Se connecter</button>
  </form>
</body>
</html>
"""

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
    button { margin-right: .5rem; padding: .4rem .75rem; cursor: pointer; }
    #uploadbox { margin: 1rem 0; padding: 1rem; border: 1px dashed #aaa; border-radius: 8px; }
    textarea { width: 100%; min-height: 7rem; font-family: ui-monospace, monospace; font-size: .85rem; }
    .ok { color: #1b6b2a; }
    .err { color: #9b2c2c; }
    .meta { font-size: .85rem; color: #555; }
    .top { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
    .tabs { display: flex; gap: .35rem; margin: 1rem 0; flex-wrap: wrap; }
    .tabs button { background: #eee; border: 1px solid #ccc; border-radius: 6px 6px 0 0; }
    .tabs button.active { background: #0f3d24; color: #fff; border-color: #0f3d24; }
    .panel { display: none; }
    .panel.active { display: block; }
    #toast { position: sticky; top: 0; background: #fff3cd; border: 1px solid #e6c200; padding: .5rem .75rem; margin: .5rem 0; display: none; }
  </style>
</head>
<body>
  <div class="top">
    <h1>Provider Baoulé (<code>bci</code>)</h1>
    <p class="meta">Connecté : <strong id="who"></strong> · <a href="/admin/baoule/logout">Déconnexion</a></p>
  </div>
  <p class="hint">
    Upload <strong>JSON, CSV ou Excel (.xlsx)</strong> → <strong>Bronze</strong>.
    Les doublons (même texte ou même id) sont <strong>ignorés</strong>.
    Données persistées (survit au Redeploy). Ne publie pas le dioula WhatsApp.
  </p>
  <div id="toast"></div>

  <div class="tabs">
    <button type="button" class="tab active" data-tab="upload">1. Ajouter</button>
    <button type="button" class="tab" data-tab="bronze">2. À accepter <span id="nBronze"></span></button>
    <button type="button" class="tab" data-tab="accepted">3. À promouvoir <span id="nAccepted"></span></button>
    <button type="button" class="tab" data-tab="corpus">4. Corpus baoulé <span id="nCorpus"></span></button>
  </div>

  <div id="panel-upload" class="panel active">
  <h2>Ajouter des phrases</h2>
  <div id="uploadbox">
    <p class="hint">
      Colonnes CSV/Excel : <code>text_local</code> (ou baoule) + <code>text_fr</code> (ou francais).
      Optionnel : id, intent, cultures, region, notes.
    </p>
    <p>
      <label>Fichier
        <input id="file" type="file" accept=".json,.csv,.xlsx,application/json,text/csv"/>
      </label>
      <button type="button" id="sendFile">Envoyer le fichier</button>
    </p>
    <p class="hint">Ou coller du JSON :</p>
    <textarea id="json">[
  {
    "id": "bci_001",
    "language": "bci",
    "text_local": "(phrase baoulé)",
    "text_fr": "(français)",
    "intent": "CONSEIL_PRODUCTION"
  }
]</textarea>
    <p><button type="button" id="sendJson">Envoyer le JSON</button></p>
    <p id="uploadMsg" class="meta"></p>
  </div>
  <div class="card" style="background:#fff8e6;border-color:#e6c200">
    <strong>Non-lecteurs</strong>
    <p class="hint" style="margin:.4rem 0 0">Produit final = voix d'abord. Colonne optionnelle <code>audio_url</code>. Sans audio = pas prêt pour canal vocal.</p>
  </div>
  </div>

  <div id="panel-bronze" class="panel">
    <h2>À accepter (Bronze)</h2>
    <p class="hint">Accepter → passe dans l'onglet « À promouvoir ». Rejeter → sort de la file active.</p>
    <p><button type="button" id="loadB">Rafraîchir</button></p>
    <div id="listBronze" class="hint">—</div>
  </div>

  <div id="panel-accepted" class="panel">
    <h2>À promouvoir (Acceptées)</h2>
    <p class="hint">Promouvoir → corpus baoulé atelier (pas WhatsApp dioula).</p>
    <p><button type="button" id="loadA">Rafraîchir</button></p>
    <div id="listAccepted" class="hint">—</div>
  </div>

  <div id="panel-corpus" class="panel">
    <h2>Corpus baoulé (Production atelier)</h2>
    <p class="hint">Phrases déjà promues. Persistées sur le serveur.</p>
    <p><button type="button" id="loadC">Rafraîchir</button></p>
    <div id="listCorpus" class="hint">—</div>
  </div>

  <script>
    const uploadMsg = document.getElementById("uploadMsg");
    const jsonArea = document.getElementById("json");
    const toast = document.getElementById("toast");
    let cache = { bronze: [], accepted: [], corpus: [] };

    function showToast(msg, isErr) {
      toast.style.display = "block";
      toast.style.background = isErr ? "#fdecea" : "#e8f5e9";
      toast.style.borderColor = isErr ? "#c62828" : "#2e7d32";
      toast.textContent = msg;
      setTimeout(() => { toast.style.display = "none"; }, 5000);
    }

    async function api(path, opt) {
      const r = await fetch(path, Object.assign({credentials: "same-origin"}, opt || {}));
      if (r.status === 401) { location.href = "/admin/baoule/"; throw new Error("Session expirée"); }
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        const d = data.detail;
        throw new Error((typeof d === "string" ? d : data.reason) || (data.errors && data.errors.join("; ")) || ("Erreur " + r.status));
      }
      return data;
    }

    function esc(s) {
      return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function card(t, mode) {
      const audio = t.audio_url
        ? `<p class="meta">Audio : ${esc(t.audio_url)}</p>`
        : `<p class="meta">⚠ Pas d'audio</p>`;
      let actions = "";
      if (mode === "bronze") {
        actions = `<button data-d="admin_accepted">Accepter → à promouvoir</button>
          <button data-d="admin_rejected">Rejeter</button>`;
      } else if (mode === "accepted") {
        actions = `<button data-p="1">Promouvoir au corpus baoulé</button>`;
      }
      return `<article class="card" data-id="${esc(t.id)}">
          <div class="meta"><strong>${esc(t.intent || "—")}</strong> · ${esc(t.source || "")} · ${esc(t.status || "")}</div>
          <p class="local"><strong>Baoulé :</strong> ${esc(t.text_local || t.excerpt || "")}</p>
          <p><strong>FR :</strong> ${esc(t.text_fr || "")}</p>
          ${audio}${actions}
        </article>`;
    }

    function renderLists() {
      const b = cache.bronze || [];
      const a = cache.accepted || [];
      const c = cache.corpus || [];
      document.getElementById("nBronze").textContent = b.length ? "(" + b.length + ")" : "";
      document.getElementById("nAccepted").textContent = a.length ? "(" + a.length + ")" : "";
      document.getElementById("nCorpus").textContent = c.length ? "(" + c.length + ")" : "";
      document.getElementById("listBronze").innerHTML = b.length
        ? b.map(t => card(t, "bronze")).join("")
        : "<p class='hint'>Aucune phrase Bronze.</p>";
      document.getElementById("listAccepted").innerHTML = a.length
        ? a.map(t => card(t, "accepted")).join("")
        : "<p class='hint'>Rien à promouvoir. Accepte d'abord dans l'onglet Bronze.</p>";
      document.getElementById("listCorpus").innerHTML = c.length
        ? c.slice().reverse().map(t => `
          <article class="card">
            <div class="meta">production · ${esc(t.promoted_at || "")}</div>
            <p class="local"><strong>Baoulé :</strong> ${esc(t.text_local || "")}</p>
            <p><strong>FR :</strong> ${esc(t.text_fr || "")}</p>
            <p class="meta">${t.audio_url ? "Audio: " + esc(t.audio_url) : "Sans audio"}</p>
          </article>`).join("")
        : "<p class='hint'>Corpus baoulé vide.</p>";
    }

    async function refresh() {
      const data = await api("/admin/baoule/api/tasks");
      document.getElementById("who").textContent = data.user || "—";
      cache.bronze = data.bronze || [];
      cache.accepted = data.accepted || [];
      const corp = await api("/admin/baoule/api/corpus");
      cache.corpus = corp.entries || [];
      renderLists();
    }

    document.querySelectorAll(".tab").forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("panel-" + btn.dataset.tab).classList.add("active");
      };
    });

    async function afterUpload(data, label) {
      const dup = data.duplicates_skipped || 0;
      uploadMsg.className = "ok";
      uploadMsg.textContent = "OK — nouvelles: " + (data.accepted || 0)
        + (dup ? " · doublons ignorés: " + dup : "")
        + (label ? " (" + label + ")" : "");
      await refresh();
      document.querySelector('.tab[data-tab="bronze"]').click();
    }

    document.getElementById("loadB").onclick = () => refresh().catch(e => showToast(e.message, true));
    document.getElementById("loadA").onclick = () => refresh().catch(e => showToast(e.message, true));
    document.getElementById("loadC").onclick = () => refresh().catch(e => showToast(e.message, true));

    document.getElementById("sendJson").onclick = () => {
      try {
        const payload = JSON.parse(jsonArea.value);
        uploadMsg.textContent = "Envoi…";
        api("/admin/baoule/api/upload-json", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        }).then(d => afterUpload(d)).catch(e => { uploadMsg.className = "err"; uploadMsg.textContent = e.message; });
      } catch (e) {
        uploadMsg.className = "err";
        uploadMsg.textContent = "JSON invalide: " + e.message;
      }
    };
    document.getElementById("sendFile").onclick = async () => {
      const f = document.getElementById("file").files[0];
      if (!f) { uploadMsg.className = "err"; uploadMsg.textContent = "Choisis un fichier"; return; }
      const fd = new FormData();
      fd.append("file", f);
      uploadMsg.textContent = "Envoi…";
      try {
        const data = await api("/admin/baoule/api/upload", { method: "POST", body: fd });
        await afterUpload(data, f.name);
      } catch (e) {
        uploadMsg.className = "err";
        uploadMsg.textContent = e.message;
      }
    };

    document.body.addEventListener("click", async (ev) => {
      const btnD = ev.target.closest("button[data-d]");
      const btnP = ev.target.closest("button[data-p]");
      if (!btnD && !btnP) return;
      const art = ev.target.closest("[data-id]");
      if (!art) return;
      const id = art.dataset.id;
      try {
        if (btnD) {
          await api("/admin/baoule/api/decision", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id, decision: btnD.dataset.d}),
          });
          showToast(btnD.dataset.d === "admin_accepted" ? "Acceptée → onglet À promouvoir" : "Rejetée");
          if (btnD.dataset.d === "admin_accepted") {
            document.querySelector('.tab[data-tab="accepted"]').click();
          }
        } else {
          await api("/admin/baoule/api/promote", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id}),
          });
          showToast("Promue au corpus baoulé");
          document.querySelector('.tab[data-tab="corpus"]').click();
        }
        await refresh();
      } catch (e) {
        showToast("Erreur: " + e.message, true);
        refresh().catch(() => {});
      }
    });

    refresh().catch(e => showToast(e.message, true));
  </script>
</body>
</html>
"""


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


class PromoteBody(BaseModel):
    id: str = Field(min_length=1)


@router.get("/", response_class=HTMLResponse)
def baoule_home(request: Request):
    if not is_configured():
        return HTMLResponse(
            _LOGIN.format(
                err="<p class='err'>Compte non configuré. Dokploy : "
                "BAOULE_PROVIDER_USER et BAOULE_PROVIDER_PASSWORD (min 8 car.).</p>"
            ),
            status_code=503,
        )
    if not _session_user(request):
        return HTMLResponse(_LOGIN.format(err=""))
    return HTMLResponse(_PAGE)


@router.post("/login")
async def baoule_login(
    username: str = Form(...),
    password: str = Form(...),
):
    if not verify_password(username, password):
        return HTMLResponse(
            _LOGIN.format(err="<p class='err'>Identifiants incorrects.</p>"),
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
