"""Convertit l'export dictée (ZIP audiofolder) en dataset parquet Omnilingual — maillon ③ (#474).

Pont entre le maillon ② (export dictée, ADR-0035) et le maillon ③ (fine-tune
Omnilingual, cf. étude de faisabilité docs/benchmarks/0004 et test mécanique 0005).

Entrée : ZIP export dictée
    audio/<x>.webm ...
    metadata.csv : file_name, transcription, language, filiere, text_fr

Sortie : un dataset parquet partitionné (« hive »), seul format que lit le chargeur
`MixtureParquetStorage` de la recette de fine-tune (omnilingual-asr 0.1.0) :
    <racine>/corpus=<corpus>/split=<split>/language=<code>/part-0.parquet
        - text        : transcription normalisée (baoulé) — la CIBLE ASR
        - audio_bytes : audio FLAC 16 kHz mono, en list<int8> (schéma amont)
        - audio_size  : nombre d'échantillons du waveform décodé
    corpus / split / language vivent dans les NOMS DE DOSSIERS, pas dans le fichier :
    la recette découvre les splits et les partitions à partir de l'arborescence.
    Un fichier parquet « à plat » n'est pas lu (aucun split découvert).

Le code langue est celui d'Omnilingual (ISO 639-3 + écriture) : `bci` -> `bci_Latn`.

Usage :
    python dictee_to_parquet.py export.zip dataset_root \\
        --corpus wourri_dictee --split train --language bci \\
        --stats language_distribution_0.tsv

Décodage : soundfile (wav/flac/ogg) ; repli librosa+ffmpeg pour webm/opus/mp3
(le fine-tune tourne sur Colab/Kaggle où ffmpeg est présent). Le rééchantillonnage
utilise librosa si présent, sinon un repli linéaire (dégradé — le vrai run a librosa).

Ce module est recopié tel quel dans le notebook `colab/omnilingual_finetune_smoke_test.ipynb`
(cellule %%writefile) : un test vérifie que les deux copies restent identiques.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

TARGET_SR = 16000
ROW_GROUP_SIZE = 100  # valeur amont : limite la mémoire du streaming et permet le mélange
FILE_COLUMNS = ["text", "audio_bytes", "audio_size"]

# Apostrophe baoulé : Common Voice bci et la sortie d'Omnilingual l'écrivent U+02BC (ʼ,
# lettre modificative, conservée par la normalisation amont et présente dans le vocabulaire :
# le 1B la produit au benchmark 0003). Les variantes tapées au clavier ENTRE DEUX LETTRES
# (' ’ ‘ ‛) y sont ramenées, sinon un même son aurait plusieurs cibles ; ailleurs ce sont
# des guillemets, retirés comme la ponctuation. Un ton combinant (ɛ̀ = ɛ + U+0300, sans forme
# précomposée) compte comme lettre.
_APOSTROPHES = "'‘’‛"
_INNER_APOSTROPHE = re.compile(rf"(?<=[\ẁ-ͯ])[{_APOSTROPHES}](?=\w)")
_OTHER_APOSTROPHE = re.compile(rf"[{_APOSTROPHES}]")
# Invisibles supprimés par l'amont (shared_deletion_list) + BOM : souvent hérités d'un copier-coller.
_INVISIBLE = re.compile("[​‌‎‏‪‬﻿]")
_PUNCT = re.compile(r"[.,!?;:«»\"“”„()\[\]{}…—–/\\_]")
_DIGIT_WORD = re.compile(r"(?<!\S)\d+(?!\S)")


def normalize_text(text: str) -> str:
    """Normalise une transcription comme la préparation de données amont (text_tools) :
    NFKC, invisibles supprimés, minuscules, ponctuation retirée, mots uniquement numériques
    retirés. Les lettres baoulé (ɛ ɔ ɲ, tons, ʼ) sont conservées : elles portent le sens."""
    t = unicodedata.normalize("NFKC", text or "")
    t = _INVISIBLE.sub("", t).lower()
    t = _INNER_APOSTROPHE.sub("ʼ", t)
    t = _OTHER_APOSTROPHE.sub(" ", t)
    t = _PUNCT.sub(" ", t)
    t = _DIGIT_WORD.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def omni_language_code(code: str) -> str:
    """Code Omnilingual (`lang_ids.py`) = ISO 639-3 + écriture : 'bci' -> 'bci_Latn'.

    Les langues de l'atelier s'écrivent en latin (colonne `script` de la table
    `languages`) ; un code déjà complet ('bci_Latn') est gardé tel quel."""
    code = (code or "").strip()
    if not code:
        raise ValueError("code langue vide")
    return code if "_" in code else f"{code}_Latn"


def decode_to_16k_mono(raw: bytes, filename: str):
    """Octets audio -> (waveform float32 mono 16 kHz, n_samples)."""
    import numpy as np
    import soundfile as sf

    try:
        wav, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)  # (n, ch)
        wav = wav.mean(axis=1)  # -> mono (n,)
    except Exception:
        wav, sr = _decode_via_librosa(raw, filename)  # webm/opus/mp3 -> ffmpeg
    if sr != TARGET_SR:
        wav = _resample(np.asarray(wav, dtype="float32"), sr, TARGET_SR)
    return np.asarray(wav, dtype="float32"), int(len(wav))


def _decode_via_librosa(raw: bytes, filename: str):
    import tempfile
    import warnings

    import librosa

    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        # webm : soundfile échoue toujours, librosa passe par audioread + ffmpeg. Ses deux
        # avertissements (« PySoundFile failed », dépréciation d'audioread) sortiraient une fois
        # par clip et noieraient la sortie du notebook (433 clips = 433 paires).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            warnings.simplefilter("ignore", FutureWarning)
            wav, sr = librosa.load(path, sr=None, mono=True)  # float32 mono
    finally:
        Path(path).unlink(missing_ok=True)
    return wav, sr


def _resample(wav, sr: int, target: int):
    import numpy as np

    try:
        import librosa

        return librosa.resample(wav, orig_sr=sr, target_sr=target)
    except Exception:
        # repli linéaire (le vrai run a librosa ; ce repli garde le script utilisable en test)
        n = int(round(len(wav) * target / sr))
        if n <= 0:
            return wav
        return np.interp(
            np.linspace(0, len(wav) - 1, n), np.arange(len(wav)), wav
        ).astype("float32")


def encode_flac(wav) -> bytes:
    """Waveform float32 mono 16 kHz -> octets FLAC."""
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, wav, TARGET_SR, format="FLAC")
    return buf.getvalue()


def read_export(zip_path) -> list[dict]:
    """Lit le ZIP export dictée -> [{file_name, transcription, language, filiere, text_fr, raw}]."""
    rows: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        metas = sorted(n for n in names if PurePosixPath(n).name == "metadata.csv")
        if not metas:
            raise SystemExit("metadata.csv introuvable dans le ZIP")
        meta_name = "metadata.csv" if "metadata.csv" in names else metas[0]
        meta = zf.read(meta_name).decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(meta)):
            fn = (r.get("file_name") or "").strip()
            if not fn:
                continue
            if fn not in names:
                # tolère un préfixe de chemin différent, jamais un autre fichier :
                # même nom exact (pas « 11.webm » pour « 1.webm ») et un seul candidat
                base = PurePosixPath(fn).name
                cands = [n for n in names if PurePosixPath(n).name == base]
                if len(cands) != 1:
                    why = "absent du ZIP" if not cands else f"ambigu ({len(cands)} fichiers)"
                    print(f"  [SKIP] audio {why} : {fn}", file=sys.stderr)
                    continue
                fn = cands[0]
            rows.append(
                {
                    "file_name": fn,
                    "transcription": (r.get("transcription") or "").strip(),
                    "language": (r.get("language") or "").strip(),
                    "filiere": (r.get("filiere") or "").strip(),
                    "text_fr": (r.get("text_fr") or "").strip(),
                    "raw": zf.read(fn),
                }
            )
    return rows


def make_table(examples):
    """[(transcription, waveform float32 mono 16 kHz)] -> table parquet (colonnes FILE_COLUMNS).

    Ignore les paires sans texte après normalisation ou sans audio : une paire
    audio↔texte complète est requise pour l'apprentissage."""
    import numpy as np
    import pyarrow as pa

    texts, audios, sizes = [], [], []
    for text, wav in examples:
        norm = normalize_text(text)
        if not norm or len(wav) == 0:
            continue
        texts.append(norm)
        audios.append(np.frombuffer(encode_flac(wav), dtype=np.int8))
        sizes.append(int(len(wav)))
    return pa.table(
        {
            "text": pa.array(texts, type=pa.string()),
            "audio_bytes": pa.array(audios, type=pa.list_(pa.int8())),
            "audio_size": pa.array(sizes, type=pa.int64()),
        }
    )


