"""Sous-package STT post-traitement.

Extrait du refactor `stt_whisper.py` (2026-05-28). Heuristiques de
detection d'hallucination Whisper et de mauvaise transcription Dioula
(`postprocess`). Anticipe l'ajout d'autres modules (cf. ADR-0005
Phase D : detection ML AfroLID dans un futur `lang_detect.py`).
"""
from app.services.stt.postprocess import (
    is_likely_dioula_input,
    is_likely_hallucination,
)

__all__ = ["is_likely_dioula_input", "is_likely_hallucination"]
