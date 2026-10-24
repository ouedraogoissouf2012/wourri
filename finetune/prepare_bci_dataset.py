"""Prépare le dataset baoulé du fine-tune Omnilingual (#474, ADR-0044).

Common Voice bci (miroir Klayt, révision épinglée du benchmark 0003) :
    train -> split « train », validation -> « dev », test -> « test » (avec --with-test)
+ l'export de l'écran Dictée de l'atelier (optionnel) -> corpus « wourri_dictee », split « train »,
puis le TSV de statistiques et la carte dataset fairseq2.

Le split « test » (290 clips, ceux du benchmark 0003) n'est JAMAIS entraîné : la recette
n'entraîne que sur `train_split: train`. Il est seulement évalué (`valid_split: dev,test`) pour
comparer, dans les mêmes conditions, le modèle de départ et le modèle fine-tuné. La séparation
locuteurs / phrases entre ces splits est vérifiée (docs/benchmarks/0005 §3).

Usage (dans le Python 3.12 du notebook) :
    python prepare_bci_dataset.py --work /workspace --dictee /workspace --with-test

Ce module est recopié tel quel dans les notebooks de finetune/colab/ (cellule %%writefile) :
`python finetune/colab/sync_smoke_test_notebook.py` les resynchronise, un test le vérifie.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

import dictee_to_parquet as d2p

DATASET_REPO = "Klayt/baoule-common-voice"
REV = "176d5f8ad6c04e5ca1a0e66770866709bcbb338b"  # même révision que le benchmark 0003
# split Hugging Face -> split de la recette (« dev » : nom attendu par valid_split)
CV_SPLITS = {"train": "train", "validation": "dev", "test": "test"}
CARD_NAME = "wourri_bci"


def get_audio(row):
    """Audio d'une ligne Hugging Face -> (waveform float32 mono, sample rate)."""
    import numpy as np

    a = row["audio"]
    if isinstance(a, dict):  # datasets < 4.0
        return np.asarray(a["array"], dtype="float32"), int(a["sampling_rate"])
    samples = a.get_all_samples()  # datasets >= 4.0 (AudioDecoder)
    return samples.data.numpy().squeeze().astype("float32"), int(samples.sample_rate)


def cv_examples(hf_split, load_dataset=None):
    """[(phrase, waveform 16 kHz)] du split Common Voice demandé."""
    if load_dataset is None:
        from datasets import load_dataset
    for row in load_dataset(DATASET_REPO, revision=REV, split=hf_split):
        wav, sr = get_audio(row)
        if sr != d2p.TARGET_SR:
            wav = d2p._resample(wav, sr, d2p.TARGET_SR)
        yield row["sentence"], wav


def find_export(path, tmp_dir) -> Path:
    """Le ZIP de l'écran Dictée, ou son dossier décompressé (rezippé au format attendu)."""
    src = Path(path)
    if src.is_file():
        return src
    zips = sorted(src.rglob("dictee_*.zip"))
    if zips:
        return zips[0]
    metas = sorted(src.rglob("metadata.csv"))
    if metas:
        base = Path(tmp_dir) / "dictee_export"
        return Path(shutil.make_archive(str(base), "zip", root_dir=metas[0].parent))
    raise SystemExit(f"Ni dictee_*.zip ni metadata.csv sous {path}")


def write_card(asset_dir, data_root) -> Path:
    """Carte fairseq2 `mixture_parquet_asr_dataset` (répertoire FAIRSEQ2_USER_ASSET_DIR)."""
    asset_dir = Path(asset_dir)
    asset_dir.mkdir(parents=True, exist_ok=True)
    card = asset_dir / f"{CARD_NAME}.yaml"
    card.write_text(
        f"name: {CARD_NAME}\n"
        "dataset_family: mixture_parquet_asr_dataset\n"
        "dataset_config:\n"
        f"  data: {data_root}\n"
        "tokenizer_ref: omniASR_tokenizer\n",
        encoding="utf-8",
    )
    return card


def prepare(work, dictee=None, with_test=False, load_dataset=None) -> dict:
    """Construit <work>/wourri_bci (dataset partitionné + TSV) et la carte fairseq2.

    Repart toujours d'un dossier vide : une préparation précédente (autres splits,
    ancien export) ne doit pas se mélanger à celle-ci. Retourne les comptes par partition.
    """
    work = Path(work)
    dataset_dir = work / "wourri_bci"
    data_root = dataset_dir / "version=0"  # le `data:` de la carte fairseq2
    shutil.rmtree(dataset_dir, ignore_errors=True)
    lang = d2p.omni_language_code("bci")
    counts = {}

    for hf_split, split in CV_SPLITS.items():
        if split == "test" and not with_test:
            continue
        table = d2p.make_table(cv_examples(hf_split, load_dataset))
        d2p.write_partition(table, data_root, "cv_bci", split, lang)
        counts[f"cv_bci/{split}"] = table.num_rows

    if dictee:
        export = find_export(dictee, work)
        rows = d2p.read_export(export)
        counts["wourri_dictee/train"] = d2p.build_dataset(rows, data_root, "wourri_dictee", "train", "bci")

    stats = d2p.write_stats(data_root, dataset_dir / "language_distribution_0.tsv")
    card = write_card(work / "fairseq2_assets", data_root)
    return {"counts": counts, "stats": stats, "card": card}


