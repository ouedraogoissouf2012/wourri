"""
WOURI - Interface ASR (Liskov Substitution Principle).

Toute implémentation ASR doit hériter de ASRProvider.
Permet de substituer NeMo, MMS-dyu ou MMS-generic sans modifier le code appelant.
"""
from abc import ABC, abstractmethod
from typing import Optional


class ASRProvider(ABC):
    """Interface commune pour tous les services de reconnaissance vocale.

    Contrat Liskov : tout ASRProvider peut être utilisé partout où un
    ASRProvider est attendu, sans modifier le comportement du programme.
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
    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        """Transcrit des bytes audio en texte.

        Args:
            audio_bytes: Contenu brut du fichier audio.
            file_extension: Extension du fichier source (ogg, mp3, wav, webm).

        Returns:
            Texte transcrit, ou None si la transcription échoue.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} available={self.is_available()}>"
