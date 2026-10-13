"""Étapes 1-2 : corrections exactes JSON et fusions NeMo."""
import re

from app.services.asr.normalizer.data import _EXACT_CORRECTIONS, _REGLES


def _motif_fin_de_mot(fautif: str) -> re.Pattern[str]:
    """Motif d'une clé de correction qui ne s'arrête jamais au milieu d'un mot.

    Une clé qui finit par une lettre ne se déclenche plus si le mot continue
    après elle : « ka ba » ne touche plus « ka bana » ni « ka bananku », et
    « a ni su » ne retouche plus le « a ni sufɛ » produit par « an ni su ».
    Une clé d'un seul mot admet toutefois après elle un suffixe de pluriel
    (`suffixes_pluriel` d'asr_normalizer_regles.json), qu'elle laisse en
    place : « tigkaw » devient « tigaw », « mangogow » « mangorow ».
    Le début de la clé peut rester collé à un mot : « sɔgɔ ma » corrige
    toujours « inisɔgɔ ma » en « inisɔgɔma », que FUSIONS sépare ensuite en
    « i ni sɔgɔma ». Une clé bordée d'espaces (« kan ») garde ses limites.
    """
    if not re.match(r"\w", fautif[-1:]):
        return re.compile(re.escape(fautif))
    suffixes = [] if " " in fautif.strip() else _REGLES.get("suffixes_pluriel", [])
    pluriel = "|".join(re.escape(suffixe) for suffixe in suffixes)
    fin = rf"(?=(?:{pluriel})?(?!\w))" if pluriel else r"(?!\w)"
    return re.compile(re.escape(fautif) + fin)


# Clés triées par longueur décroissante (« ani sɔgɔma » avant « ani »).
_CORRECTIONS_ORDONNEES: list[tuple[str, re.Pattern[str], str]] = [
    (fautif, _motif_fin_de_mot(fautif), juste)
    for fautif, juste in sorted(
        _EXACT_CORRECTIONS.items(), key=lambda paire: len(paire[0]), reverse=True
    )
]


def _apply_exact_corrections(text: str) -> str:
    """Applique les corrections exactes (JSON + normalizer bambara fusions).

    Les corrections multi-mots (espaces, particules) sont appliquées
    sans couper de mot (_motif_fin_de_mot), par longueur décroissante
    pour éviter les conflits (ex: "ani sɔgɔma" avant "ani").
    """
    result = f" {text} "
    for fautif, motif, juste in _CORRECTIONS_ORDONNEES:
        if fautif in result:
            result = motif.sub(lambda _m, remplacement=juste: remplacement, result)
    return result.strip()


def _apply_nemo_fusions(text: str) -> str:
    """Applique les corrections de fusions syllabiques NeMo.

    Délègue au normalizer bambara existant (FUSIONS + PHRASE_SUBS).
    """
    from app.services.asr_bambara_normalizer import normalize_bambara_asr
    return normalize_bambara_asr(text) or text
