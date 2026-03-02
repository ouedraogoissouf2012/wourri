"""
WOURI - Service NLU (Natural Language Understanding)
Extraction de concepts + classification d'intention + reconstruction de phrase française
depuis une transcription bambara/dioula partielle (sortie ASR NeMo TDT).
"""
from .nlu_service import NLUService, NLUResult, get_nlu_service

__all__ = ["NLUService", "NLUResult", "get_nlu_service"]
