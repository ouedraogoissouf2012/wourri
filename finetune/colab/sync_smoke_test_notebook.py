"""Recopie finetune/dictee_to_parquet.py dans la cellule %%writefile du notebook
omnilingual_finetune_smoke_test.ipynb, qui doit rester autonome sur Kaggle.

Usage : python finetune/colab/sync_smoke_test_notebook.py
Garde-fou : finetune/test_dictee_to_parquet.py::test_notebook_embarque_le_module_a_jour.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "omnilingual_finetune_smoke_test.ipynb"
MODULE = HERE.parent / "dictee_to_parquet.py"
MARKER = "%%writefile dictee_to_parquet.py\n"


def main():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = [
        c
        for c in nb["cells"]
        if c["cell_type"] == "code" and "".join(c["source"]).startswith(MARKER)
    ]
    if len(cells) != 1:
        raise SystemExit(f"{len(cells)} cellule(s) '{MARKER.strip()}' trouvée(s), 1 attendue")
    cells[0]["source"] = MARKER + MODULE.read_text(encoding="utf-8")
    NOTEBOOK.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"OK : {MODULE.name} recopié dans {NOTEBOOK.name}")


if __name__ == "__main__":
    main()