ZENODO_DIR = "bci-datasets"  # racine de l'archive Zenodo 6705861 (data354, CC BY 4.0)


def zenodo_rows(zip_path) -> list[tuple[str, str]]:
    """[(fichier audio, transcription)] de l'archive Zenodo. Les numéros de verset en tête
    (« 28 Amun… ») ne sont pas prononcés (mesuré le 2026-10-24 sur les durées : +0,02 s à
    longueur égale) : `normalize_text` retire les mots numériques, rien d'autre à faire."""
    with zipfile.ZipFile(zip_path) as z:
        tsv = z.read(f"{ZENODO_DIR}/transcription.tsv").decode("utf-8-sig")
    return [(r["id"], r["bci"]) for r in csv.DictReader(io.StringIO(tsv), delimiter="\t") if r.get("bci")]


def zenodo_examples(zip_path, rows):
    with zipfile.ZipFile(zip_path) as z:
        for fichier, texte in rows:
            wav, _ = d2p.decode_to_16k_mono(z.read(f"{ZENODO_DIR}/wav/{fichier}"), fichier)
            yield texte, wav


def cv27_examples(rows, dossier):
    for r in rows:
        raw = (Path(dossier) / "clips" / r["path"]).read_bytes()
        wav, _ = d2p.decode_to_16k_mono(raw, r["path"])
        yield r["sentence"], wav


def extraire_cv27(source, work) -> Path:
    """Dossier `…/bci` de Common Voice 27 : l'archive .tar.gz est extraite une fois dans <work>/cv27."""
    import cv27_split as cvs  # import local : les notebooks du 1er fine-tune n'embarquent pas ce module

    source = Path(source)
    if source.is_file():
        cible = Path(work) / "cv27"
        if not any(cible.rglob("validated.tsv")):
            with tarfile.open(source) as t:
                t.extractall(cible, filter="data")
        source = cible
    return cvs.trouver(source)


def prepare_cv27(work, cv27, zenodo=None, dictee=None) -> dict:
    """2e fine-tune : Common Voice 27 réparti par `cv27_split` (train / dev / test), + Zenodo et
    dictée en train. La répartition est vérifiée contre TOUS les textes d'entraînement
    (aucune phrase du test chez Zenodo ni dans la dictée) avant d'écrire quoi que ce soit."""
    import cv27_split as cvs  # import local : les notebooks du 1er fine-tune n'embarquent pas ce module

    work = Path(work)
    dataset_dir = work / "wourri_bci"
    data_root = dataset_dir / "version=0"
    shutil.rmtree(dataset_dir, ignore_errors=True)
    lang = d2p.omni_language_code("bci")
    zen = zenodo_rows(zenodo) if zenodo else []
    dic = d2p.read_export(find_export(dictee, work)) if dictee else []
    dossier = extraire_cv27(cv27, work)
    rep, manifeste = cvs.preparer(dossier, [t for _, t in zen] + [r["transcription"] for r in dic])
    counts = {}
    for split, rows in rep.items():
        table = d2p.make_table(cv27_examples(rows, dossier))
        d2p.write_partition(table, data_root, "cv_bci", split, lang)
        counts[f"cv_bci/{split}"] = table.num_rows
    if zen:
        table = d2p.make_table(zenodo_examples(zenodo, zen))
        d2p.write_partition(table, data_root, "zenodo_bci", "train", lang)
        counts["zenodo_bci/train"] = table.num_rows
    if dic:
        counts["wourri_dictee/train"] = d2p.build_dataset(dic, data_root, "wourri_dictee", "train", "bci")
    (work / "split_cv27.json").write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
    stats = d2p.write_stats(data_root, dataset_dir / "language_distribution_0.tsv")
    card = write_card(work / "fairseq2_assets", data_root)
    return {"counts": counts, "stats": stats, "card": card, "splits": manifeste["splits"]}


def main():
    ap = argparse.ArgumentParser(description="Dataset baoulé du fine-tune Omnilingual (#474)")
    ap.add_argument("--work", required=True, help="dossier de travail (sortie)")
    ap.add_argument("--dictee", default=None, help="ZIP de la dictée ou dossier qui le contient")
    ap.add_argument("--with-test", action="store_true",
                    help="ajoute le split test (évalué, jamais entraîné)")
    ap.add_argument("--cv27", default=None, help="Common Voice 27 bci (.tar.gz ou dossier extrait) : 2e fine-tune")
    ap.add_argument("--zenodo", default=None, help="archive Zenodo 6705861 (bci-datasets.zip), avec --cv27")
    args = ap.parse_args()
    if args.cv27:
        result = prepare_cv27(args.work, args.cv27, args.zenodo, args.dictee)
        print("Répartition :", json.dumps(result["splits"], ensure_ascii=False))
    else:
        result = prepare(args.work, args.dictee, args.with_test)
    for name, n in result["counts"].items():
        print(f"{name}: {n} clips")
    for s in result["stats"]:
        print(f"{s['corpus']:15s} {s['language']}  {s['hours']:.2f} h")
    print("Carte :", result["card"])


if __name__ == "__main__":
    main()
