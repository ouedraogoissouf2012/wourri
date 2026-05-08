"""
WOURI - Traduction NLLB (fallback IA)
Stratégie 3 : la plus lente mais couvre tout le vocabulaire.
Utilisée quand le dictionnaire ne suffit pas.

Migration ADR-0011 Phase 2 : NLLB passe par ModelRegistry (lock thread-safe,
unload disponible, comportement uniforme avec NeMo / TTS / Whisper).
"""
import logging
from typing import Optional

from .interfaces import ITranslator, TranslationResult, Direction
from app.services.model_registry import registry

logger = logging.getLogger(__name__)


def _load_nllb():
    """Loader NLLB appelé par ModelRegistry.

    Retourne un tuple (model, tokenizer, torch) — torch est inclus pour
    éviter à `translate()` de devoir le ré-importer (et garantit que la
    version torch utilisée à la traduction est la même qu'au chargement).
    """
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    from app.config import get_settings

    settings = get_settings()
    logger.info("[NLLB] Chargement du modèle de traduction...")
    tokenizer = AutoTokenizer.from_pretrained(settings.hf_translator_model)
    model = AutoModelForSeq2SeqLM.from_pretrained(settings.hf_translator_model)
    model.eval()
    logger.info("[NLLB] Modèle chargé!")
    return model, tokenizer, torch


class NLLBTranslator(ITranslator):
    """Traduction via le modèle NLLB-200 de Meta"""

    def __init__(self):
        # Gate post-erreur conservé au niveau de l'instance : évite de
        # retenter `registry.get(...)` (qui ne mémorise pas les échecs)
        # à chaque appel translate() en boucle si NLLB est cassé (OOM,
        # disque plein, etc.).
        self._load_failed = False

    @property
    def name(self) -> str:
        return "nllb"

    @property
    def priority(self) -> int:
        return 3  # Dernier recours

    def _ensure_loaded(self) -> bool:
        if registry.is_loaded("nllb"):
            return True
        if self._load_failed:
            return False  # Ne pas réessayer si déjà échoué (évite OOM répété)
        try:
            registry.get("nllb", loader=_load_nllb)
            return True
        except Exception as e:
            logger.error(f"[NLLB] Erreur chargement: {e}")
            logger.warning("[NLLB] NLLB désactivé - le dictionnaire sera utilisé seul")
            self._load_failed = True
            return False

    def can_handle(self, text: str, direction: Direction) -> bool:
        return True  # NLLB peut toujours essayer

    def translate(self, text: str, direction: Direction) -> Optional[TranslationResult]:
        if not self._ensure_loaded():
            return None

        try:
            model, tokenizer, torch = registry.get("nllb", loader=_load_nllb)

            if direction == Direction.BAM_TO_FR:
                src_lang = "bam_Latn"
                tgt_lang = "fra_Latn"
            else:
                src_lang = "fra_Latn"
                tgt_lang = "bam_Latn"

            tokenizer.src_lang = src_lang

            inputs = tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            )

            forced_bos_token_id = tokenizer.convert_tokens_to_ids(tgt_lang)

            with torch.no_grad():
                generated_tokens = model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos_token_id,
                    max_length=512,
                    num_beams=3,
                    no_repeat_ngram_size=2,
                )

            result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]

            # Vérification qualité basique
            if not result or len(result) < 2:
                return None

            return TranslationResult(
                text=result,
                source_text=text,
                direction=direction,
                strategy_used=self.name,
                confidence=0.5,  # Confiance moyenne par défaut pour NLLB
                words_matched=0,
                words_total=len(text.split()),
            )

        except Exception as e:
            logger.error(f"[NLLB] Erreur traduction: {e}")
            return None

    def get_model_and_tokenizer(self):
        """Accès direct au modèle (pour compatibilité avec tts_bambara/tts_dioula).

        Retourne (model, tokenizer) ou (None, None) si NLLB indisponible.
        """
        if not self._ensure_loaded():
            return None, None
        model, tokenizer, _torch = registry.get("nllb", loader=_load_nllb)
        return model, tokenizer
