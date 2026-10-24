"""2e fine-tune : répartition de Common Voice 27 + Zenodo + dictée (#474, ADR-0044 révision 2026-10-24).

Common Voice est simulé par quelques TSV et des WAV synthétiques (aucune donnée Mozilla dans le
dépôt : re-hébergement interdit). On vérifie la règle de répartition, l'absence de fuite du test
vers l'entraînement, l'assemblage des partitions et le chargement du test par l'évaluation.
"""
import io
import json
import tarfile
import zipfile

import numpy as np
import pyarrow.parquet as pq
import pytest
import soundfile as sf

import cv27_split as cvs
import eval_bci_cer as ev
from prepare_bci_dataset import extraire_cv27, prepare_cv27, zenodo_rows


def _wav_bytes(seconds=0.5):
    buf = io.BytesIO()
    sf.write(buf, (0.1 * np.sin(np.arange(int(16000 * seconds)) / 10)).astype("float32"), 16000, format="WAV")
    return buf.getvalue()


def _row(voix, phrase, h=0.01, path=None):
    return {"client_id": voix, "path": path or f"{voix}-{phrase}.mp3", "sentence": phrase,
            "cle": phrase.lower(), "h": h}


# Voix T1 et T2 lisent le test officiel ; A et B sont des voix d'entraînement.
VALIDES = ([_row("T1", p) for p in ("s1", "s2", "x1")] + [_row("T2", p) for p in ("s1", "s3", "x2")]
           + [_row("T3", p, h=0.5) for p in ("s1", "x3")]
           + [_row("A", p) for p in ("x1", "x2", "s2")] + [_row("B", p) for p in ("x3", "s3")])
S = {"s1", "s2", "s3"}


def test_repartir_test_dev_train():
    rep = cvs.repartir(VALIDES, S, {"T1", "T2"})
    assert {r["path"] for r in rep["test"]} == {"T1-s1.mp3", "T1-s2.mp3", "T2-s1.mp3", "T2-s3.mp3"}
    assert {r["path"] for r in rep["dev"]} == {"T1-x1.mp3", "T2-x2.mp3"}
    # T3 n'est pas au test : ses clips hors phrases du test vont à l'entraînement, jamais « s1 »
    assert {r["path"] for r in rep["train"]} == {"T3-x3.mp3", "A-x1.mp3", "A-x2.mp3", "B-x3.mp3"}


def test_choisir_voix_test_maximise_l_entrainement_sous_contraintes():
    # T3 porte 0,5 h : le garder hors du test maximise l'entraînement
    assert cvs.choisir_voix_test(VALIDES, S, {"T1", "T2", "T3"}, min_clips=3, min_voix=2, min_voix_dev=2) == {"T1", "T2"}
    with pytest.raises(SystemExit):
        cvs.choisir_voix_test(VALIDES, S, {"T1", "T2", "T3"}, min_clips=99, min_voix=2, min_voix_dev=1)


def test_verifier_refuse_toute_fuite():
    rep = cvs.repartir(VALIDES, S, {"T1", "T2"})
    cvs.verifier(rep, S, {"T1", "T2"}, autres_textes=["x9"])
    with pytest.raises(ValueError, match="test dans l'entraînement"):
        cvs.verifier(rep, S, {"T1", "T2"}, autres_textes=["S1."])  # même phrase après normalisation
    rep["train"].append(_row("T1", "x5"))
    with pytest.raises(ValueError):
        cvs.verifier(rep, S, {"T1", "T2"})


def _cv27(root):
    """Common Voice extrait : validated.tsv, clip_durations.tsv, test.tsv, clips/*.mp3 (WAV dedans)."""
    d = root / "cv-corpus-27.0" / "bci"
    (d / "clips").mkdir(parents=True)
    entete = "client_id\tpath\tsentence_id\tsentence\tsentence_domain\tup_votes\tdown_votes\n"
    lignes = [(r["client_id"], r["path"], r["sentence"]) for r in VALIDES]
    (d / "validated.tsv").write_text(entete + "".join(f"{v}\t{p}\tid\t{s}\t\t2\t0\n" for v, p, s in lignes),
                                     encoding="utf-8")
    test = [l for l in lignes if l[0] in {"T1", "T2", "T3"} and l[2] in S]
    (d / "test.tsv").write_text(entete + "".join(f"{v}\t{p}\tid\t{s}\t\t2\t0\n" for v, p, s in test), encoding="utf-8")
    (d / "clip_durations.tsv").write_text("clip\tduration[ms]\n" + "".join(f"{p}\t500\n" for _, p, _ in lignes),
                                          encoding="utf-8")
    for _, p, _ in lignes:
        (d / "clips" / p).write_bytes(_wav_bytes())
    return d


