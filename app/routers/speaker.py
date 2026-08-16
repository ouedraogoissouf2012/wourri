"""Écran locuteur FR — file dyu (#433). Auth = Better Auth (Convex), session cookie locale."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.improvement_queue import decide_task, list_tasks
from app.services.speaker_session import (
    COOKIE_NAME,
    read_session,
    sign_session,
    verify_better_auth,
)

router = APIRouter(prefix="/speaker", tags=["Speaker LQE"])

_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>WOURI — Locuteur dioula CI</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }}
    h1 {{ font-size: 1.25rem; }}
    .hint {{ color: #444; font-size: .92rem; }}
    .err {{ color: #9b2c2c; }}
    .card {{ border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin: .75rem 0; }}
    input, button {{ font-size: 1rem; padding: .4rem .6rem; margin: .25rem 0; }}
    input[type=email], input[type=password] {{ width: 100%; max-width: 22rem; }}
  </style>
</head>
<body>
  <h1>Locuteur — dioula de Côte d’Ivoire</h1>
  <p class="hint">Interface en français. Vous ne voyez que la file <strong>dyu</strong>.
  Valider ici ne publie pas le corpus (sas admin ensuite).</p>
  {body}
</body>
</html>
"""


def _html(body: str) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(body=body))


@router.get("/", response_class=HTMLResponse)
async def speaker_home(request: Request):
    sess = read_session(request.cookies.get(COOKIE_NAME))
    if not sess:
        return _html(
            """
            <p class="hint">Connexion Better Auth (compte locuteur créé par l’admin Convex).</p>
            <form method="post" action="/speaker/login">
              <div><label>Email<br/><input name="email" type="email" required autocomplete="username"/></label></div>
              <div><label>Mot de passe<br/><input name="password" type="password" required autocomplete="current-password" minlength="12"/></label></div>
              <button type="submit">Se connecter</button>
            </form>
            """
        )
    tasks = list_tasks(status="bronze", language="dyu")
    if not tasks:
        cards = "<p>Aucune phrase Bronze dyu pour le moment.</p>"
    else:
        parts = []
        for t in tasks:
            parts.append(
                f"""
                <article class="card">
                  <div><strong>{t.get("intent") or "—"}</strong> · {t.get("source") or ""}</div>
                  <p>{(t.get("excerpt") or "").replace("<", "")}</p>
                  <form method="post" action="/speaker/decide" style="display:inline">
                    <input type="hidden" name="id" value="{t.get("id") or ""}"/>
                    <input type="hidden" name="decision" value="admin_accepted"/>
                    <button type="submit">Valider (vers admin)</button>
                  </form>
                  <form method="post" action="/speaker/decide" style="display:inline">
                    <input type="hidden" name="id" value="{t.get("id") or ""}"/>
                    <input type="hidden" name="decision" value="admin_rejected"/>
                    <button type="submit">Rejeter</button>
                  </form>
                </article>
                """
            )
        cards = "".join(parts)
    return _html(
        f"""
        <p>Connecté : <strong>{sess["email"]}</strong> · langue <strong>dyu</strong>
        <a href="/speaker/logout">Déconnexion</a></p>
        {cards}
        """
    )


@router.post("/login")
async def speaker_login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
):
    ok = await verify_better_auth(email, password)
    if not ok:
        return _html(
            """
            <p class="err">Connexion refusée. Vérifiez email / mot de passe
            (Better Auth + AUTH_EMAIL_PASSWORD_ENABLED côté Convex).</p>
            <p><a href="/speaker/">Réessayer</a></p>
            """
        )
    from app.config import get_settings

    token = sign_session(email)
    resp = RedirectResponse("/speaker/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
        secure=get_settings().is_production,
    )
    return resp


@router.get("/logout")
async def speaker_logout():
    resp = RedirectResponse("/speaker/", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.post("/decide")
async def speaker_decide(
    request: Request,
    id: str = Form(...),
    decision: str = Form(...),
):
    sess = read_session(request.cookies.get(COOKIE_NAME))
    if not sess:
        return RedirectResponse("/speaker/", status_code=303)
    mapped = (
        "speaker_accepted"
        if decision == "admin_accepted"
        else "speaker_rejected"
        if decision == "admin_rejected"
        else ""
    )
    if not mapped:
        return RedirectResponse("/speaker/", status_code=303)
    decide_task(id, mapped)
    return RedirectResponse("/speaker/", status_code=303)
