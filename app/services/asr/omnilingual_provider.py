"""
WOURI - ASR Provider Omnilingual (Meta, multilingue 1672 langues).

Provider basé sur Meta Omnilingual ASR (Apache 2.0).
Référence : https://github.com/facebookresearch/omnilingual-asr

Configurable par variante :
    - 300m : omniASR_CTC_300M  (le plus léger, validé Phase 1)
    - 1b   : omniASR_CTC_1B
    - 1.2b : omniASR_LLM_1_2B
    - 7b   : omniASR_LLM_7B    (nécessite A100 24GB)

Langue par défaut : dyu_Latn (dioula CI). Toute langue dans
omnilingual_asr.models.wav2vec2_llama.lang_ids.supported_langs (1672 codes).

Créé en Phase 2 d'ADR-0003 mais NON activé dans la chain (Phase 4).
Voir docs/benchmarks/0002-omnilingual-env-setup.md pour install reproductible.
"""
import logging
from typing import Optional

from app.services.asr.base import ASRProvider

logger = logging.getLogger(__name__)


# Mapping size → model_card officiel (validé Phase 1 — PAS "_v2")
MODEL_CARDS: dict[str, str] = {
    "300m": "omniASR_CTC_300M",
    "1b": "omniASR_CTC_1B",
    "1.2b": "omniASR_LLM_1_2B",
    "7b": "omniASR_LLM_7B",
}


# Lazy imports — graceful si fairseq2 / omnilingual-asr non installés
_omnilingual_available = False
_ASRInferencePipeline = None
_supported_langs: Optional[list] = None

try:
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline as _Pipeline
    from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs as _langs
    _ASRInferencePipeline = _Pipeline
    _supported_langs = _langs
    _omnilingual_available = True
except ImportError:
    pass


class OmnilingualASR(ASRProvider):
    """ASR multilingue Meta Omnilingual (1672 langues, Apache 2.0).

    Args:
        model_size: variante du modèle ("300m", "1b", "1.2b", "7b").
                    Par défaut "300m".
        default_lang: code langue cible au format {lang}_{script}
                      (ex: "dyu_Latn", "bam_Latn"). Par défaut "dyu_Latn".

    Raises:
        ValueError: si model_size n'est pas dans MODEL_CARDS.
    """

    def __init__(self, model_size: str = "300m", default_lang: str = "dyu_Latn"):
        if model_size not in MODEL_CARDS:
            raise ValueError(
                f"model_size invalide: '{model_size}'. "
                f"Valeurs acceptées: {sorted(MODEL_CARDS.keys())}"
            )
        self._model_size = model_size
        self._default_lang = default_lang
        self._model_card = MODEL_CARDS[model_size]

    @property
    def name(self) -> str:
        return f"Omnilingual {self._model_size.upper()}"

    def is_available(self) -> bool:
        if not _omnilingual_available:
            return False
        # La langue par défaut doit être dans la liste des langues supportées.
        # Évite un crash silencieux à l'inférence si typo dans la config.
        if _supported_langs is not None and self._default_lang not in _supported_langs:
            logger.warning(
                "[%s] langue '%s' absente de supported_langs (%d langues)",
                self.name, self._default_lang, len(_supported_langs),
            )
            return False
        return True

    def _get_pipeline(self):
        """Charge (ou récupère depuis le cache) le pipeline d'inférence."""
        from app.services.model_registry import registry

        registry_key = f"omnilingual_{self._model_size}"

        def _load():
            logger.info("[%s] Chargement modèle (%s)...", self.name, self._model_card)
            pipeline = _ASRInferencePipeline(model_card=self._model_card)
            logger.info("[%s] Modèle chargé!", self.name)
            return pipeline

        return registry.get(registry_key, loader=_load)

    def transcribe_wav(self, wav_path: str) -> Optional[str]:
        """Transcrit un WAV 16kHz avec Omnilingual."""
        pipeline = self._get_pipeline()
        if pipeline is None:
            return None

        try:
            transcriptions = pipeline.transcribe(
                [wav_path],
                lang=[self._default_lang],
                batch_size=1,
            )

            if not transcriptions:
                return ""

            transcription = transcriptions[0].strip()
            if transcription:
                logger.info("[%s] Transcription: '%s'", self.name, transcription)
            return transcription

        except Exception as e:
            logger.error("[%s] Erreur transcription: %s", self.name, e, exc_info=True)
            return None
