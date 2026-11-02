"""Mesure du serveur voix baoulé sur processeur (ADR-0048), avant toute mise en service.

Trois questions, dans le conteneur de finetune/voix/Dockerfile, avec le nombre de cœurs qu'on
lui donnera en production (`--threads`) :
1. Qualité : le processeur retrouve-t-il le CER du GPU ? Décodage glouton sur le test du
   2e fine-tune (623 clips, cv27_split, protocole 0003). Fiche 0007 : 13,4 % sur GPU.
2. Vitesse : secondes de calcul pour un vocal de 5, 10 et 30 s (clips du test mis bout à bout),
   avec le modèle de langue si `--lm` est donné (configuration du serveur). Seuil du
   valideur (2026-10-27) : moins de 5 s pour un vocal de 10 s.
3. Mémoire : pic de mémoire résidente du processus.

Usage (dans le conteneur) :
    python mesure_cpu_bci.py --cv27 /cv27/bci --checkpoint-root /modele --threads 4 \\
        --out /sortie/mesure_cpu_bci.json [--lm /donnees/lm_bci.pkl] [--limit 50]

Vitesse seule, sur le serveur (sans copier Common Voice) : `--audios /donnees/reponses_ogg
--limit 20` met bout à bout des réponses lues par le locuteur ; pas de mesure de qualité.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path

import cv27_split as cvs
import dictee_to_parquet as d2p
import eval_bci_cer as ev

DUREES_S = (5, 10, 30)
REPETITIONS = 3


def vocaux_synthetiques(audios, durees=DUREES_S, sr=None) -> dict[int, object]:
    """{durée: signal} : clips mis bout à bout jusqu'à la durée voulue, puis coupés net."""
    import numpy as np

    sr = sr or d2p.TARGET_SR
    tout = np.concatenate([a for a, _ in audios])
    out = {}
    for d in durees:
        n = int(d * sr)
        if len(tout) < n:
            raise SystemExit(f"pas assez d'audio pour un vocal de {d} s")
        out[d] = tout[:n]
    return out


def audios_du_dossier(dossier, limite=None) -> list[tuple[object, int]]:
    """[(signal 16 kHz, sr)] des fichiers ogg/wav du dossier, dans l'ordre des noms."""
    fichiers = sorted(p for p in Path(dossier).iterdir() if p.suffix.lower() in (".ogg", ".wav"))[:limite]
    return [(d2p.decode_to_16k_mono(p.read_bytes(), p.name)[0], d2p.TARGET_SR) for p in fichiers]


def chronometrer(transcrire, chemins, repetitions=REPETITIONS, horloge=time.perf_counter) -> float:
    """Médiane des secondes pour transcrire chaque fichier, un appel à la fois (comme le serveur)."""
    temps = []
    for _ in range(repetitions):
        for c in chemins:
            t0 = horloge()
            transcrire(c)
            temps.append(horloge() - t0)
    return statistics.median(temps)


