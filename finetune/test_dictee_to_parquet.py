"""Test du pont export dictée -> dataset parquet Omnilingual (#474).

Utilise un WAV synthétique (lu par soundfile, pas de ffmpeg requis) pour exercer
tout le pipeline : read_export -> build_dataset -> relecture parquet. Le décodage
webm et le rééchantillonnage librosa haute qualité ne sont exercés que dans le
notebook de fine-tune réel (Colab/Kaggle avec ffmpeg + librosa).

Le test de contrat reproduit, avec pyarrow seul, la découverte des splits et des
partitions de `MixtureParquetStorage` (omnilingual-asr 0.1.0,
src/omnilingual_asr/datasets/storage/mixture_parquet_storage.py) : fairseq2 ne
s'installe pas sous Windows, mais c'est cette lecture qui décide si la recette
trouve nos données.
"""
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import soundfile as sf
from pyarrow.dataset import get_partition_keys

import dictee_to_parquet
from dictee_to_parquet import (
    FILE_COLUMNS,
    build_dataset,
    make_table,
    normalize_text,
    omni_language_code,
    read_export,
    write_partition,
    write_stats,
)

PARTITION = ("corpus=wourri_dictee", "split=train", "language=bci_Latn")


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


def _sine(seconds=1.0):
    return (0.1 * np.sin(np.arange(int(16000 * seconds)) / 10)).astype("float32")


def test_conversion_zip_vers_dataset(tmp_path):
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

    root = tmp_path / "dataset"
    n = build_dataset(rows, root, corpus="wourri_dictee", split="train", language="bci")
    assert n == 1

    part = root.joinpath(*PARTITION, "part-0.parquet")
    assert part.is_file()
    table = pq.read_table(str(part))
    assert table.column_names == FILE_COLUMNS  # corpus/split/language = dossiers, pas colonnes
    assert table.schema.field("audio_bytes").type == pa.list_(pa.int8())  # schéma amont
    d = table.to_pydict()
    assert d["text"][0] == "blɛ benin nun yɛ ɔ fata"  # cible normalisée, lettres baoulé gardées
    # rééchantillonné 8k -> 16k : ~16000 échantillons pour 1 s
    assert 15000 < d["audio_size"][0] < 17000
    # audio_bytes est bien du FLAC 16 kHz relisible, cohérent avec audio_size
    raw = np.asarray(d["audio_bytes"][0], dtype=np.int8).tobytes()
    w2, sr2 = sf.read(io.BytesIO(raw))
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
    root = tmp_path / "dataset"
    n = build_dataset(rows, root, corpus="wourri_dictee", split="train", language="bci")
    assert n == 1  # mais seule celle avec transcription part dans le dataset
    d = pq.read_table(str(root.joinpath(*PARTITION, "part-0.parquet"))).to_pydict()
    assert d["text"] == ["wafa sɛ amun gua kaba"]


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


def test_audio_retrouve_par_nom_exact_jamais_un_autre_fichier(tmp_path):
    # « 1.wav » ne doit pas être apparié à « audio/11.wav » ; un nom ambigu est sauté
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("audio/11.wav", _wav_bytes(16000, seconds=2.0))
        zf.writestr("audio/1.wav", _wav_bytes(16000, seconds=1.0))
        zf.writestr("a/x.wav", _wav_bytes(16000))
        zf.writestr("b/x.wav", _wav_bytes(16000))
        zf.writestr(
            "metadata.csv",
            "file_name,transcription,language,filiere,text_fr\r\n"
            "1.wav,phrase un,bci,CACAO,?\r\n"
            "x.wav,phrase ambigue,bci,CACAO,?\r\n",
        )
    rows = read_export(zpath)
    assert [(r["file_name"], r["transcription"]) for r in rows] == [("audio/1.wav", "phrase un")]


@pytest.mark.parametrize(
    "brut, attendu",
    [
        # minuscules (Ɛ -> ɛ, Ɔ -> ɔ) + ponctuation retirée
        ("Ɛ kwla yo ninnge mun likawlɛ naan sran kwlaa wʼa yo kpa.", "ɛ kwla yo ninnge mun likawlɛ naan sran kwlaa wʼa yo kpa"),
        ("« Ɔ ti kpa ! »", "ɔ ti kpa"),
        # apostrophe baoulé U+02BC conservée telle quelle
        ("Blaʼm be nian fieʼn nun", "blaʼm be nian fieʼn nun"),
        # variantes clavier entre deux lettres -> U+02BC ; en bord de mot = guillemet retiré
        ("w’a yo kpa", "wʼa yo kpa"),
        ("w'a yo kpa", "wʼa yo kpa"),
        ("'kpa' sran", "kpa sran"),
        # guillemet fermant suivi d'une ponctuation : retiré, pas transformé en ʼ collé au mot
        ("n’ɔ ‘bɛ’, ‘mɔ’.", "nʼɔ bɛ mɔ"),
        # ton combinant (ɛ + U+0300, sans forme précomposée) puis apostrophe : reste une lettre
        ("ɛ̀’a", "ɛ̀ʼa"),
        # invisibles d'un copier-coller supprimés ; « _ » traité comme ponctuation
        ("a​b﻿ kpa_sran", "ab kpa sran"),
        # mot uniquement numérique retiré (le locuteur l'a prononcé en baoulé)
        ("Be su 2 hectare", "be su hectare"),
        ("   ", ""),
    ],
)
def test_normalize_text(brut, attendu):
    assert normalize_text(brut) == attendu


