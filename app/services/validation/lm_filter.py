"""
Wourri — LM Filter (KenLM shallow fusion pour ASR dioula CI)

Étape 5 du pipeline normalizer : rescorer les transcriptions avec un modèle
de langue 4-gram entraîné sur ~31k phrases dioula CI (Koumankan + Findora + corpus IVR).

Objectif : détecter les hallucinations NeMo type "ka ka aw" (kakawo fragmenté)
en mesurant la perplexité normalisée.

Usage :
    from app.services.validation.lm_filter import DioulaLMFilter

    lm = DioulaLMFilter()
    if lm.available:
        score = lm.score("n bɛ fɛ ka kakawo sɛnɛ")
        # score.ppl_norm bas = naturel, haut = improbable

Activation :
    - Variable config : ENABLE_LM_RESCORING (default: False)
    - Fichier modèle : data/models/kenlm_dyu_agri.binary (entraîné sur Colab)

Feature flag :
    Si le fichier KenLM n'existe pas ou ENABLE_LM_RESCORING=False,
    le filtre est inactif et retourne toujours 'HIGH' (pass-through).
"""
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # wouri-api/
_DEFAULT_LM_PATH = _PROJECT_ROOT / "data" / "models" / "kenlm_dyu_agri.binary"

# Seuils empiriques — à calibrer après première utilisation en prod
# Source : littérature ASR langues basse-ressource (Kumar et al. 2023)
PPL_REJECT = 500.0      # Au-delà → transcription absurde
PPL_CAUTION = 150.0     # Entre 150-500 → faible confiance
OOV_REJECT = 0.40       # Plus de 40% de mots hors-vocabulaire → probablement pas dyu
REPEAT_MAX_REJECT = 3   # Plus de 3 répétitions du même bigramme


@dataclass
class LMScore:
    """Résultat d'un scoring LM."""
    ppl_norm: float       # Perplexité normalisée par longueur
    oov_ratio: float      # Ratio mots hors-vocabulaire
    repeat_max: int       # Nombre max de répétitions du bigramme dominant
    verdict: str          # HIGH | MEDIUM | REJECT
    logprob: float        # Log-probabilité brute
    n_tokens: int

    @property
    def is_suspect(self) -> bool:
        return self.verdict in ("MEDIUM", "REJECT")


class DioulaLMFilter:
    """Filtre de langue KenLM pour détecter les hallucinations ASR dioula.

    Charge le modèle KenLM une seule fois (singleton lazy). Si KenLM n'est
    pas installé ou le fichier modèle absent, devient inactif (pass-through).
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_path: Optional[Path] = None, lexicon: Optional[set] = None):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.model_path = Path(model_path) if model_path else _DEFAULT_LM_PATH
        self.lm = None
        self.lexicon = lexicon or set()
        self.available = False
        self._load()

    def _load(self):
        """Charge le modèle KenLM. Silencieux si indisponible."""
        # Vérifier que kenlm est installé
        try:
            import kenlm
        except ImportError:
            logger.info("[LM-FILTER] kenlm non installé — filtre inactif (pass-through)")
            return

        # Vérifier que le fichier modèle existe
        if not self.model_path.exists():
            logger.info(
                "[LM-FILTER] Modèle KenLM absent (%s) — filtre inactif (pass-through). "
                "Entraîner via finetune/colab/wourri_asr_improvements.ipynb",
                self.model_path,
            )
            return

        # Charger
        try:
            self.lm = kenlm.Model(str(self.model_path))
            self.available = True
            size_mb = os.path.getsize(self.model_path) / 1024 / 1024
            logger.info(
                "[LM-FILTER] KenLM chargé: %s (%.1f MB)",
                self.model_path.name, size_mb,
            )
        except Exception as e:
            logger.error("[LM-FILTER] Erreur chargement KenLM: %s", e)

    def score(self, text: str) -> LMScore:
        """Score une transcription et retourne un verdict.

        Args:
            text: texte dioula à scorer (déjà normalisé, en minuscules recommandé)

        Returns:
            LMScore avec verdict HIGH/MEDIUM/REJECT et métriques détaillées.
            Si LM indisponible : toujours HIGH (pass-through).
        """
        if not self.available:
            return LMScore(
                ppl_norm=0.0, oov_ratio=0.0, repeat_max=0,
                verdict="HIGH", logprob=0.0, n_tokens=0,
            )

        tokens = re.findall(r"\S+", text.lower())
        n = len(tokens)

        if n == 0:
            return LMScore(
                ppl_norm=1e6, oov_ratio=1.0, repeat_max=0,
                verdict="REJECT", logprob=-1e6, n_tokens=0,
            )

        # Log-probabilité KenLM
        logprob = self.lm.score(text, bos=True, eos=True)
        ppl_norm = 10 ** (-logprob / n)

        # Ratio hors-vocabulaire (si un lexique est fourni)
        oov_ratio = 0.0
        if self.lexicon:
            oov = sum(1 for t in tokens if t not in self.lexicon)
            oov_ratio = oov / n

        # Répétitions bigramme (détecte "ka ka ka" pathologique)
        bigrams = list(zip(tokens, tokens[1:]))
        repeat_max = max(Counter(bigrams).values()) if bigrams else 0

        # Verdict composite
        if (ppl_norm > PPL_REJECT
                or oov_ratio > OOV_REJECT
                or repeat_max > REPEAT_MAX_REJECT):
            verdict = "REJECT"
        elif ppl_norm > PPL_CAUTION or oov_ratio > 0.15:
            verdict = "MEDIUM"
        else:
            verdict = "HIGH"

        return LMScore(
            ppl_norm=ppl_norm,
            oov_ratio=oov_ratio,
            repeat_max=repeat_max,
            verdict=verdict,
            logprob=logprob,
            n_tokens=n,
        )

    def rescore_candidates(self, candidates: list[str]) -> Optional[str]:
        """Choisit le meilleur candidat parmi plusieurs hypothèses ASR.

        Args:
            candidates: liste de transcriptions alternatives (n-best list de NeMo).

        Returns:
            La candidate avec la meilleure perplexité normalisée, ou None si LM indisponible.
        """
        if not self.available or not candidates:
            return candidates[0] if candidates else None

        scored = [(c, self.score(c).ppl_norm) for c in candidates]
        scored.sort(key=lambda x: x[1])  # plus petit PPL = meilleur
        return scored[0][0]


# Singleton global
_default_filter: Optional[DioulaLMFilter] = None


def get_lm_filter() -> DioulaLMFilter:
    """Retourne l'instance singleton du filtre LM."""
    global _default_filter
    if _default_filter is None:
        _default_filter = DioulaLMFilter()
    return _default_filter