def _zenodo(root):
    z = root / "bci-datasets.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("bci-datasets/transcription.tsv", "id\tbci\nOD_1.m4a\t28 Amun bɔbɔ\nOD_2.m4a\tKlolɛ su\n")
        for n in ("OD_1.m4a", "OD_2.m4a"):
            f.writestr(f"bci-datasets/wav/{n}", _wav_bytes())
    return z


def test_prepare_cv27_partitions_manifeste_sans_voix_et_zenodo_sans_numero(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "MIN_CLIPS", 3)
    monkeypatch.setattr(cvs, "MIN_VOIX", 2)
    work = tmp_path / "work"
    res = prepare_cv27(work, _cv27(tmp_path / "cv"), zenodo=_zenodo(tmp_path))
    assert res["counts"] == {"cv_bci/train": 4, "cv_bci/dev": 2, "cv_bci/test": 4, "zenodo_bci/train": 2}
    zen = pq.read_table(str(work / "wourri_bci/version=0/corpus=zenodo_bci/split=train/language=bci_Latn/part-0.parquet"))
    assert zen.column("text").to_pylist() == ["amun bɔbɔ", "klolɛ su"]  # numéro de verset retiré
    manifeste = (work / "split_cv27.json").read_text(encoding="utf-8")
    assert "client_id" not in manifeste and "T1" not in manifeste.replace("T1-", "")
    assert json.loads(manifeste)["splits"]["test"] == {"clips": 4, "heures": 0.0, "voix": 2}


def test_zenodo_et_extraction_de_l_archive(tmp_path):
    assert zenodo_rows(_zenodo(tmp_path)) == [("OD_1.m4a", "28 Amun bɔbɔ"), ("OD_2.m4a", "Klolɛ su")]
    src = _cv27(tmp_path / "src")
    archive = tmp_path / "cv.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        t.add(src.parent.parent, arcname="cv")
    assert extraire_cv27(archive, tmp_path / "work").name == "bci"


def test_notebook_cv27_embarque_les_modules_a_jour():
    """Le notebook du 2e fine-tune recopie ses quatre modules (%%writefile) : copies identiques exigées."""
    from pathlib import Path

    here = Path(__file__).parent
    nb = json.loads((here / "colab" / "omnilingual_finetune_1b_cv27.ipynb").read_text(encoding="utf-8"))
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for name in ("dictee_to_parquet.py", "cv27_split.py", "prepare_bci_dataset.py", "eval_bci_cer.py"):
        marker = f"%%writefile {name}\n"
        embedded = [src[len(marker):] for src in cells if src.startswith(marker)]
        assert len(embedded) == 1, f"cellule {marker.strip()} introuvable"
        assert embedded[0] == (here / name).read_text(encoding="utf-8"), (
            f"Copie périmée de {name} : relancer `python finetune/colab/sync_smoke_test_notebook.py`.")


def test_evaluation_charge_le_nouveau_test_et_compare_au_depart(tmp_path):
    d = _cv27(tmp_path / "cv")
    m = tmp_path / "split_cv27.json"
    m.write_text(json.dumps({"test": [{"path": "T1-s1.mp3", "sentence": "s1"}]}), encoding="utf-8")
    refs, audios = ev.load_cv27_test(m, d)
    assert refs == ["s1"] and audios[0][1] == 16000 and len(audios[0][0]) == 8000
    r = {"temoin 1B depart": {"cer": 0.30, "wer": 0.6, "n": 1, "empty_hyps": 0, "samples": []},
         "1B fine-tune step_1200": {"cer": 0.25, "wer": 0.5, "n": 1, "empty_hyps": 0, "samples": []},
         "1B 2e fine-tune step_800": {"cer": 0.20, "wer": 0.4, "n": 1, "empty_hyps": 0, "samples": []}}
    texte = ev.report(r, "temoin 1B depart", "1B fine-tune step_1200", reference_0003=False)
    assert "TEMOIN" not in texte and "pas de reference 0003" in texte
    assert "Gain CER 1B 2e fine-tune step_800 : +10.0 pts" in texte
