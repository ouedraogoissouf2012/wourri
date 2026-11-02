"""Serveur voix baoulé sur processeur (ADR-0048) : démarrage du conteneur et outils de mesure,
sans modèle ni processeur particulier (carte écrite dans un dossier temporaire, horloge factice)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent / "voix"))
import demarrer
import mesure_cpu_bci as mesure


def _checkpoint(racine, step="step_3000"):
    pp = racine / step / "model" / "pp_00" / "tp_00"
    pp.mkdir(parents=True)
    (pp / "sdp_00.pt").write_bytes(b"")
    return racine


def test_demarrage_ecrit_la_carte_et_ignore_un_modele_de_langue_absent(tmp_path):
    env = {"BCI_VOIX_CLE": "cle", "BCI_VOIX_MODELE": str(_checkpoint(tmp_path / "modele")),
           "FAIRSEQ2_USER_ASSET_DIR": str(tmp_path / "cartes"), "BCI_VOIX_LM": str(tmp_path / "absent.pkl")}
    extra = demarrer.preparer(env)
    assert extra == {"BCI_VOIX_CARTE": "wourri_bci_voix", "BCI_VOIX_LM": ""}
    carte = (tmp_path / "cartes" / "wourri_bci_voix.yaml").read_text(encoding="utf-8")
    assert "base: omniASR_CTC_1B" in carte and "step_3000/model" in carte

    (tmp_path / "lm.pkl").write_bytes(b"x")
    assert "BCI_VOIX_LM" not in demarrer.preparer({**env, "BCI_VOIX_LM": str(tmp_path / "lm.pkl")})


def test_demarrage_refuse_sans_cle(tmp_path):
    with pytest.raises(SystemExit, match="BCI_VOIX_CLE"):
        demarrer.preparer({"BCI_VOIX_MODELE": str(tmp_path), "FAIRSEQ2_USER_ASSET_DIR": str(tmp_path)})


def test_vocaux_synthetiques_aux_durees_demandees():
    audios = [(np.ones(16000 * 3, dtype=np.float32), 16000) for _ in range(4)]  # 12 s au total
    v = mesure.vocaux_synthetiques(audios, durees=(5, 10), sr=16000)
    assert {d: len(s) for d, s in v.items()} == {5: 80000, 10: 160000}
    with pytest.raises(SystemExit):
        mesure.vocaux_synthetiques(audios, durees=(30,), sr=16000)


def test_audios_du_dossier_pour_la_vitesse_seule(tmp_path):
    import soundfile as sf

    for nom, n in (("b.wav", 16000), ("a.wav", 8000), ("c.wav", 4000)):
        sf.write(tmp_path / nom, np.zeros(n, dtype=np.float32), 16000)
    (tmp_path / "notes.txt").write_text("pas un audio", encoding="utf-8")
    audios = mesure.audios_du_dossier(tmp_path, limite=2)
    assert [(len(s), sr) for s, sr in audios] == [(8000, 16000), (16000, 16000)]  # a puis b


def test_chronometrer_rend_la_mediane_des_appels():
    instants = iter([0, 2, 10, 13, 20, 21])  # durées 2, 3, 1 -> médiane 2
    appels = []
    assert mesure.chronometrer(appels.append, ["v.wav"], repetitions=3, horloge=lambda: next(instants)) == 2
    assert appels == ["v.wav"] * 3
