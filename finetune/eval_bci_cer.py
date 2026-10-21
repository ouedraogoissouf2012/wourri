"""CER/WER baoulé d'un modèle Omnilingual, mesuré À L'IDENTIQUE du benchmark 0003 (#474, BAO-2).

Critère de BAO-2 (docs/wouri-planning/10) : le CER du modèle fine-tuné, mesuré sur le même jeu
(Common Voice bci test, 290 clips) et comparé aux 22,1 % du 1B de départ. L'UER de la recette
d'entraînement (fiche 0006) n'utilise pas la même normalisation : ce module refait la mesure avec
le protocole du benchmark 0003 :
- mêmes clips : révision épinglée, split test complet, aucun clip exclu ;
- même normalisation et même score (`normalize`, `score` : copie exacte de la cellule 3 de
  finetune/colab/asr_baoule_benchmark.ipynb, vérifiée par un test) ;
- même pipeline : ASRInferencePipeline, un clip à la fois, langue bci_Latn, dtype par défaut.

Le 1B de départ est remesuré dans la même session (témoin) : s'il ne retrouve pas ~22,1 %,
l'environnement diffère de celui du benchmark et la comparaison n'est pas recevable.

Le checkpoint fine-tuné est chargé par une carte fairseq2 qui hérite d'omniASR_CTC_1B (famille,
architecture, tokenizer) et pointe vers le dossier `step_N/model` écrit par l'entraînement
(pp_00/tp_00/sdp_00.pt, lu par le chargeur natif de fairseq2 0.6).

Usage (dans le Python 3.12 du notebook, après téléchargement du checkpoint) :
    python eval_bci_cer.py --checkpoint-root /tmp/wourri_ft --step step_1200

Ce module est recopié tel quel dans le notebook d'évaluation (cellule %%writefile) :
`python finetune/colab/sync_smoke_test_notebook.py` le resynchronise, un test le vérifie.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path

import jiwer

from prepare_bci_dataset import DATASET_REPO, REV, get_audio

BASE_CARD = "omniASR_CTC_1B"
# CER du 1B de départ au benchmark 0003 (docs/benchmarks/0003-asr-baoule-evaluation-results.md §1)
BENCHMARK_0003_CER = 0.221
BENCHMARK_0003_N = 290
# Écart toléré pour le témoin : au-delà, l'environnement n'est pas celui du benchmark 0003
CONTROL_TOLERANCE = 0.005
N_SAMPLES = 10

# ---- Copie exacte du benchmark 0003 (cellule 3) : ne pas modifier, un test compare les deux ----
# --- normalisation TOLERANTE : minuscule + ponctuation ASCII retiree.
# On CONSERVE les caracteres baoule (ɛ ɔ ʼ, tons) : ils portent le sens. ---
_PUNCT = re.compile(r"[.,!?;:«»\"'`()\[\]{}…—–/\\]")
def normalize(s):
    s = unicodedata.normalize("NFC", (s or "")).lower().strip()
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def score(refs, hyps):
    R, H = [], []
    for r, h in zip(refs, hyps):
        rn = normalize(r)
        if rn:                       # jiwer plante sur reference vide
            R.append(rn); H.append(normalize(h))
    return {"cer": float(jiwer.cer(R, H)), "wer": float(jiwer.wer(R, H)), "n": len(R)}
# ---- fin de la copie ----


def find_checkpoint(root, step) -> Path:
    """Dossier `<step>/model` du checkpoint téléchargé (contient pp_00/tp_00/sdp_00.pt)."""
    hits = sorted({p.parent.parent.parent for p in Path(root).rglob("sdp_*.pt")
                   if p.parent.parent.parent.parent.name == step})
    if len(hits) != 1:
        raise SystemExit(f"{len(hits)} checkpoint(s) {step}/model trouvé(s) sous {root} : 1 attendu")
    return hits[0].resolve()


def write_card(asset_dir, step, model_dir) -> str:
    """Carte fairseq2 du modèle fine-tuné : hérite de BASE_CARD, remplace son checkpoint."""
    if not (Path(model_dir) / "pp_00").is_dir():
        raise SystemExit(f"{model_dir} n'est pas un checkpoint fairseq2 (pp_00/ absent)")
    name = f"wourri_bci_ctc_1b_{step}"
    asset_dir = Path(asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / f"{name}.yaml").write_text(
        f"name: {name}\nbase: {BASE_CARD}\ncheckpoint: {Path(model_dir).resolve().as_posix()}\n",
        encoding="utf-8",
    )
    return name


def load_test_clips(load_dataset=None, limit=None):
    """(phrases de référence, [(waveform, sample rate)]) du split test, dans l'ordre du dataset."""
    if load_dataset is None:
        from datasets import load_dataset
    rows = list(load_dataset(DATASET_REPO, revision=REV, split="test"))
    rows = rows[:limit] if limit else rows
    return [r["sentence"] for r in rows], [get_audio(r) for r in rows]


def _default_pipeline(card):
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

    return ASRInferencePipeline(model_card=card)


