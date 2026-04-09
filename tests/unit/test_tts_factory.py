"""
Tests unitaires pour TTSProvider + TTSFactory (issue #45).

Valide :
- TTSProvider ne peut pas être instancié (ABC)
- TTSFactory résout les codes et alias
- TTSFactory cache LRU (max 3 providers, éviction du plus ancien)
- Liskov : tout TTSProvider est substituable
- IvorianTTSProvider refuse les codes invalides
"""
import pytest
from typing import Optional
from collections import OrderedDict

from app.services.tts.base import TTSProvider
from app.services.tts.factory import TTSFactory


# --- Mock provider ---

class MockTTSProvider(TTSProvider):
    """Provider de test."""

    def __init__(self, code: str, name: str, available: bool = True):
        self._code = code
        self._name = name
        self._available = available

    @property
    def language_code(self) -> str:
        return self._code

    @property
    def language_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    def synthesize(self, text: str) -> Optional[str]:
        return f"/static/audio/mock_{self._code}.ogg"


class TestTTSProviderABC:

    def test_cannot_instantiate_directly(self):
        """TTSProvider est abstraite."""
        with pytest.raises(TypeError):
            TTSProvider()

    def test_mock_provider_is_valid(self):
        """Un MockTTSProvider satisfait l'interface."""
        p = MockTTSProvider("bam", "Bambara")
        assert p.language_code == "bam"
        assert p.language_name == "Bambara"
        assert p.is_available()
        assert p.synthesize("test") is not None

    def test_repr(self):
        """__repr__ affiche code et disponibilité."""
        p = MockTTSProvider("bam", "Bambara")
        assert "bam" in repr(p)


class TestTTSFactory:

    def setup_method(self):
        """Factory fraîche pour chaque test."""
        self.factory = TTSFactory(max_cached=3)

    def test_get_provider_bambara(self):
        """get_provider('bam') retourne un BambaraTTSProvider."""
        p = self.factory.get_provider("bam")
        assert p is not None
        assert p.language_code == "bam"

    def test_get_provider_dioula(self):
        """get_provider('dyu') retourne un DioulaTTSProvider."""
        p = self.factory.get_provider("dyu")
        assert p is not None
        assert p.language_code == "dyu"

    def test_get_provider_french(self):
        """get_provider('fra') retourne un FrenchTTSProvider."""
        p = self.factory.get_provider("fra")
        assert p is not None
        assert p.language_code == "fra"

    def test_get_provider_ivorian(self):
        """get_provider('ati') retourne un IvorianTTSProvider pour Attié."""
        p = self.factory.get_provider("ati")
        assert p is not None
        assert p.language_code == "ati"

    def test_alias_resolution_dioula(self):
        """L'alias 'dioula' résout vers 'bam'."""
        p = self.factory.get_provider("dioula")
        assert p is not None
        assert p.language_code == "bam"

    def test_alias_resolution_bambara(self):
        """L'alias 'bambara' résout vers 'bam'."""
        p = self.factory.get_provider("bambara")
        assert p is not None
        assert p.language_code == "bam"

    def test_alias_resolution_french(self):
        """'french' résout vers 'fra'."""
        p = self.factory.get_provider("french")
        assert p is not None
        assert p.language_code == "fra"

    def test_unknown_language_returns_none(self):
        """Une langue inconnue retourne None."""
        p = self.factory.get_provider("klingon")
        assert p is None

    def test_case_insensitive(self):
        """La résolution est insensible à la casse."""
        p = self.factory.get_provider("BAM")
        assert p is not None
        assert p.language_code == "bam"

    def test_cache_returns_same_instance(self):
        """Deux appels avec le même code retournent la même instance."""
        p1 = self.factory.get_provider("bam")
        p2 = self.factory.get_provider("bam")
        assert p1 is p2


class TestTTSFactoryLRU:

    def test_lru_eviction(self):
        """Au-delà de max_cached, le plus ancien provider est évincé."""
        factory = TTSFactory(max_cached=2)

        factory.get_provider("bam")
        factory.get_provider("fra")
        assert len(factory.list_cached()) == 2

        # Ajouter un 3ème → évince bam (le plus ancien)
        factory.get_provider("ati")
        cached = factory.list_cached()
        assert len(cached) == 2
        assert "bam" not in cached
        assert "fra" in cached
        assert "ati" in cached

    def test_lru_access_refreshes(self):
        """Accéder à un provider le déplace en fin (pas évincé)."""
        factory = TTSFactory(max_cached=2)

        factory.get_provider("bam")
        factory.get_provider("fra")

        # Ré-accéder à bam → il passe en fin
        factory.get_provider("bam")

        # Ajouter ati → évince fra (pas bam car rafraîchi)
        factory.get_provider("ati")
        cached = factory.list_cached()
        assert "bam" in cached
        assert "fra" not in cached
        assert "ati" in cached

    def test_list_cached_empty_initially(self):
        """Le cache est vide au départ."""
        factory = TTSFactory()
        assert factory.list_cached() == []


class TestTTSProviderLiskov:
    """Vérifie que tout TTSProvider est substituable."""

    def test_all_providers_have_same_interface(self):
        """Tous les providers concrets implémentent les mêmes méthodes."""
        factory = TTSFactory()
        codes = ["bam", "dyu", "fra", "ati"]

        for code in codes:
            p = factory.get_provider(code)
            assert p is not None, f"Provider pour '{code}' est None"
            assert hasattr(p, "language_code")
            assert hasattr(p, "language_name")
            assert hasattr(p, "is_available")
            assert hasattr(p, "synthesize")
            assert isinstance(p.language_code, str)
            assert isinstance(p.language_name, str)
            assert isinstance(p.is_available(), bool)

    def test_ivorian_provider_rejects_invalid_code(self):
        """IvorianTTSProvider lève ValueError pour un code invalide."""
        from app.services.tts.ivorian_provider import IvorianTTSProvider
        with pytest.raises(ValueError):
            IvorianTTSProvider("invalid")