def write_partition(table, root, corpus: str, split: str, language: str) -> Path:
    """Écrit la table dans <root>/corpus=…/split=…/language=…/part-0.parquet.

    Remplace les parquet déjà présents dans CETTE partition : un export dictée est
    toujours complet, le reconvertir doit remplacer l'ancien, pas s'y ajouter."""
    import pyarrow.parquet as pq

    for key, value in (("corpus", corpus), ("split", split), ("language", language)):
        if not value or "/" in value or "=" in value:
            raise ValueError(f"{key} invalide pour un nom de partition : {value!r}")
    if "_" in split:
        # la recette lit un split « <split>_<corpus> » comme un filtre de corpus
        raise ValueError(f"split sans '_' attendu (reçu {split!r})")
    if table.num_rows == 0:
        # une partition vide fait échouer la recette au démarrage (lecture de son 1er exemple)
        raise ValueError(f"aucune paire audio↔texte exploitable pour {corpus}/{split}")
    part_dir = Path(root) / f"corpus={corpus}" / f"split={split}" / f"language={language}"
    part_dir.mkdir(parents=True, exist_ok=True)
    for old in part_dir.glob("*.parquet"):
        old.unlink()
    out = part_dir / "part-0.parquet"
    pq.write_table(table, out, row_group_size=ROW_GROUP_SIZE)
    return out


