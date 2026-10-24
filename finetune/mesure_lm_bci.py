"""Mesure du modèle de langue baoulé sur le 2e fine-tune (#474) — à lancer sur la machine louée.

1. Corpus (lm_bci) : textes natifs (Common Voice validé, dictée, Zenodo, SMOL) et web filtré
   (`filtrer_baoule`), sans aucune phrase de dev NI du test ; pas la Bible. Dev sert à régler α et β :
   s'il était dans le corpus, le modèle de langue l'aurait vu mot pour mot et paraîtrait meilleur
   qu'il n'est (mesuré le 2026-10-24 : couverture des mots de dev 100 % contre 96 % au test).
2. Deux candidats : « natif » (textes natifs seuls) et « complet » (natif + web filtré).
3. Log-probabilités du modèle retenu (fiche 0007) sur dev et test, en une seule passe GPU.
4. Glouton (contrôle : il doit retrouver le CER de la fiche 0007) ; α et β réglés sur dev pour
   chaque candidat ; le candidat est choisi sur dev ; il n'est noté qu'UNE fois sur test.
5. Sorties : `mesure_lm_bci.json` ; `lm_bci.pkl` (modèle et réglages pour le serveur voix), écrit
   seulement si le modèle de langue fait mieux que le glouton sur dev.

Usage (Python 3.12 du notebook) :
    python mesure_lm_bci.py --cv27 /workspace/cv27/.../bci --dictee /workspace/dictee_bci_433.zip \\
        --zenodo /workspace/bci-datasets.zip --checkpoint-root /workspace/ft_nouveau --step step_3000 \\
        --out /workspace/lm --processus 14

Ce module est recopié tel quel dans le notebook (cellule %%writefile) : un test le vérifie.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pickle
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import cv27_split as cvs
import dictee_to_parquet as d2p
import lm_bci as lm

HF = "https://huggingface.co/datasets"
WEB = {
    "smolsent_en_bci.jsonl": f"{HF}/google/smol/resolve/main/smolsent/en_bci.jsonl",
    "smoldoc_en_bci.jsonl": f"{HF}/google/smol/resolve/main/smoldoc/en_bci.jsonl",
    "fineweb2_bci.parquet": f"{HF}/HuggingFaceFW/fineweb-2/resolve/main/data/bci_Latn/train/000_00000.parquet",
    "finepdfs_bci.parquet": f"{HF}/HuggingFaceFW/finepdfs/resolve/main/data/bci_Latn/train/000_00000.parquet",
    "glotcc_bci.parquet": f"{HF}/cis-lmu/GlotCC-V1/resolve/main/v1.0/bci-Latn/bci-Latn_0.parquet",
    "madlad_bci.csv": f"{HF}/AfriSpeech/madlad-91-african/resolve/main/Baoul%C3%A9_bci_v2.csv",
}
TOKENIZER = "https://dl.fbaipublicfiles.com/mms/omniASR_tokenizer.model"  # carte omniASR_CTC_1B
ALPHAS = (0.2, 0.4, 0.6, 0.8, 1.0)
BETAS = (0.0, 1.0, 2.0, 3.0)


def telecharger(dossier) -> Path:
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    for nom, url in {**WEB, "omniASR_tokenizer.model": TOKENIZER}.items():
        if not (d / nom).exists():
            urllib.request.urlretrieve(url, d / nom)
    return d


def textes_natifs(cv27_dir, dictee, zenodo, sources) -> list[str]:
    cv = [r["sentence"] for r in cvs._tsv(Path(cv27_dir) / "validated_sentences.tsv")]
    dic = [r["transcription"] for r in d2p.read_export(dictee)]
    with zipfile.ZipFile(zenodo) as z:
        zen = [r["bci"] for r in csv.DictReader(io.StringIO(z.read("bci-datasets/transcription.tsv").decode("utf-8-sig")),
                                               delimiter="\t")]
    smol = [t for f in ("smolsent_en_bci.jsonl", "smoldoc_en_bci.jsonl")
            for l in (Path(sources) / f).read_text(encoding="utf-8").splitlines() if l.strip()
            for t in json.loads(l).get("trgs", [])]
    return cv + dic + zen + smol


def textes_web(sources) -> list[str]:
    import pyarrow.parquet as pq

    d = Path(sources)
    docs = []
    for nom, col in (("fineweb2_bci.parquet", "text"), ("finepdfs_bci.parquet", "text"), ("glotcc_bci.parquet", "content")):
        docs += pq.read_table(d / nom, columns=[col]).column(col).to_pylist()
    csv.field_size_limit(10**9)
    with open(d / "madlad_bci.csv", encoding="utf-8") as f:
        docs += [r["local"] for r in csv.DictReader(f)]
    return [str(x) for x in docs if x]


def corpus(natifs, web, phrases_exclues) -> tuple[dict, dict]:
    """Lignes des deux candidats et comptes (phrases de dev et de test retirées, web écarté)."""
    natif, st_n = lm.preparer_corpus(natifs, phrases_exclues)
    ref = {w for l in natif for w in l.split()}
    web_lignes, st_w = lm.preparer_corpus(web, phrases_exclues)
    web_ok, ecartees = lm.filtrer_baoule(web_lignes, ref)
    stats = {"natif": st_n, "web": {**st_w, "ecartees_non_baoule": ecartees, "gardees": len(web_ok)}}
    return {"natif": natif, "complet": natif + web_ok}, stats


def pieces_tokenizer(path) -> list[str]:
    import sentencepiece as spm

    sp = spm.SentencePieceProcessor(model_file=str(path))
    return [sp.id_to_piece(i) for i in range(sp.get_piece_size())]


def capturer(card, rows, cv27_dir, ids, labels) -> tuple[list, list[str]]:
    """(matrices réduites, transcriptions gloutonnes) du modèle, clip par clip, dans l'ordre."""
    import soundfile as sf
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

    pipe = ASRInferencePipeline(model_card=card)
    mats = []
    lm.brancher(pipe, ids, labels, capture=mats)
    tmp = tempfile.mkdtemp()
    paths = []
    for i, r in enumerate(rows):
        wav, _ = d2p.decode_to_16k_mono((Path(cv27_dir) / "clips" / r["path"]).read_bytes(), r["path"])
        p = os.path.join(tmp, f"{i}.wav")
        sf.write(p, wav, d2p.TARGET_SR)
        paths.append(p)
    hyps = list(pipe.transcribe(paths, lang=["bci_Latn"] * len(paths), batch_size=1))
    return mats, hyps


