"""
WOURI - Traduction NLLB (fallback IA)
Stratégie 3 : la plus lente mais couvre tout le vocabulaire.
Utilisée quand le dictionnaire ne suffit pas.
Pré-chargée au démarrage pour éviter les OOM pendant les requêtes.
"""
from typing import Optional
from .interfaces import ITranslator, TranslationResult, Direction


class NLLBTranslator(ITranslator):
    """Traduction via le modèle NLLB-200 de Meta"""

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._torch = None
        self._load_failed = False  # Empêcher les tentatives répétées si OOM

    @property
    def name(self) -> str:
        return "nllb"

    @property
    def priority(self) -> int:
        return 3  # Dernier recours

    def _ensure_loaded(self):
        if self._model is not None:
            return True
        if self._load_failed:
            return False  # Ne pas réessayer si déjà échoué (évite OOM répété)
        try:
            import torch
            self._torch = torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            from app.config import get_settings
            settings = get_settings()

            print("[NLLB] Chargement du modèle de traduction...")
            self._tokenizer = AutoTokenizer.from_pretrained(settings.hf_translator_model)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(settings.hf_translator_model)
            self._model.eval()
            print("[NLLB] Modèle chargé!")
            return True
        except Exception as e:
            print(f"[NLLB] Erreur chargement: {e}")
            print("[NLLB] NLLB désactivé - le dictionnaire sera utilisé seul")
            self._load_failed = True
            return False

    def can_handle(self, text: str, direction: Direction) -> bool:
        return True  # NLLB peut toujours essayer

    def translate(self, text: str, direction: Direction) -> Optional[TranslationResult]:
        if not self._ensure_loaded():
            return None

        try:
            if direction == Direction.BAM_TO_FR:
                src_lang = "bam_Latn"
                tgt_lang = "fra_Latn"
            else:
                src_lang = "fra_Latn"
                tgt_lang = "bam_Latn"

            self._tokenizer.src_lang = src_lang

            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            )

            forced_bos_token_id = self._tokenizer.convert_tokens_to_ids(tgt_lang)

            with self._torch.no_grad():
                generated_tokens = self._model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos_token_id,
                    max_length=512,
                    num_beams=3,
                    no_repeat_ngram_size=2,
                )

            result = self._tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]

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
            print(f"[NLLB] Erreur traduction: {e}")
            return None

    def get_model_and_tokenizer(self):
        """Accès direct au modèle (pour compatibilité avec tts_bambara)"""
        self._ensure_loaded()
        return self._model, self._tokenizer
