"""Serveur voix baoulé (ADR-0045) : le paysan parle, il entend la voix du locuteur natif.

Tourne sur un GPU loué (RunPod), lancé par finetune/colab/serveur_voix_baoule_runpod.ipynb.

- `POST /transcribe` (clé `X-Api-Key`) : le vocal WhatsApp (ogg/opus, multipart `audio`)
  → texte baoulé, par le 1B fine-tuné (fiche 0007 : CER 13,4 %), avec le modèle de langue
  si `BCI_VOIX_LM` désigne le fichier retenu par mesure_lm_bci.py. Le serveur WhatsApp
  envoie ensuite ce texte à `/api/chat/` en langue « baoule ».
- `GET /audio/<nom>.ogg` : les réponses LUES par le locuteur pendant la dictée, converties
  en ogg/opus (format des notes vocales WhatsApp). L'API renvoie leur adresse
  (`BCI_AUDIO_BASE_URL`) ; aucune voix de synthèse.
- `GET /health`.

Réglages (variables d'environnement) : `BCI_VOIX_CLE` (clé partagée avec le serveur
WhatsApp), `BCI_VOIX_CARTE` (carte fairseq2 du modèle, cf. eval_bci_cer.write_card),
`BCI_VOIX_AUDIO` (dossier des réponses ogg), `BCI_VOIX_LM` (facultatif : lm_bci.pkl),
`BCI_VOIX_PROCESSEUR` (« 1 » : sans GPU, float32 + int8, ADR-0048 ; image finetune/voix).

Ce module est recopié tel quel dans le notebook (cellule %%writefile) :
`python finetune/colab/sync_smoke_test_notebook.py` le resynchronise, un test le vérifie.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

logger = logging.getLogger("voix_bci")

MAX_AUDIO_OCTETS = 10_000_000  # même plafond que la chaîne ASR de l'API
# Le pipeline Omnilingual refuse les audios de plus de 40 s : on garde les 39 premières.
DUREE_MAX_S = 39
NOM_AUDIO = re.compile(r"^[A-Za-z0-9_-]{1,80}\.ogg$")


def vers_wav_16k(data: bytes, dossier: str) -> str:
    """Audio quelconque (ogg/opus de WhatsApp, webm...) → WAV 16 kHz mono, par ffmpeg."""
    chemin = os.path.join(dossier, "vocal.wav")
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", "pipe:0", "-t", str(DUREE_MAX_S),
         "-ac", "1", "-ar", "16000", chemin],
        input=data, capture_output=True,
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode("utf-8", "replace")[-300:] or "ffmpeg a échoué")
    return chemin


def convertir_reponses(export_zip, dossier_ogg) -> int:
    """Chaque audio de l'export Dictée → `<nom>.ogg` (opus copié sans perte, ré-encodé sinon)."""
    out = Path(dossier_ogg)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(export_zip) as z, tempfile.TemporaryDirectory() as tmp:
        for nom in z.namelist():
            if not nom.lower().endswith((".webm", ".ogg", ".wav", ".m4a", ".mp3")):
                continue
            cible = out / f"{PurePosixPath(nom).stem}.ogg"
            if cible.exists():
                n += 1
                continue
            source = Path(tmp) / PurePosixPath(nom).name
            source.write_bytes(z.read(nom))
            copie = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-c:a", "copy", str(cible)]
            if subprocess.run(copie, capture_output=True).returncode != 0:
                encode = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-vn",
                          "-c:a", "libopus", "-b:a", "32k", str(cible)]
                subprocess.run(encode, capture_output=True, check=True)
            n += 1
    return n


def vers_int8(modele) -> int:
    """Couches linéaires en int8 (quantification dynamique de PyTorch), sur place (ADR-0048).

    Les couches de fairseq2 (`fairseq2.nn.Linear`) ne sont pas des `torch.nn.Linear` : la
    quantification ne les verrait pas. Chacune est recopiée en `torch.nn.Linear` (mêmes poids),
    quantifiée et remplacée AUSSITÔT : la mémoire ne dépasse jamais le modèle plus une couche
    (une copie complète avant quantification dépassait 7,6 Go et le conteneur était tué).
    Retourne le nombre de couches converties."""
    import torch
    from fairseq2.nn import Linear as LinearF2
    from torch.ao.nn.quantized.dynamic import Linear as LinearQ

    cibles = [nom for nom, m in modele.named_modules() if isinstance(m, LinearF2)]
    for nom in cibles:
        m = modele.get_submodule(nom)
        parent = modele.get_submodule(nom.rpartition(".")[0]) if "." in nom else modele
        lin = torch.nn.Linear(m.input_dim, m.output_dim, bias=m.bias is not None)
        with torch.no_grad():
            lin.weight.copy_(m.weight)
            if m.bias is not None:
                lin.bias.copy_(m.bias)
        lin.qconfig = torch.ao.quantization.default_dynamic_qconfig
        setattr(parent, nom.rpartition(".")[2], LinearQ.from_float(lin))
        del m, lin
    return len(cibles)


