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
import shutil
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


def main():
    ap = argparse.ArgumentParser(description="Dataset baoulé du fine-tune Omnilingual (#474)")
    ap.add_argument("--work", required=True, help="dossier de travail (sortie)")
    ap.add_argument("--dictee", default=None, help="ZIP de la dictée ou dossier qui le contient")
    ap.add_argument("--with-test", action="store_true",
                    help="ajoute le split test (évalué, jamais entraîné)")
    args = ap.parse_args()
    result = prepare(args.work, args.dictee, args.with_test)
    for name, n in result["counts"].items():
        print(f"{name}: {n} clips")
    for s in result["stats"]:
        print(f"{s['corpus']:15s} {s['language']}  {s['hours']:.2f} h")
    print("Carte :", result["card"])


if __name__ == "__main__":
    main()
