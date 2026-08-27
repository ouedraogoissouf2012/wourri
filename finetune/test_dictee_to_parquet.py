"""Test du pont export dictée -> parquet Omnilingual (#474).

Utilise un WAV synthétique (lu par soundfile, pas de ffmpeg requis) pour exercer
tout le pipeline : read_export -> build_parquet -> relecture parquet. Le décodage
webm et le rééchantillonnage librosa haute qualité ne sont exercés que dans le
notebook de fine-tune réel (Colab/Kaggle avec ffmpeg + librosa).
"""
import io
import zipfile

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

from dictee_to_parquet import REQUIRED_COLUMNS, build_parquet, read_export


def _wav_bytes(sr, seconds=1.0, freq=440.0):
    t = np.arange(int(sr * seconds))
    wav = (0.1 * np.sin(2 * np.pi * freq * t / sr)).astype("float32")
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV")
    return buf.getvalue()


def _make_export(path, rows):
    """rows = [(file_name, transcription, language, filiere, text_fr, wav_sr)]."""
    with zipfile.ZipFile(path, "w") as zf:
        header = "file_name,transcription,language,filiere,text_fr\r\n"
        lines = [header]
        for fn, transc, lang, fil, fr, sr in rows:
            zf.writestr(fn, _wav_bytes(sr))
            lines.append(f"{fn},{transc},{lang},{fil},{fr}\r\n")
        zf.writestr("metadata.csv", "".join(lines))


def test_conversion_zip_vers_parquet(tmp_path):
    zpath = tmp_path / "export.zip"
    # 1 clip à 8 kHz (pour tester le rééchantillonnage vers 16 kHz), baoulé réel
    _make_export(
        zpath,
        [("audio/clip1.wav", "Blɛ benin nun yɛ ɔ fata", "bci", "CACAO", "Quand planter ?", 8000)],
    )

    rows = read_export(zpath)
    assert len(rows) == 1
    assert rows[0]["transcription"] == "Blɛ benin nun yɛ ɔ fata"  # UTF-8 baoulé intact
    assert rows[0]["language"] == "bci"

    out = tmp_path / "out.parquet"
    n = build_parquet(rows, str(out), corpus="wourri_dictee", split="train", language_override="bci")
    assert n == 1

    table = pq.read_table(str(out))
    assert table.column_names == REQUIRED_COLUMNS  # schéma Omnilingual exact
    d = table.to_pydict()
    assert d["text"][0] == "Blɛ benin nun yɛ ɔ fata"  # transcription = cible ASR
    assert d["language"][0] == "bci"
    assert d["corpus"][0] == "wourri_dictee"
    assert d["split"][0] == "train"
    # rééchantillonné 8k -> 16k : ~16000 échantillons pour 1 s
    assert 15000 < d["audio_size"][0] < 17000
    # audio_bytes est bien du FLAC 16 kHz relisible, cohérent avec audio_size
    w2, sr2 = sf.read(io.BytesIO(d["audio_bytes"][0]))
    assert sr2 == 16000
    assert abs(len(w2) - d["audio_size"][0]) <= 1


def test_ligne_sans_transcription_ignoree(tmp_path):
    zpath = tmp_path / "export.zip"
    _make_export(
        zpath,
        [
            ("audio/ok.wav", "Wafa sɛ amun gua kaba", "bci", "MAIS", "Comment semer ?", 16000),
            ("audio/vide.wav", "", "bci", "RIZ", "Sans transcription ?", 16000),
        ],
    )
    rows = read_export(zpath)
    assert len(rows) == 2  # les 2 lignes sont lues
    out = tmp_path / "out.parquet"
    n = build_parquet(rows, str(out), corpus="wourri_dictee", split="train")
    assert n == 1  # mais seule celle avec transcription part dans le dataset
    d = pq.read_table(str(out)).to_pydict()
    assert d["text"] == ["Wafa sɛ amun gua kaba"]


def test_audio_absent_du_zip_est_saute(tmp_path):
    # metadata référence un fichier qui n'est pas dans le ZIP -> sauté, pas de crash
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("audio/present.wav", _wav_bytes(16000))
        zf.writestr(
            "metadata.csv",
            "file_name,transcription,language,filiere,text_fr\r\n"
            "audio/present.wav,phrase A,bci,CACAO,?\r\n"
            "audio/manquant.wav,phrase B,bci,CACAO,?\r\n",
        )
    rows = read_export(zpath)
    assert len(rows) == 1 and rows[0]["transcription"] == "phrase A"
