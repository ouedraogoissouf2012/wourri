"""
WOURI - ASR Provider NeMo Soloni (bambara, décodeur TDT).

Provider principal pour le bambara malien. Utilise le modèle
RobotsMali/soloni-114m-tdt-ctc-v0 avec décodeur malsd_batch.
"""
import logging
import os
import tempfile
from typing import Optional

from app.services.asr.base import ASRProvider
from app.services.asr.audio_utils import transcribe_with_temp_files

logger = logging.getLogger(__name__)

NEMO_PATH = os.getenv(
    "NEMO_MODEL_PATH",
    os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface", "hub",
        "models--RobotsMali--soloni-114m-tdt-ctc-v0", "snapshots",
        "c0078bb2285e6157960710c5751bbdf83b1a758d", "soloni-114m-tdt-ctc-v0.nemo",
    ),
)

_nemo_available = False
_nemo_asr = None
_torch = None

try:
    import nemo.collections.asr as nemo_asr_mod
    import torch as torch_mod
    _nemo_asr = nemo_asr_mod
    _torch = torch_mod
    _nemo_available = True
except ImportError:
    pass


class NemoSoloniASR(ASRProvider):
    """ASR bambara via NeMo Soloni TDT (114M params)."""

    @property
    def name(self) -> str:
        return "NeMo Soloni"

    def is_available(self) -> bool:
        return _nemo_available and os.path.exists(NEMO_PATH)

    def _get_model(self):
        from app.services.model_registry import registry

        def _load():
            logger.info("[%s] Chargement modèle...", self.name)
            model = _nemo_asr.models.ASRModel.restore_from(
                NEMO_PATH, map_location=_torch.device("cpu"),
            )
            model.eval()

            try:
                from omegaconf import open_dict
                with open_dict(model.cfg):
                    model.cfg.decoding.strategy = "beam"
                    model.cfg.decoding.beam.beam_size = 4
                    model.cfg.decoding.beam.search_type = "malsd_batch"
                model.change_decoding_strategy(model.cfg.decoding)
                logger.info("[%s] Décodeur malsd_batch activé", self.name)
            except Exception as e:
                logger.warning("[%s] malsd_batch non disponible: %s", self.name, e)

            logger.info("[%s] Modèle chargé!", self.name)
            return model

        return registry.get("nemo_soloni", loader=_load)

    def preload(self):
        """Force le chargement du modèle (préchargement au démarrage, ADR-0021).

        Déclenche le chargement via le registry sous la clé partagée
        `nemo_soloni`. Le runtime réutilise exactement ce modèle et sa config
        décodeur — plus de divergence préchargé/runtime possible. Retourne le
        modèle chargé, ou None si NeMo est indisponible.
        """
        if not self.is_available():
            return None
        return self._get_model()

    def _transcribe_wav(self, wav_path: str) -> Optional[str]:
        """Transcrit un WAV 16kHz avec NeMo TDT."""
        model = self._get_model()
        if model is None:
            return None

        try:
            with _torch.no_grad():
                results = model.transcribe([wav_path])

            if not results:
                return ""

            result = results[0]
            if isinstance(result, list):
                result = result[0] if result else ""
            if hasattr(result, "text"):
                return result.text.strip()
            return str(result).strip()

        except Exception as e:
            logger.error("[%s] Erreur inférence: %s", self.name, e, exc_info=True)
            return None

    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        if not self.is_available():
            return None

        result = await transcribe_with_temp_files(
            audio_bytes, file_extension, self._transcribe_wav, self.name,
        )

        # Post-traitement : normalisation bambara
        if result:
            from app.services.asr_bambara_normalizer import normalize_bambara_asr
            result = normalize_bambara_asr(result)
            logger.info("[%s] Transcription: '%s'", self.name, result)

        return result


# --- Préchargement / statut (ADR-0021) ---------------------------------------
# Remplacent app/services/asr_soloni_nemo.py (supprimé). Le préchargement au
# démarrage (main.py) et le statut santé passent désormais par ce provider
# canonique — seule source de vérité du modèle NeMo Soloni et de sa config.


def preload_nemo_model():
    """Précharge le modèle NeMo Soloni au démarrage. None si indisponible."""
    return NemoSoloniASR().preload()


def get_nemo_status() -> dict:
    """Statut du provider NeMo Soloni (disponibilité, présence modèle, cache)."""
    from app.services.model_registry import registry

    return {
        "nemo_available": _nemo_available,
        "model_path_exists": os.path.exists(NEMO_PATH),
        "model_loaded": registry.is_loaded("nemo_soloni"),
    }
