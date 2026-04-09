"""
WOURI - Interface TTS (Liskov Substitution Principle).

Toute implémentation TTS doit hériter de TTSProvider.
Permet de substituer bambara, dioula, french ou ivoirien sans modifier le code appelant.
"""
from abc import ABC, abstractmethod
from typing import Optional


class TTSProvider(ABC):
    """Interface commune pour tous les services de synthèse vocale.

    Contrat Liskov : tout TTSProvider peut être utilisé partout où un
    TTSProvider est attendu, sans modifier le comportement du programme.
    """

    @property
    @abstractmethod
    def language_code(self) -> str:
        """Code ISO de la langue (bam, dyu, fra, ati...)."""
        ...

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Nom lisible de la langue (Bambara, Dioula, Français...)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Retourne True si le provider est utilisable."""
        ...

    @abstractmethod
    def synthesize(self, text: str) -> Optional[str]:
        """Synthétise du texte en audio.

        Args:
            text: Texte dans la langue du provider.

        Returns:
            URL relative vers le fichier audio (ex: /static/audio/xxx.ogg),
            ou None si la synthèse échoue.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} lang={self.language_code!r} available={self.is_available()}>"
