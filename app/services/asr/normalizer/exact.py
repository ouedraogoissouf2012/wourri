"""Étapes 1-2 : corrections exactes JSON et fusions NeMo."""
from app.services.asr.normalizer.data import _EXACT_CORRECTIONS


def _apply_exact_corrections(text: str) -> str:
    """Applique les corrections exactes (JSON + normalizer bambara fusions).

    Les corrections multi-mots (espaces, particules) sont appliquées
    par remplacement de sous-chaîne, ordonnées par longueur décroissante
    pour éviter les conflits (ex: "ani sɔgɔma" avant "ani").
    """
    result = f" {text} "
    for wrong in sorted(_EXACT_CORRECTIONS, key=len, reverse=True):
        if wrong in result:
            result = result.replace(wrong, _EXACT_CORRECTIONS[wrong])
    return result.strip()


def _apply_nemo_fusions(text: str) -> str:
    """Applique les corrections de fusions syllabiques NeMo.

    Délègue au normalizer bambara existant (FUSIONS + PHRASE_SUBS).
    """
    from app.services.asr_bambara_normalizer import normalize_bambara_asr
    return normalize_bambara_asr(text) or text