def write_stats(root, out_tsv) -> list[dict]:
    """Écrit le TSV `corpus / language / hours` attendu par `dataset_summary_path`
    (pondération des partitions à l'entraînement). Comme l'outil amont, les heures
    sont cumulées sur tous les splits."""
    import pyarrow.dataset as ds

    table = ds.dataset(str(root), format="parquet", partitioning="hive").to_table(
        columns=["corpus", "language", "audio_size"]
    )
    samples: dict[tuple[str, str], int] = {}
    for corpus, language, size in zip(
        table.column("corpus").to_pylist(),
        table.column("language").to_pylist(),
        table.column("audio_size").to_pylist(),
    ):
        key = (str(corpus), str(language))
        samples[key] = samples.get(key, 0) + int(size)
    stats = [
        {"corpus": c, "language": lang, "hours": n / TARGET_SR / 3600}
        for (c, lang), n in sorted(samples.items())
    ]
    lines = ["corpus\tlanguage\thours"]
    lines += [f"{s['corpus']}\t{s['language']}\t{s['hours']:.6f}" for s in stats]
    Path(out_tsv).parent.mkdir(parents=True, exist_ok=True)
    Path(out_tsv).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats


def build_dataset(rows, root, corpus: str, split: str, language: str) -> int:
    """Lignes d'export dictée -> partition parquet. Retourne le nombre de clips écrits."""

    def examples():
        for r in rows:
            if r.get("transcription"):
                wav, _ = decode_to_16k_mono(r["raw"], r["file_name"])
                yield r["transcription"], wav

    table = make_table(examples())
    write_partition(table, root, corpus, split, omni_language_code(language))
    return table.num_rows


def main():
    ap = argparse.ArgumentParser(
        description="Export dictée (ZIP audiofolder) -> dataset parquet Omnilingual (#474)"
    )
    ap.add_argument("zip_path", help="ZIP export dictée (audio/ + metadata.csv)")
    ap.add_argument("out_root", help="racine du dataset (le `data:` de la carte fairseq2)")
    ap.add_argument("--corpus", default="wourri_dictee")
    ap.add_argument("--split", default="train", choices=["train", "dev", "test"])
    ap.add_argument("--language", default=None, help="code langue (ex. bci) ; défaut : celui du CSV")
    ap.add_argument("--stats", default=None, help="écrit aussi le TSV corpus/language/hours")
    args = ap.parse_args()

    rows = read_export(args.zip_path)
    language = args.language
    if not language:
        found = {r["language"] for r in rows if r.get("language")}
        if len(found) != 1:
            raise SystemExit(f"--language requis : langues trouvées dans le CSV = {sorted(found)}")
        language = found.pop()
    n = build_dataset(rows, args.out_root, args.corpus, args.split, language)
    print(f"OK : {n} clips -> {args.out_root} (corpus={args.corpus}, split={args.split}, "
          f"language={omni_language_code(language)})")
    if args.stats:
        write_stats(args.out_root, args.stats)
        print(f"Stats -> {args.stats}")


if __name__ == "__main__":
    main()
