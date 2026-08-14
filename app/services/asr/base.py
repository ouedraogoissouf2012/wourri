"""
WOURI - Interface ASR (Liskov Substitution Principle).

Toute implémentation ASR doit hériter de ASRProvider.
Permet de substituer NeMo, MMS-dyu ou MMS-generic sans modifier le code appelant.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional


class ASRProvider(ABC):
    """Interface commune pour tous les services de reconnaissance vocale.

    Contrat Liskov : tout ASRProvider peut être utilisé partout où un
    ASRProvider est attendu, sans modifier le comportement du programme.

    #301 — séparation conversion / inférence : l'inférence part TOUJOURS d'un
    WAV 16kHz déjà converti (`transcribe_wav`). La conversion ffmpeg est faite
    en amont — une seule fois par la chaîne pour tous les providers, ou par la
    méthode template `transcribe(bytes, ext)` quand un provider est utilisé seul.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nom lisible du provider (pour les logs)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Retourne True si le provider est utilisable (dépendances installées, modèle trouvé)."""
        ...

    @abstractmethod
    def transcribe_wav(self, wav_path: str) -> Optional[str]:
        """Transcrit un WAV 16kHz mono déjà converti en texte.

        C'est le seul point d'inférence à implémenter : la conversion audio est
        déjà faite en amont (#301). Inclut le post-traitement propre au provider
        (ex. normalisation bambara pour NeMo). Méthode synchrone : la chaîne
        l'exécute dans un thread pour ne pas bloquer le event loop.

        Args:
            wav_path: Chemin d'un WAV 16kHz mono prêt à transcrire.

        Returns:
            Texte transcrit, ou None si la transcription échoue.
        """
        ...

    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        """Transcrit des bytes audio en texte (conversion incluse).

        Méthode template : convertit `audio_bytes` en WAV 16kHz UNE fois puis
        délègue à `transcribe_wav`. Utilisée quand un provider est appelé seul
        (hors chaîne). Dans la chaîne, `ASRChain` convertit une seule fois et
        appelle directement `transcribe_wav` (#301), évitant N conversions.

        Args:
            audio_bytes: Contenu brut du fichier audio.
            file_extension: Extension du fichier source (ogg, mp3, wav, webm).

        Returns:
            Texte transcrit, ou None si la transcription échoue.
        """
        if not self.is_available():
            return None

        # Import local : évite un cycle base ↔ audio_utils au chargement.
        from app.services.asr.audio_utils import prepared_wav_16k

        with prepared_wav_16k(audio_bytes, file_extension, self.name) as wav_path:
            if wav_path is None:
                return None
            return await asyncio.to_thread(self.transcribe_wav, wav_path)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} available={self.is_available()}>"
