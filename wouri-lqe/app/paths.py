"""Chemins persistants (volume LQE_DATA_DIR)."""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def data_dir() -> Path:
    p = Path(get_settings().lqe_data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p
