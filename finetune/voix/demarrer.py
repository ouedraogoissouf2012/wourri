"""Démarrage du serveur voix baoulé dans son conteneur (ADR-0048).

Écrit la carte fairseq2 du modèle monté (`BCI_VOIX_MODELE`, étape `BCI_VOIX_STEP`), puis
lance uvicorn sur serveur_voix_bci:app. Le modèle de langue n'est branché que si le fichier
`BCI_VOIX_LM` existe : sinon décodage glouton (mesuré dans la fiche 0007).
"""
from __future__ import annotations

import os
import sys

import eval_bci_cer as ev


def preparer(env=os.environ) -> dict:
    """Variables à ajouter pour serveur_voix_bci (carte du modèle, modèle de langue présent ou non)."""
    if not env.get("BCI_VOIX_CLE"):
        raise SystemExit("BCI_VOIX_CLE absente : le serveur refuserait toute transcription")
    step = env.get("BCI_VOIX_STEP", "step_3000")
    carte = ev.write_card(env["FAIRSEQ2_USER_ASSET_DIR"], step,
                          ev.find_checkpoint(env["BCI_VOIX_MODELE"], step), "wourri_bci_voix")
    extra = {"BCI_VOIX_CARTE": carte}
    lm = env.get("BCI_VOIX_LM", "")
    if lm and not os.path.isfile(lm):
        print(f"Modèle de langue {lm} absent : décodage glouton", file=sys.stderr)
        extra["BCI_VOIX_LM"] = ""
    return extra


def main():
    os.environ.update(preparer())
    port = os.environ.get("BCI_VOIX_PORT", "8000")
    os.execvp("uvicorn", ["uvicorn", "serveur_voix_bci:app", "--host", "0.0.0.0", "--port", port, "--workers", "1"])


if __name__ == "__main__":
    main()