def main(argv=None):
    import eval_bci_cer as ev

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for a in ("--cv27", "--dictee", "--zenodo", "--checkpoint-root", "--out"):
        ap.add_argument(a, required=True)
    ap.add_argument("--step", default="step_3000")
    ap.add_argument("--sources", default=None, help="dossier des textes (défaut : <out>/sources)")
    ap.add_argument("--processus", type=int, default=0)
    ap.add_argument("--beam", type=int, default=64)
    args = ap.parse_args(argv)

    out = Path(args.out)
    sources = telecharger(args.sources or out / "sources")
    rep, _ = cvs.preparer(args.cv27)
    phrases_test = [r["sentence"] for r in rep["test"]]
    exclues = phrases_test + [r["sentence"] for r in rep["dev"]]
    candidats, stats = corpus(textes_natifs(args.cv27, args.dictee, args.zenodo, sources), textes_web(sources), exclues)
    print("Corpus :", json.dumps(stats, ensure_ascii=False), flush=True)
    ids, labels = lm.colonnes(pieces_tokenizer(sources / "omniASR_tokenizer.model"), lm.alphabet_de(candidats["natif"]))

    asset_dir = tempfile.mkdtemp(prefix="fairseq2_assets_")
    card = ev.write_card(asset_dir, args.step, ev.find_checkpoint(args.checkpoint_root, args.step), "wourri_bci_nouveau")
    os.environ["FAIRSEQ2_USER_ASSET_DIR"] = asset_dir
    mats, hyps = capturer(card, rep["dev"] + rep["test"], args.cv27, ids, labels)
    n_dev = len(rep["dev"])
    refs = {"dev": [r["sentence"] for r in rep["dev"]], "test": phrases_test}
    m = {"dev": mats[:n_dev], "test": mats[n_dev:]}
    resultats = {"corpus": stats, "colonnes": len(ids),
                 "glouton": {s: ev.score(refs[s], h) for s, h in (("dev", hyps[:n_dev]), ("test", hyps[n_dev:]))}}
    print("Glouton :", {s: round(r["cer"] * 100, 2) for s, r in resultats["glouton"].items()}, flush=True)

    tris = {nom: lm.Trigramme(lignes) for nom, lignes in candidats.items()}
    resultats["candidats"] = {nom: lm.regler(m["dev"], refs["dev"], labels, tri, ALPHAS, BETAS, ev.score,
                                             args.beam, args.processus) for nom, tri in tris.items()}
    nom = min(resultats["candidats"], key=lambda k: resultats["candidats"][k]["meilleur"]["cer"])
    best = resultats["candidats"][nom]["meilleur"]
    dec = lm.decodeur(labels, lm.modele_pyctcdecode(tris[nom], best["alpha"], best["beta"]))
    hyps_test = lm.decoder_tout(dec, m["test"], args.beam, args.processus)
    resultats["retenu"] = {"lm": nom, **best}
    resultats["test"] = {"glouton": resultats["glouton"]["test"], "lm": ev.score(refs["test"], hyps_test)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "mesure_lm_bci.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1, default=str),
                                            encoding="utf-8")
    if best["cer"] < resultats["glouton"]["dev"]["cer"]:
        with open(out / "lm_bci.pkl", "wb") as f:
            pickle.dump({"trigramme": tris[nom], "alpha": best["alpha"], "beta": best["beta"],
                         "ids": ids, "labels": labels}, f)
    g, l = resultats["test"]["glouton"], resultats["test"]["lm"]
    print(f"\nRetenu sur dev : modèle « {nom} », α={best['alpha']}, β={best['beta']} "
          f"(CER dev {resultats['glouton']['dev']['cer'] * 100:.1f} % -> {best['cer'] * 100:.1f} %)")
    print(f"TEST ({len(phrases_test)} clips) : CER {g['cer'] * 100:.1f} % -> {l['cer'] * 100:.1f} % | "
          f"WER {g['wer'] * 100:.1f} % -> {l['wer'] * 100:.1f} %")
    print("Serveur voix :", (out / "lm_bci.pkl") if (out / "lm_bci.pkl").exists()
          else "glouton (le modèle de langue ne gagne pas sur dev)")


if __name__ == "__main__":
    main()
