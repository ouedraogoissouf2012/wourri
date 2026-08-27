"""Convertit l'export dictée (ZIP audiofolder) en parquet Omnilingual — maillon ③ (#474).

Pont entre le maillon ② (export dictée, ADR-0035) et le maillon ③ (fine-tune
Omnilingual, cf. étude de faisabilité docs/benchmarks/0004).

Entrée : ZIP export dictée
    audio/<x>.webm ...
    metadata.csv : file_name, transcription, language, filiere, text_fr

Sortie : UN fichier parquet au format attendu par la recette de fine-tune
Omnilingual (workflows/dataprep) :
    - text        : transcription (baoulé) — la CIBLE ASR
    - audio_bytes : audio compressé FLAC, 16 kHz mono (binaire)
    - audio_size  : nombre d'échantillons du waveform décodé
    - corpus / split / language : métadonnées de partition

Usage :
    python dictee_to_parquet.py export.zip out.parquet \\
        --corpus wourri_dictee --split train --language bci

Décodage : soundfile (wav/flac/ogg) ; repli librosa+ffmpeg pour webm/opus/mp3
(le fine-tune tourne sur Colab/Kaggle où ffmpeg est présent). Le rééchantillonnage
utilise librosa si présent, sinon un repli linéaire (dégradé — le vrai run a librosa).
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

TARGET_SR = 16000
REQUIRED_COLUMNS = ["text", "audio_bytes", "audio_size", "corpus", "split", "language"]


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

    import librosa

    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
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
        meta_name = (
            "metadata.csv"
            if "metadata.csv" in names
            else next((n for n in names if n.endswith("metadata.csv")), None)
        )
        if not meta_name:
            raise SystemExit("metadata.csv introuvable dans le ZIP")
        meta = zf.read(meta_name).decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(meta)):
            fn = (r.get("file_name") or "").strip()
            if not fn:
                continue
            if fn not in names:  # tolère un préfixe de chemin différent
                cand = next((n for n in names if n.endswith(fn.split("/")[-1])), None)
                if not cand:
                    print(f"  [SKIP] audio absent du ZIP : {fn}", file=sys.stderr)
                    continue
                fn = cand
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


def build_parquet(rows, out_path, corpus, split, language_override=None) -> int:
    """Construit le parquet Omnilingual. Ignore les lignes sans transcription
    (une paire audio↔texte est requise). Retourne le nombre de clips écrits."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    cols: dict[str, list] = {c: [] for c in REQUIRED_COLUMNS}
    for r in rows:
        if not r.get("transcription"):
            continue
        wav, n = decode_to_16k_mono(r["raw"], r["file_name"])
        cols["text"].append(r["transcription"])
        cols["audio_bytes"].append(encode_flac(wav))
        cols["audio_size"].append(n)
        cols["corpus"].append(corpus)
        cols["split"].append(split)
        cols["language"].append(language_override or r.get("language") or "bci")

    table = pa.table(
        {
            "text": pa.array(cols["text"], type=pa.string()),
            "audio_bytes": pa.array(cols["audio_bytes"], type=pa.binary()),
            "audio_size": pa.array(cols["audio_size"], type=pa.int64()),
            "corpus": pa.array(cols["corpus"], type=pa.string()),
            "split": pa.array(cols["split"], type=pa.string()),
            "language": pa.array(cols["language"], type=pa.string()),
        }
    )
    pq.write_table(table, out_path)
    return len(cols["text"])


def main():
    ap = argparse.ArgumentParser(
        description="Export dictée (ZIP audiofolder) -> parquet Omnilingual (#474)"
    )
    ap.add_argument("zip_path", help="ZIP export dictée (audio/ + metadata.csv)")
    ap.add_argument("out_path", help="fichier .parquet de sortie")
    ap.add_argument("--corpus", default="wourri_dictee")
    ap.add_argument("--split", default="train", choices=["train", "dev", "test"])
    ap.add_argument("--language", default=None, help="force le code langue (ex. bci)")
    args = ap.parse_args()

    rows = read_export(args.zip_path)
    n = build_parquet(rows, args.out_path, args.corpus, args.split, args.language)
    print(f"OK : {n} clips -> {args.out_path} (corpus={args.corpus}, split={args.split})")


if __name__ == "__main__":
    main()