def memoire_max_go() -> float | None:
    try:
        import resource
    except ImportError:  # Windows : pas de mesure (le conteneur est sous Linux)
        return None
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for a in ("--checkpoint-root", "--out"):
        ap.add_argument(a, required=True)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--cv27", help="test du 2e fine-tune : qualité et vitesse")
    source.add_argument("--audios", help="dossier d'audios (ogg/wav) : vitesse seule")
    ap.add_argument("--step", default="step_3000")
    ap.add_argument("--threads", type=int, required=True, help="cœurs donnés au serveur en production")
    ap.add_argument("--lm", help="lm_bci.pkl : latence mesurée avec le modèle de langue")
    ap.add_argument("--limit", type=int, help="nombre de clips du test (défaut : les 623)")
    # Le pipeline calcule en bfloat16 par défaut (fait pour le GPU) ; sur un processeur sans
    # instructions bfloat16, le float32 peut être bien plus rapide : on mesure, on ne suppose pas.
    ap.add_argument("--dtype", choices=("float32", "bfloat16"), default="float32")
    ap.add_argument("--int8", action="store_true",
                    help="couches linéaires quantifiées en int8 (serveur_voix_bci.vers_int8)")
    ap.add_argument("--details", help="fichier des transcriptions clip par clip (local : Common Voice "
                                      "interdit de republier ses phrases, jamais sur git)")
    args = ap.parse_args(argv)

    import soundfile as sf
    import torch

    torch.set_num_threads(args.threads)
    asset_dir = tempfile.mkdtemp(prefix="fairseq2_assets_")
    os.environ["FAIRSEQ2_USER_ASSET_DIR"] = asset_dir
    card = ev.write_card(asset_dir, args.step, ev.find_checkpoint(args.checkpoint_root, args.step), "wourri_bci_cpu")

    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
    from serveur_voix_bci import vers_int8

    t0 = time.perf_counter()
    pipe = ASRInferencePipeline(model_card=card, device="cpu", dtype=getattr(torch, args.dtype))
    converties = vers_int8(pipe.model) if args.int8 else 0
    chargement = time.perf_counter() - t0
    transcrire = lambda chemin: pipe.transcribe([chemin], lang=["bci_Latn"], batch_size=1)[0]

    tmp = Path(tempfile.mkdtemp())
    refs, hyps, par_clip, audios = [], [], [], []
    test = []
    if args.audios:
        audios = audios_du_dossier(args.audios, args.limit)
    else:
        rep, _ = cvs.preparer(args.cv27)
        test = rep["test"][: args.limit] if args.limit else rep["test"]
    for i, r in enumerate(test):
        wav, _ = d2p.decode_to_16k_mono((Path(args.cv27) / "clips" / r["path"]).read_bytes(), r["path"])
        chemin = tmp / f"{i}.wav"
        sf.write(chemin, wav, d2p.TARGET_SR)
        t = time.perf_counter()
        hyps.append(transcrire(str(chemin)))
        par_clip.append((time.perf_counter() - t, len(wav) / d2p.TARGET_SR))
        refs.append(r["sentence"])
        audios.append((wav, d2p.TARGET_SR))
    qualite = {**ev.score(refs, hyps), "vides": sum(1 for h in hyps if not h.strip())} if test else {}
    if args.details:
        Path(args.details).write_text(json.dumps([{"client": r["client_id"][:8], "ref": r["sentence"], "hyp": h}
                                                  for r, h in zip(test, hyps)], ensure_ascii=False, indent=1),
                                      encoding="utf-8")

    vocaux = {}
    for d, signal in vocaux_synthetiques(audios).items():
        sf.write(tmp / f"vocal_{d}s.wav", signal, d2p.TARGET_SR)
        vocaux[d] = str(tmp / f"vocal_{d}s.wav")
    latence = {"glouton": {str(d): round(chronometrer(transcrire, [c]), 2) for d, c in vocaux.items()}}
    if args.lm:
        import pickle

        import lm_bci

        with open(args.lm, "rb") as f:
            cfg = pickle.load(f)
        dec = lm_bci.decodeur(cfg["labels"], lm_bci.modele_pyctcdecode(cfg["trigramme"], cfg["alpha"], cfg["beta"]))
        lm_bci.brancher(pipe, cfg["ids"], cfg["labels"], decodeur=dec)
        latence["modele_langue"] = {str(d): round(chronometrer(transcrire, [c]), 2) for d, c in vocaux.items()}

    rtf = [s / d for s, d in par_clip if d > 0]
    resultat = {
        "materiel": {"processeur": platform.processor() or platform.machine(), "coeurs_visibles": os.cpu_count(),
                     "threads": args.threads, "dtype": args.dtype, "int8_couches": converties,
                     "torch": torch.__version__},
        "chargement_s": round(chargement, 1),
        "memoire_max_go": memoire_max_go(),
        "test": {**qualite, "clips": len(test)},
        "par_clip": {"rtf_median": round(statistics.median(rtf), 3),
                     "p90_s": round(sorted(s for s, _ in par_clip)[int(0.9 * (len(par_clip) - 1))], 2)} if rtf else {},
        "latence_s_par_duree_de_vocal": latence,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resultat, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