def charger_pipeline(carte, processeur=False):
    """Pipeline Omnilingual. `processeur` (ADR-0048, mesuré le 2026-10-27) : float32 puis int8 ;
    le bfloat16 par défaut du pipeline, fait pour le GPU, est beaucoup plus lent sur processeur."""
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

    if not processeur:
        return ASRInferencePipeline(model_card=carte)
    import torch

    pipe = ASRInferencePipeline(model_card=carte, device="cpu", dtype=torch.float32)
    logger.info("modele en int8 : %d couches", vers_int8(pipe.model))
    return pipe


def _pipeline_par_defaut():
    pipe = charger_pipeline(os.environ["BCI_VOIX_CARTE"], os.environ.get("BCI_VOIX_PROCESSEUR") == "1")
    if os.environ.get("BCI_VOIX_LM"):
        # Modèle de langue retenu par mesure_lm_bci.py (choisi sur dev) : recherche en faisceau.
        import pickle

        import lm_bci

        with open(os.environ["BCI_VOIX_LM"], "rb") as f:
            cfg = pickle.load(f)
        dec = lm_bci.decodeur(cfg["labels"], lm_bci.modele_pyctcdecode(cfg["trigramme"], cfg["alpha"], cfg["beta"]))
        lm_bci.brancher(pipe, cfg["ids"], cfg["labels"], decodeur=dec)
        logger.info("modele de langue charge (alpha=%s, beta=%s)", cfg["alpha"], cfg["beta"])
    return pipe


def creer_app(pipeline=None, decodeur=vers_wav_16k, cle=None, dossier_audio=None) -> FastAPI:
    """Application FastAPI ; pipeline et décodeur injectables (tests sans GPU ni ffmpeg)."""
    app = FastAPI(title="Wourri — voix baoulé")
    cle = cle if cle is not None else os.environ.get("BCI_VOIX_CLE", "")
    dossier_audio = Path(dossier_audio or os.environ.get("BCI_VOIX_AUDIO", "reponses_ogg"))
    etat = {"pipeline": pipeline}

    def _pipeline():
        if etat["pipeline"] is None:
            etat["pipeline"] = _pipeline_par_defaut()
        return etat["pipeline"]

    @app.get("/health")
    def health():
        return {"ok": True, "modele_charge": etat["pipeline"] is not None,
                "modele_langue": bool(os.environ.get("BCI_VOIX_LM")),
                "reponses_audio": len(list(dossier_audio.glob("*.ogg"))) if dossier_audio.is_dir() else 0}

    @app.post("/transcribe")
    async def transcribe(audio: UploadFile = File(...), x_api_key: str = Header(default="")):
        if not cle or not secrets.compare_digest(x_api_key, cle):
            raise HTTPException(status_code=401, detail="cle invalide")
        data = await audio.read()
        if not data:
            raise HTTPException(status_code=422, detail="audio vide")
        if len(data) > MAX_AUDIO_OCTETS:
            raise HTTPException(status_code=413, detail="audio trop volumineux")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                wav = decodeur(data, tmp)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"audio illisible : {exc}") from exc
            try:
                textes = _pipeline().transcribe([wav], lang=["bci_Latn"], batch_size=1)
            except Exception as exc:  # erreur du modèle : réponse claire, jamais de 500 muet
                logger.exception("transcription impossible")
                raise HTTPException(status_code=422, detail=f"transcription impossible : {type(exc).__name__}") from exc
        return {"text": (list(textes) or [""])[0].strip(), "language": "bci"}

    @app.get("/audio/{nom}")
    def audio_reponse(nom: str):
        if not NOM_AUDIO.match(nom):
            raise HTTPException(status_code=404, detail="introuvable")
        chemin = dossier_audio / nom
        if not chemin.is_file():
            raise HTTPException(status_code=404, detail="introuvable")
        return FileResponse(chemin, media_type="audio/ogg")

    return app


app = creer_app() if os.environ.get("BCI_VOIX_CLE") else None