def _free_gpu():
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def transcribe(card, paths, make_pipeline=None):
    """Transcriptions d'un modèle comme au benchmark 0003 (un clip à la fois, bci_Latn) + durées."""
    make_pipeline = make_pipeline or _default_pipeline
    t0 = time.time()
    pipe = make_pipeline(card)
    load_s = time.time() - t0
    t1 = time.time()
    hyps = list(pipe.transcribe(paths, lang=["bci_Latn"] * len(paths), batch_size=1))
    infer_s = time.time() - t1
    del pipe  # libère le modèle avant de charger le suivant (deux 1B ne tiennent pas sur un T4)
    _free_gpu()
    return hyps, round(load_s, 1), round(infer_s, 1)


def evaluate(models, out_path, load_dataset=None, make_pipeline=None, limit=None):
    """Mesure chaque (libellé, carte) sur les mêmes clips ; résultats écrits après chaque modèle."""
    import soundfile as sf

    refs, audios = load_test_clips(load_dataset, limit)
    tmp = tempfile.mkdtemp()
    paths = []
    for i, (wav, sr) in enumerate(audios):
        p = os.path.join(tmp, f"{i}.wav")
        sf.write(p, wav, sr)
        paths.append(p)
    out_path = Path(out_path)
    results = {}
    for label, card in models:
        hyps, load_s, infer_s = transcribe(card, paths, make_pipeline)
        r = score(refs, hyps)
        r.update(card=card, load_s=load_s, infer_s=infer_s,
                 empty_hyps=sum(1 for h in hyps if not normalize(h)),
                 samples=[{"ref": refs[i], "hyp": hyps[i]} for i in range(min(N_SAMPLES, len(hyps)))],
                 hyps=hyps)
        results[label] = r
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{label}: CER={r['cer'] * 100:.1f}%  WER={r['wer'] * 100:.1f}%  n={r['n']}  "
              f"vides={r['empty_hyps']}  (charg {load_s:.0f}s, infer {infer_s:.0f}s)", flush=True)
    return results


def control_ok(cer, n):
    """Le témoin (1B de départ) reproduit-il le benchmark 0003 : mêmes clips, ~22,1 % ?"""
    return n == BENCHMARK_0003_N and abs(cer - BENCHMARK_0003_CER) <= CONTROL_TOLERANCE


def report(results, base_label, ft_label):
    """Tableau, verdict du témoin, gain et exemples côte à côte (texte à recopier dans la fiche 0006)."""
    base, ft = results[base_label], results[ft_label]
    lines = [f"{'Modele':28s} {'CER':>7s} {'WER':>7s} {'n':>5s} {'vides':>6s}", "-" * 58]
    for label, r in results.items():
        lines.append(f"{label:28s} {r['cer'] * 100:6.1f}% {r['wer'] * 100:6.1f}% {r['n']:5d} {r['empty_hyps']:6d}")
    if control_ok(base["cer"], base["n"]):
        lines.append(f"\nTEMOIN OK : {base['cer'] * 100:.1f}% (benchmark 0003 : {BENCHMARK_0003_CER * 100:.1f}%)"
                     " -> comparaison recevable.")
    else:
        lines.append(f"\nTEMOIN ECART : {base['cer'] * 100:.1f}% sur {base['n']} clips, attendu "
                     f"{BENCHMARK_0003_CER * 100:.1f}% sur {BENCHMARK_0003_N} -> environnement different, "
                     "a signaler tel quel.")
    lines.append(f"Gain CER : {(base['cer'] - ft['cer']) * 100:+.1f} pts "
                 f"({base['cer'] * 100:.1f}% -> {ft['cer'] * 100:.1f}%)")
    lines.append("\n=== Exemples (reference | depart | fine-tune) ===")
    for i in range(min(len(base["samples"]), len(ft["samples"]))):
        lines.append(f"\n[{i}] REF : {base['samples'][i]['ref']}\n    DEP : {base['samples'][i]['hyp']}"
                     f"\n    FT  : {ft['samples'][i]['hyp']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--checkpoint-root", required=True, help="dossier où le checkpoint a été téléchargé")
    ap.add_argument("--step", default="step_1200", help="étape retenue sur dev (fiche 0006)")
    ap.add_argument("--asset-dir", default=None, help="répertoire de cartes fairseq2 (défaut : temporaire)")
    ap.add_argument("--out", default="eval_bci_cer_results.json")
    ap.add_argument("--limit", type=int, default=None, help="essai rapide sur N clips (défaut : les 290)")
    args = ap.parse_args(argv)

    asset_dir = args.asset_dir or tempfile.mkdtemp(prefix="fairseq2_assets_")
    card = write_card(asset_dir, args.step, find_checkpoint(args.checkpoint_root, args.step))
    # fairseq2 lit ce répertoire à sa première utilisation : à poser avant tout chargement de modèle.
    os.environ["FAIRSEQ2_USER_ASSET_DIR"] = str(asset_dir)

    base_label, ft_label = "temoin 1B depart", f"1B fine-tune {args.step}"
    results = evaluate([(base_label, BASE_CARD), (ft_label, card)], args.out, limit=args.limit)
    print("\n" + report(results, base_label, ft_label))
    print("\nResultats complets ->", args.out)


if __name__ == "__main__":
    main()
