"""Recopie les modules de finetune/ dans les cellules %%writefile des notebooks de
finetune/colab/, qui doivent rester autonomes (Kaggle, GPU loué).

Chaque cellule de code commençant par « %%writefile <module>.py » reçoit le contenu
exact de finetune/<module>.py, si ce module existe. Une cellule %%writefile propre au
notebook (ex. prepare_data.py du notebook Kaggle) est laissée telle quelle.

Usage : python finetune/colab/sync_smoke_test_notebook.py
Garde-fous : finetune/test_dictee_to_parquet.py et finetune/test_prepare_bci_dataset.py.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FINETUNE = HERE.parent
NOTEBOOKS = [
    HERE / "omnilingual_finetune_smoke_test.ipynb",
    HERE / "omnilingual_finetune_1b_gpu_loue.ipynb",
]
MARKER = re.compile(r"%%writefile ([\w.]+\.py)\n")


def embedded_modules(nb):
    """[(cellule, nom du module)] des cellules %%writefile d'un notebook."""
    found = []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        m = MARKER.match("".join(cell["source"]))
        if m:
            found.append((cell, m.group(1)))
    return found


def main():
    for notebook in NOTEBOOKS:
        nb = json.loads(notebook.read_text(encoding="utf-8"))
        synced = []
        for cell, name in embedded_modules(nb):
            module = FINETUNE / name
            if module.is_file():
                cell["source"] = f"%%writefile {name}\n" + module.read_text(encoding="utf-8")
                synced.append(name)
        if not synced:
            raise SystemExit(f"{notebook.name} : aucune cellule %%writefile d'un module de finetune/")
        notebook.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"OK : {', '.join(synced)} recopié(s) dans {notebook.name}")


if __name__ == "__main__":
    main()
