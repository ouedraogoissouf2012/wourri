"""WOURI — outils de traitement de la langue mandingue (dioula CI / bambara Mali).

Voir ADR-0020 (docs/adr/0020-filtre-bam-dyu-perimetre-reduit.md).
"""

from app.services.language.bam_dyu_phonology import (
    phonological_variants,
    variants_for_text,
)

__all__ = ["phonological_variants", "variants_for_text"]
