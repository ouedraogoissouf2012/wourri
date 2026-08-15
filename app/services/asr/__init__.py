"""
WOURI - Package ASR.

Point d'entrée unique pour la reconnaissance vocale.
Le routeur importe uniquement get_asr_chain() — jamais les providers directement.
"""
from app.services.asr.base import ASRProvider
from app.services.asr.chain import ASRChain

# Singleton de la chaîne ASR — construit au premier appel
_asr_chain: ASRChain | None = None


def get_asr_chain() -> ASRChain:
    """Retourne la chaîne ASR configurée (singleton).

    Ordre par défaut (bambara/dioula) — ADR-0027 Option A :
    1. MMS-dyu adapter (dioula CI, fine-tuné AXE-4)
    2. MMS-generic (8 langues, fallback universel)

    MMS-dyu est aussi agri_fallback : si le premier passage (ou un
    provider antérieur) transcrit sans mot-clé agricole, on retente.
    NeMo Soloni retiré (jamais exécuté ; réversible git revert).
    """
    global _asr_chain
    if _asr_chain is not None:
        return _asr_chain

    from app.services.asr.mms_dyu_provider import MMSDyuASR
    from app.services.asr.mms_generic_provider import MMSGenericASR

    mms_dyu = MMSDyuASR()
    mms_generic = MMSGenericASR(language_code="bam")

    _asr_chain = ASRChain(
        providers=[mms_dyu, mms_generic],
        agri_fallback=mms_dyu,
    )

    return _asr_chain


def get_generic_asr_chain(language_code: str) -> ASRChain:
    """Retourne une chaîne ASR pour une langue ivoirienne non-bambara.

    Pour les langues autres que bam (ati, dyi, myk, etc.),
    seul MMS-generic est disponible.
    """
    from app.services.asr.mms_generic_provider import MMSGenericASR

    provider = MMSGenericASR(language_code=language_code)
    return ASRChain(providers=[provider])


__all__ = [
    "ASRProvider",
    "ASRChain",
    "get_asr_chain",
    "get_generic_asr_chain",
]
