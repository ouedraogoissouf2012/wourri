"""Chemins LQE persistants.

En prod Dokploy, `/app/data` n'est PAS monté → perdu à chaque Redeploy.
On écrit sous `/app/logs/lqe` (volume `wourri_api_logs` déjà monté).
Surcharge : LQE_DATA_DIR.
"""
from __future__ import annotations

import os
from pathlib import Path


def lqe_data_dir() -> Path:
    env = (os.getenv("LQE_DATA_DIR") or "").strip()
    if env:
        p = Path(env)
    elif Path("/app/logs").is_dir():
        p = Path("/app/logs/lqe")
    else:
        p = Path(__file__).resolve().parent.parent.parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def improvement_tasks_path() -> Path:
    return lqe_data_dir() / "improvement_tasks.jsonl"


def baoule_corpus_path() -> Path:
    return lqe_data_dir() / "baoule_corpus.jsonl"
