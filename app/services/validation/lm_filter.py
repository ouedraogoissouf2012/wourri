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
    - Flag config : ENABLE_LM_RESCORING (default: False), injecté par get_lm_filter().
    - Binaire KenLM : data/models/kenlm_dyu_agri.binary, chemin surchargeable via
      l'env KENLM_DYU_PATH (même pattern que MMS_DYU_ADAPTER_PATH — artefact ML
      monté en volume au déploiement V3, jamais versionné).
    - Seuils (PPL/OOV/répétitions) : externalisés en config, injectés au constructeur.

Feature flag :
    Si ENABLE_LM_RESCORING=False OU que le binaire KenLM est absent (ou kenlm non
    installé), le filtre est inactif et retourne toujours 'HIGH' (pass-through).
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
# Chemin binaire KenLM — surchargeable via KENLM_DYU_PATH (même pattern que
# MMS_DYU_ADAPTER_PATH dans mms_dyu_provider.py : artefact ML monté en volume au
# déploiement V3, exclu de l'image et jamais versionné dans git).
_DEFAULT_LM_PATH = Path(
    os.getenv(
        "KENLM_DYU_PATH",
        str(_PROJECT_ROOT / "data" / "models" / "kenlm_dyu_agri.binary"),
    )
)

# Seuils empiriques par défaut — externalisés en config (Settings.lm_*), injectés
# au constructeur par get_lm_filter(). Ces constantes restent les valeurs par
# défaut du constructeur (rétrocompat + tests qui n'injectent pas de seuils).
# Source : littérature ASR langues basse-ressource (Kumar et al. 2023).
PPL_REJECT = 500.0      # Au-delà → transcription absurde (REJECT)
PPL_CAUTION = 150.0     # Entre 150-500 → faible confiance (MEDIUM). Attendu < PPL_REJECT.
OOV_REJECT = 0.40       # Plus de 40% de mots hors-vocabulaire → probablement pas dyu (REJECT)
OOV_CAUTION = 0.15      # Entre 15-40% → faible confiance (MEDIUM). Attendu <= OOV_REJECT.
REPEAT_MAX_REJECT = 3   # Plus de 3 répétitions du même bigramme (REJECT)


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

    def __init__(
        self,
        model_path: Optional[Path] = None,
        lexicon: Optional[set] = None,
        *,
        enabled: bool = False,
        ppl_reject: float = PPL_REJECT,
        ppl_caution: float = PPL_CAUTION,
        oov_reject: float = OOV_REJECT,
        oov_caution: float = OOV_CAUTION,
        repeat_max_reject: int = REPEAT_MAX_REJECT,
    ):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.model_path = Path(model_path) if model_path else _DEFAULT_LM_PATH
        self.lm = None
        self.lexicon = lexicon or set()
        self.available = False
        # Feature flag ENABLE_LM_RESCORING (ADR-0029, #94) : injecté par
        # get_lm_filter() depuis la config. Défaut False = fail-safe (le filtre
        # est OFF par défaut ; une construction directe n'active jamais le
        # rescoring sans opt-in explicite). Si False → _load() n'active rien.
        self.enabled = enabled
        # Seuils de verdict injectés (externalisés en config).
        self.ppl_reject = ppl_reject
        self.ppl_caution = ppl_caution
        self.oov_reject = oov_reject
        self.oov_caution = oov_caution
        self.repeat_max_reject = repeat_max_reject
        self._load()

    def _load(self):
        """Charge le modèle KenLM. Silencieux si indisponible."""
        # Feature flag : filtre désactivé → inactif (pass-through), on ne
        # charge même pas le binaire. Respecte ENABLE_LM_RESCORING (#94).
        if not self.enabled:
            logger.info("[LM-FILTER] ENABLE_LM_RESCORING=False — filtre inactif (pass-through)")
            return

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

        # Verdict composite (tous les seuils injectés depuis la config).
        if (ppl_norm > self.ppl_reject
                or oov_ratio > self.oov_reject
                or repeat_max > self.repeat_max_reject):
            verdict = "REJECT"
        elif ppl_norm > self.ppl_caution or oov_ratio > self.oov_caution:
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
    """Retourne l'instance singleton du filtre LM.

    Lit le flag ENABLE_LM_RESCORING et les 4 seuils depuis la config (ADR-0029,
    #94) et les injecte au constructeur. Import local de get_settings pour éviter
    tout couplage d'import au chargement du module (le filtre est importé
    paresseusement par app/services/asr/chain.py).
    """
    global _default_filter
    if _default_filter is None:
        from app.config import get_settings

        settings = get_settings()
        _default_filter = DioulaLMFilter(
            enabled=settings.enable_lm_rescoring,
            ppl_reject=settings.lm_ppl_reject,
            ppl_caution=settings.lm_ppl_caution,
            oov_reject=settings.lm_oov_reject,
            oov_caution=settings.lm_oov_caution,
            repeat_max_reject=settings.lm_repeat_max_reject,
        )
    return _default_filter