def test_omni_language_code():
    assert omni_language_code("bci") == "bci_Latn"
    assert omni_language_code("dyu") == "dyu_Latn"
    assert omni_language_code("bci_Latn") == "bci_Latn"  # déjà complet : gardé
    with pytest.raises(ValueError):
        omni_language_code("")


def test_write_partition_refuse_split_avec_underscore(tmp_path):
    # la recette lirait « dev_extra » comme split=dev + corpus=extra
    table = make_table([("ɔ ti kpa", _sine())])
    with pytest.raises(ValueError):
        write_partition(table, tmp_path, "cv_bci", "dev_extra", "bci_Latn")


def test_write_partition_refuse_une_partition_vide(tmp_path):
    # tout ignoré (texte vide après normalisation) -> erreur claire, pas un parquet vide
    # qui ferait échouer la recette au démarrage
    with pytest.raises(ValueError):
        write_partition(make_table([("…", _sine())]), tmp_path, "c", "train", "bci_Latn")
    assert not any(tmp_path.rglob("*.parquet"))


def test_write_partition_remplace_l_ancien_contenu(tmp_path):
    write_partition(make_table([("a", _sine()), ("b", _sine())]), tmp_path, "c", "train", "bci_Latn")
    part = write_partition(make_table([("c", _sine())]), tmp_path, "c", "train", "bci_Latn")
    assert sorted(p.name for p in part.parent.iterdir()) == ["part-0.parquet"]
    assert pq.read_table(str(part)).num_rows == 1  # export complet = remplacement


def test_contrat_lecture_recette_amont(tmp_path):
    """Reproduit MixtureParquetStorage.load_and_discover_splits + get_all_mixture_partitions."""
    root = tmp_path / "version=0"
    write_partition(make_table([("ɔ ti kpa", _sine())]), root, "cv_bci", "train", "bci_Latn")
    write_partition(make_table([("blɛ", _sine())]), root, "cv_bci", "dev", "bci_Latn")
    write_partition(make_table([("wafa", _sine())]), root, "wourri_dictee", "train", "bci_Latn")

    dataset = pq.ParquetDataset(str(root))
    names = dataset.partitioning.schema.names
    assert {"corpus", "split", "language"} <= set(names)
    splits = set(dataset.partitioning.dictionaries[names.index("split")].to_pylist())
    assert splits == {"train", "dev"}  # valid_split « dev » de la recette trouvé

    partitions = []
    for fragment in dataset._dataset.get_fragments(filter=dataset._filter_expression):
        keys = get_partition_keys(fragment.partition_expression) or {}
        partitions.append((keys["split"], keys["corpus"], keys["language"]))
    assert sorted(partitions) == [
        ("dev", "cv_bci", "bci_Latn"),
        ("train", "cv_bci", "bci_Latn"),
        ("train", "wourri_dictee", "bci_Latn"),
    ]


def test_write_stats(tmp_path):
    root = tmp_path / "version=0"
    write_partition(make_table([("a", _sine(2.0)), ("b", _sine(1.0))]), root, "cv_bci", "train", "bci_Latn")
    write_partition(make_table([("c", _sine(1.0))]), root, "cv_bci", "dev", "bci_Latn")
    tsv = tmp_path / "language_distribution_0.tsv"
    stats = write_stats(root, tsv)
    lines = tsv.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "corpus\tlanguage\thours"  # colonnes lues par get_partition_weights_from_betas
    assert len(stats) == 1  # une ligne par (corpus, langue), tous splits cumulés
    assert stats[0]["corpus"] == "cv_bci" and stats[0]["language"] == "bci_Latn"
    assert stats[0]["hours"] == pytest.approx(4.0 / 3600)


def test_notebook_embarque_le_module_a_jour():
    """Le notebook Kaggle recopie ce module (%%writefile) : les deux copies doivent rester identiques."""
    nb_path = Path(__file__).parent / "colab" / "omnilingual_finetune_smoke_test.ipynb"
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    marker = "%%writefile dictee_to_parquet.py\n"
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    embedded = [src[len(marker):] for src in cells if src.startswith(marker)]
    assert len(embedded) == 1, "cellule %%writefile dictee_to_parquet.py introuvable"
    module_src = Path(dictee_to_parquet.__file__).read_text(encoding="utf-8")
    assert embedded[0] == module_src, (
        "Le notebook embarque une copie périmée de dictee_to_parquet.py : "
        "relancer `python finetune/colab/sync_smoke_test_notebook.py`."
    )
