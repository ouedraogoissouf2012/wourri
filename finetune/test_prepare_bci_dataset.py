"""Test de la préparation du dataset baoulé (#474, ADR-0044).

Common Voice est remplacé par un faux `load_dataset` (3 clips par split, en mémoire) :
le test vérifie l'assemblage (partitions, split test optionnel, dictée, carte fairseq2,
remise à zéro), pas le téléchargement Hugging Face.
"""
import json
import zipfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
import soundfile as sf

from prepare_bci_dataset import CV_SPLITS, REV, find_export, prepare


def _wav(seconds=1.0):
    return (0.1 * np.sin(np.arange(int(16000 * seconds)) / 10)).astype("float32")


def fake_load_dataset(name, revision, split):
    assert name == "Klayt/baoule-common-voice" and revision == REV
    assert split in CV_SPLITS
    return [{"audio": {"array": _wav(), "sampling_rate": 16000}, "sentence": f"Ɔ ti kpa {split}."}
            for _ in range(3)]


def _dictee_dir(root):
    """Export de dictée tel que Kaggle le décompresse : metadata.csv + audio/."""
    d = root / "input" / "wourri-dictee" / "dictee_bci_2"
    (d / "audio").mkdir(parents=True)
    for n in ("a", "b"):
        sf.write(d / "audio" / f"{n}.wav", _wav(), 16000)
    (d / "metadata.csv").write_text(
        "file_name,transcription,language,filiere,text_fr\n"
        "audio/a.wav,Blɛ benin,bci,CACAO,?\n"
        "audio/b.wav,W’a yo kpa,bci,MAIS,?\n",
        encoding="utf-8",
    )
    return root / "input"


def _partitions(work):
    root = work / "wourri_bci" / "version=0"
    return sorted(p.parent.relative_to(root).as_posix() for p in root.rglob("part-0.parquet"))


def test_prepare_avec_test_et_dictee(tmp_path):
    work = tmp_path / "work"
    result = prepare(work, dictee=_dictee_dir(tmp_path), with_test=True, load_dataset=fake_load_dataset)

    assert result["counts"] == {
        "cv_bci/train": 3, "cv_bci/dev": 3, "cv_bci/test": 3, "wourri_dictee/train": 2,
    }
    assert _partitions(work) == [
        "corpus=cv_bci/split=dev/language=bci_Latn",
        "corpus=cv_bci/split=test/language=bci_Latn",
        "corpus=cv_bci/split=train/language=bci_Latn",
        "corpus=wourri_dictee/split=train/language=bci_Latn",
    ]
    # Cibles normalisées comme le reste de la chaîne (dictee_to_parquet.normalize_text)
    dictee = pq.read_table(str(work / "wourri_bci/version=0/corpus=wourri_dictee/split=train/language=bci_Latn/part-0.parquet"))
    assert dictee.column("text").to_pylist() == ["blɛ benin", "wʼa yo kpa"]
    # Carte fairseq2 pointant vers la racine du dataset
    card = result["card"].read_text(encoding="utf-8")
    assert "name: wourri_bci" in card and "dataset_family: mixture_parquet_asr_dataset" in card
    assert f"data: {work / 'wourri_bci' / 'version=0'}" in card
    assert (work / "wourri_bci" / "language_distribution_0.tsv").is_file()


def test_sans_with_test_pas_de_split_test(tmp_path):
    work = tmp_path / "work"
    result = prepare(work, load_dataset=fake_load_dataset)
    assert "cv_bci/test" not in result["counts"]
    assert not any("split=test" in p for p in _partitions(work))


def test_une_nouvelle_preparation_repart_de_zero(tmp_path):
    work = tmp_path / "work"
    prepare(work, dictee=_dictee_dir(tmp_path), with_test=True, load_dataset=fake_load_dataset)
    prepare(work, load_dataset=fake_load_dataset)  # sans test ni dictée
    assert _partitions(work) == [
        "corpus=cv_bci/split=dev/language=bci_Latn",
        "corpus=cv_bci/split=train/language=bci_Latn",
    ]


def test_find_export(tmp_path):
    inp = _dictee_dir(tmp_path)
    # dossier décompressé -> rezippé, metadata.csv à la racine du ZIP
    rebuilt = find_export(inp, tmp_path)
    assert "metadata.csv" in zipfile.ZipFile(rebuilt).namelist()
    # ZIP donné directement, ou trouvé dans un dossier
    z = tmp_path / "dictee_bci_2.zip"
    z.write_bytes(rebuilt.read_bytes())
    assert find_export(z, tmp_path) == z
    holder = tmp_path / "holder"
    holder.mkdir()
    (holder / "dictee_bci_2.zip").write_bytes(z.read_bytes())
    assert find_export(holder, tmp_path).name == "dictee_bci_2.zip"
    # rien d'exploitable -> arrêt clair
    empty = tmp_path / "vide"
    empty.mkdir()
    with pytest.raises(SystemExit):
        find_export(empty, tmp_path)


def test_notebook_gpu_loue_embarque_les_modules_a_jour():
    """Le notebook GPU loué recopie les deux modules (%%writefile) : copies identiques exigées."""
    here = Path(__file__).parent
    nb = json.loads((here / "colab" / "omnilingual_finetune_1b_gpu_loue.ipynb").read_text(encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for name in ("dictee_to_parquet.py", "prepare_bci_dataset.py"):
        marker = f"%%writefile {name}\n"
        embedded = [src[len(marker):] for src in cells if src.startswith(marker)]
        assert len(embedded) == 1, f"cellule {marker.strip()} introuvable"
        assert embedded[0] == (here / name).read_text(encoding="utf-8"), (
            f"Copie périmée de {name} dans le notebook : "
            "relancer `python finetune/colab/sync_smoke_test_notebook.py`."
        )
