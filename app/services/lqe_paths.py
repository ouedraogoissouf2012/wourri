"""Chemins LQE persistants.

Données métier de l'atelier embarqué (improvement_tasks / baoule_corpus).
En prod (issue #488), un volume dédié est monté sur `/app/data` — SÉPARÉ du
volume des logs (ADR-0025 : données métier ≠ journaux). On écrit sous
`/app/data/lqe`. Surcharge : LQE_DATA_DIR.
"""
from __future__ import annotations

import os
from pathlib import Path


def lqe_data_dir() -> Path:
    env = (os.getenv("LQE_DATA_DIR") or "").strip()
    if env:
        p = Path(env)
    elif Path("/app/data").is_dir():
        p = Path("/app/data/lqe")
    else:
        p = Path(__file__).resolve().parent.parent.parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def improvement_tasks_path() -> Path:
    return lqe_data_dir() / "improvement_tasks.jsonl"


def baoule_corpus_path() -> Path:
    return lqe_data_dir() / "baoule_corpus.jsonl"
