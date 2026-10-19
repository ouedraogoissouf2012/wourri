"""Test de l'évaluation CER baoulé à l'identique du benchmark 0003 (#474, BAO-2).

Le modèle et Common Voice sont remplacés par des faux (pas de GPU, pas de réseau) : le test
vérifie le protocole (même normalisation que le benchmark 0003, transcriptions vides comptées,
carte fairseq2 du checkpoint, verdict du témoin), pas la qualité du modèle.
"""
import json
from pathlib import Path

import numpy as np
import pytest

import eval_bci_cer as ev
from prepare_bci_dataset import REV

HERE = Path(__file__).parent


def _cells(notebook):
    nb = json.loads((HERE / "colab" / notebook).read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_normalisation_et_score_copies_exactes_du_benchmark_0003():
    """Même texte que la cellule 3 du notebook du benchmark 0003, de la normalisation au score."""
    cell = next(c for c in _cells("asr_baoule_benchmark.ipynb") if "def normalize" in c)
    block = cell[cell.index("# --- normalisation TOLERANTE"):cell.index("# Garde-fou")].rstrip()
    assert block in (HERE / "eval_bci_cer.py").read_text(encoding="utf-8")


def test_normalisation_conserve_les_caracteres_baoule():
    assert ev.normalize("  Blaʼm  be NIAN, fieʼn nun…  ") == "blaʼm be nian fieʼn nun"
    assert ev.normalize("Ɔ ti kpa!") == "ɔ ti kpa"
    assert ev.normalize(None) == ""


def test_score_compte_les_transcriptions_vides_et_ignore_les_references_vides():
    r = ev.score(["ɔ ti kpa", "", "blɛ"], ["ɔ ti kpa", "n'importe quoi", ""])
    assert r["n"] == 2  # la référence vide est ignorée, comme au benchmark 0003
    # « blɛ » non transcrit : 3 caractères manquants sur 8 + 3
    assert r["cer"] == pytest.approx(3 / 11)
    assert r["wer"] == pytest.approx(1 / 4)


def _checkpoint(root, step):
    shard = root / "snapshot" / step / "model" / "pp_00" / "tp_00" / "sdp_00.pt"
    shard.parent.mkdir(parents=True)
    shard.write_bytes(b"")
    return shard.parent.parent.parent


def test_find_checkpoint_et_carte_fairseq2(tmp_path):
    model_dir = _checkpoint(tmp_path, "step_1200")
    _checkpoint(tmp_path / "autre", "step_200")
    assert ev.find_checkpoint(tmp_path, "step_1200") == model_dir.resolve()
    with pytest.raises(SystemExit):
        ev.find_checkpoint(tmp_path, "step_1400")

    name = ev.write_card(tmp_path / "assets", "step_1200", model_dir)
    assert name == "wourri_bci_ctc_1b_step_1200"
    card = (tmp_path / "assets" / f"{name}.yaml").read_text(encoding="utf-8").splitlines()
    assert card == [f"name: {name}", "base: omniASR_CTC_1B", f"checkpoint: {model_dir.resolve().as_posix()}"]
    with pytest.raises(SystemExit):  # dossier sans pp_00/ : pas un checkpoint fairseq2
        ev.write_card(tmp_path / "assets", "step_1200", tmp_path)


def fake_load_dataset(name, revision, split):
    assert name == "Klayt/baoule-common-voice" and revision == REV and split == "test"
    wav = (0.1 * np.sin(np.arange(16000) / 10)).astype("float32")
    return [{"audio": {"array": wav, "sampling_rate": 16000}, "sentence": s}
            for s in ("Ɔ ti kpa.", "Blɛ benin.", "W'a yo kpa.")]


class FakePipeline:
    OUTPUTS = {"omniASR_CTC_1B": ["ɔ ti pa", "", "wa yo kpa"],
               "wourri_bci_ctc_1b_step_1200": ["ɔ ti kpa", "blɛ benin", "w'a yo kpa"]}

    def __init__(self, card):
        self.card = card

    def transcribe(self, paths, lang, batch_size):
        assert batch_size == 1 and set(lang) == {"bci_Latn"} and len(paths) == 3
        assert all(Path(p).is_file() for p in paths)
        return self.OUTPUTS[self.card]


def test_evaluate_memes_clips_pour_les_deux_modeles(tmp_path):
    out = tmp_path / "res.json"
    models = [("temoin", "omniASR_CTC_1B"), ("ft", "wourri_bci_ctc_1b_step_1200")]
    results = ev.evaluate(models, out, load_dataset=fake_load_dataset, make_pipeline=FakePipeline)

    assert json.loads(out.read_text(encoding="utf-8")) == results
    assert results["temoin"]["n"] == results["ft"]["n"] == 3
    assert results["temoin"]["empty_hyps"] == 1 and results["ft"]["empty_hyps"] == 0
    assert results["ft"]["cer"] == 0.0 and results["temoin"]["cer"] > 0
    assert results["ft"]["samples"][1] == {"ref": "Blɛ benin.", "hyp": "blɛ benin"}
    text = ev.report(results, "temoin", "ft")
    assert "TEMOIN ECART" in text  # 3 clips au lieu de 290 : jamais recevable
    assert "Gain CER" in text


@pytest.mark.parametrize("cer, n, ok", [
    (0.221, 290, True), (0.2255, 290, True), (0.2265, 290, False), (0.221, 289, False),
])
def test_verdict_du_temoin(cer, n, ok):
    assert ev.control_ok(cer, n) is ok


def test_notebook_eval_embarque_les_modules_a_jour():
    """Le notebook d'évaluation recopie les modules (%%writefile) : copies identiques exigées."""
    cells = _cells("omnilingual_eval_finetune.ipynb")
    for name in ("dictee_to_parquet.py", "prepare_bci_dataset.py", "eval_bci_cer.py"):
        marker = f"%%writefile {name}\n"
        embedded = [src[len(marker):] for src in cells if src.startswith(marker)]
        assert len(embedded) == 1, f"cellule {marker.strip()} introuvable"
        assert embedded[0] == (HERE / name).read_text(encoding="utf-8"), (
            f"Copie périmée de {name} dans le notebook : "
            "relancer `python finetune/colab/sync_smoke_test_notebook.py`."
        )
