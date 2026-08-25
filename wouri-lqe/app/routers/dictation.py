"""Dictee guidee ASR (ADR-0035) — routeur mince. Le locuteur LIT des phrases imposees
(transcription garantie) ; l'admin importe le lot et exporte le dataset (format HF).
Isolation par langue heritee de la session (`user['lang']`)."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from app.data.language_registry import is_known
from app.routers.session import require_role
from app.services import dictation as svc
from app.services import dictation_repo as repo
from app.services.audio_store import LocalAudioStore

router = APIRouter(prefix="/dictation")

_ALLOWED_AUDIO = {"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4"}
_MAX_IMPORT = 5_000_000
_MAX_AUDIO = 15_000_000


@router.post("/import")
async def import_prompts(
    language: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(require_role("admin")),
):
    """Admin : importe un lot de phrases a lire (CSV/XLSX/JSON) pour `language`.
    Idempotent (re-import = les doublons sont ignores)."""
    lang = language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    raw = await file.read()
    if len(raw) > _MAX_IMPORT:
        raise HTTPException(status_code=400, detail="too_large")
    try:
        prompts = svc.parse_prompts(file.filename or "", raw)
    except Exception as exc:  # fichier illisible / format non reconnu
        raise HTTPException(status_code=400, detail=f"parse: {exc}") from exc
    if not prompts:
        raise HTTPException(status_code=400, detail="aucune_phrase_reconnue")
    return repo.import_prompts(language=lang, prompts=prompts)


@router.get("/prompts")
def list_prompts(status: str | None = None, user: dict = Depends(require_role("ingest"))):
    """Locuteur : les phrases de SA langue (filtre statut `todo`/`recorded` optionnel)."""
    st = (status or "").strip().lower() or None
    if st and st not in ("todo", "recorded"):
        raise HTTPException(status_code=400, detail="statut_invalide")
    rows = repo.list_prompts(language=user["lang"], status=st)
    return {"language": user["lang"], "prompts": rows, "count": len(rows)}


@router.get("/progress")
def progress(user: dict = Depends(require_role("ingest"))):
    """Locuteur : progression de la dictee (total / enregistrees / restantes)."""
    return repo.counts(language=user["lang"])


@router.get("/stats")
def stats(language: str, _: dict = Depends(require_role("admin"))):
    """Admin : progression de la dictee pour une `language` donnee (supervision avant export).
    Distinct de /progress (locuteur, langue de session)."""
    lang = language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    return repo.counts(language=lang)


@router.post("/{item_id}/audio")
async def submit_audio(
    item_id: str,
    audio: UploadFile = File(...),
    user: dict = Depends(require_role("ingest")),
):
    """Locuteur : enregistre l'audio d'UNE phrase de sa langue -> le prompt passe 'recorded'."""
    if repo.get(item_id=item_id, language=user["lang"]) is None:
        raise HTTPException(status_code=404, detail="prompt_introuvable")
    mime = (audio.content_type or "audio/webm").split(";")[0].strip()
    if mime not in _ALLOWED_AUDIO:
        raise HTTPException(status_code=400, detail="format_audio_non_supporte")
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="audio_vide")
    if len(raw) > _MAX_AUDIO:
        raise HTTPException(status_code=400, detail="audio_trop_grand")
    ref = LocalAudioStore().save(raw, mime=mime)
    if not repo.set_recorded(item_id=item_id, language=user["lang"], audio_url=ref, actor=user["u"]):
        raise HTTPException(status_code=409, detail="enregistrement_impossible")
    return {"ok": True, "id": str(item_id), "audio_url": ref}


@router.get("/export")
def export_dataset(language: str, _: dict = Depends(require_role("admin"))):
    """Admin : telecharge le dataset ASR de `language` (ZIP `audio/` + `metadata.csv`)."""
    lang = language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    data, n = svc.build_export_zip(language=lang)
    if n == 0:
        raise HTTPException(status_code=404, detail="aucun_enregistrement")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="dictee_{lang}_{n}.zip"'},
    )
