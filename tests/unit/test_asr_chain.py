"""
Tests unitaires pour ASRProvider + ASRChain (issue #44).

Valide :
- ASRProvider ne peut pas être instancié directement (ABC)
- ASRChain essaie les providers dans l'ordre
- ASRChain skip les providers non disponibles
- ASRChain retourne None si tous échouent
- Le filtre agri_fallback fonctionne (second passage si pas de mot agricole)
- Liskov : tout ASRProvider est substituable
"""
import pytest
from typing import Optional
from unittest.mock import AsyncMock

from app.services.asr.base import ASRProvider
from app.services.asr.chain import ASRChain, AGRI_KEYWORDS


# --- Mock providers pour les tests ---

class MockASRProvider(ASRProvider):
    """Provider de test configurable."""

    def __init__(self, provider_name: str, available: bool = True, result: Optional[str] = None):
        self._name = provider_name
        self._available = available
        self._result = result
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    async def transcribe(self, audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
        self.call_count += 1
        return self._result


class TestASRProviderABC:

    def test_cannot_instantiate_directly(self):
        """ASRProvider est abstraite — on ne peut pas l'instancier."""
        with pytest.raises(TypeError):
            ASRProvider()

    def test_mock_provider_is_valid(self):
        """Un MockASRProvider satisfait l'interface."""
        provider = MockASRProvider("test", available=True, result="hello")
        assert provider.name == "test"
        assert provider.is_available()

    def test_repr(self):
        """__repr__ affiche nom et disponibilité."""
        p = MockASRProvider("test", available=True)
        assert "test" in repr(p)
        assert "True" in repr(p)


class TestASRChainBasic:

    @pytest.mark.asyncio
    async def test_first_provider_succeeds(self):
        """Le premier provider qui réussit arrête la chaîne."""
        p1 = MockASRProvider("P1", result="bonjour")
        p2 = MockASRProvider("P2", result="salut")

        chain = ASRChain(providers=[p1, p2])
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "bonjour"
        assert p1.call_count == 1
        assert p2.call_count == 0  # P2 jamais appelé

    @pytest.mark.asyncio
    async def test_fallback_to_second_provider(self):
        """Si le premier échoue, le second est essayé."""
        p1 = MockASRProvider("P1", result=None)
        p2 = MockASRProvider("P2", result="fallback")

        chain = ASRChain(providers=[p1, p2])
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "fallback"
        assert p1.call_count == 1
        assert p2.call_count == 1

    @pytest.mark.asyncio
    async def test_skip_unavailable_provider(self):
        """Les providers non disponibles sont ignorés."""
        p1 = MockASRProvider("P1", available=False, result="should not be called")
        p2 = MockASRProvider("P2", result="available")

        chain = ASRChain(providers=[p1, p2])
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "available"
        assert p1.call_count == 0  # Pas appelé car non disponible
        assert p2.call_count == 1

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Si tous échouent, retourne None."""
        p1 = MockASRProvider("P1", result=None)
        p2 = MockASRProvider("P2", result=None)

        chain = ASRChain(providers=[p1, p2])
        result = await chain.transcribe(b"audio", "ogg")

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_chain(self):
        """Une chaîne vide retourne None."""
        chain = ASRChain(providers=[])
        result = await chain.transcribe(b"audio", "ogg")
        assert result is None

    @pytest.mark.asyncio
    async def test_provider_exception_caught(self):
        """Si un provider lève une exception, la chaîne continue."""
        class CrashProvider(ASRProvider):
            @property
            def name(self): return "Crash"
            def is_available(self): return True
            async def transcribe(self, audio_bytes, ext="ogg"):
                raise RuntimeError("crash!")

        p2 = MockASRProvider("Backup", result="recovered")
        chain = ASRChain(providers=[CrashProvider(), p2])
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "recovered"
        assert p2.call_count == 1


class TestASRChainAgriFallback:

    @pytest.mark.asyncio
    async def test_no_fallback_when_agri_keywords_found(self):
        """Pas de second passage si des mots agricoles sont détectés."""
        p1 = MockASRProvider("P1", result="malo bɛ sɛnɛ wagati jumɛn")
        fallback = MockASRProvider("Fallback", result="other")

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "malo bɛ sɛnɛ wagati jumɛn"
        assert fallback.call_count == 0  # Pas de second passage

    @pytest.mark.asyncio
    async def test_fallback_triggered_when_no_agri_keywords(self):
        """Second passage si aucun mot agricole dans la transcription."""
        p1 = MockASRProvider("P1", result="an ni wula min ye")  # Pas de mot agricole
        fallback = MockASRProvider("Fallback", result="kaba sɛnɛ wagati")  # Mots agricoles

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "kaba sɛnɛ wagati"  # Fallback utilisé
        assert fallback.call_count == 1

    @pytest.mark.asyncio
    async def test_no_second_pass_when_winner_is_the_agri_fallback(self):
        """Pas de re-transcription quand le résultat vient déjà de
        l'agri_fallback (#358 : depuis la réparation de MMS-dyu, il est à la
        fois provider principal effectif et fallback — le re-lancer donnerait
        le même texte pour ~45s de CPU perdues)."""
        dyu = MockASRProvider("MMS-dyu", result="an ni wula min ye")  # pas agricole
        chain = ASRChain(providers=[dyu], agri_fallback=dyu)

        result = await chain.transcribe(b"audio", "ogg")

        assert result == "an ni wula min ye"
        assert dyu.call_count == 1  # UNE seule transcription, pas deux

    @pytest.mark.asyncio
    async def test_fallback_not_triggered_for_short_text(self):
        """Pas de second passage si le texte est trop court (< 3 mots)."""
        p1 = MockASRProvider("P1", result="bon")  # Court, pas de mot agri
        fallback = MockASRProvider("Fallback", result="kaba")

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "bon"  # Pas de fallback (texte trop court)
        assert fallback.call_count == 0

    @pytest.mark.asyncio
    async def test_fallback_result_without_agri_keeps_original(self):
        """Si le fallback ne trouve pas de mot agricole non plus, on garde l'original."""
        p1 = MockASRProvider("P1", result="an ni wula min ye")
        fallback = MockASRProvider("Fallback", result="texte sans agriculture")

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "an ni wula min ye"  # Original conservé
        assert fallback.call_count == 1  # Fallback tenté mais rejeté

    @pytest.mark.asyncio
    async def test_fallback_not_triggered_when_unavailable(self):
        """Si le fallback n'est pas disponible, pas de second passage."""
        p1 = MockASRProvider("P1", result="an ni wula min ye")
        fallback = MockASRProvider("Fallback", available=False, result="kaba")

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "an ni wula min ye"
        assert fallback.call_count == 0


class TestASRChainLiskov:
    """Vérifie que tout ASRProvider peut être substitué dans une chaîne."""

    @pytest.mark.asyncio
    async def test_any_provider_works_in_chain(self):
        """Tout objet ASRProvider est utilisable dans ASRChain."""
        providers = [
            MockASRProvider("A", available=False),
            MockASRProvider("B", result=None),
            MockASRProvider("C", result="transcription finale"),
        ]
        chain = ASRChain(providers=providers)
        result = await chain.transcribe(b"audio", "ogg")
        assert result == "transcription finale"

    def test_providers_list_returns_copy(self):
        """chain.providers retourne une copie (pas de mutation externe)."""
        p1 = MockASRProvider("P1")
        chain = ASRChain(providers=[p1])
        providers = chain.providers
        providers.append(MockASRProvider("P2"))
        assert len(chain.providers) == 1  # Pas modifié


class TestAgriKeywords:

    def test_agri_keywords_is_frozen(self):
        """AGRI_KEYWORDS est un frozenset (immuable)."""
        assert isinstance(AGRI_KEYWORDS, frozenset)

    def test_common_crops_in_keywords(self):
        """Les cultures principales sont dans les mots-clés."""
        for word in ["malo", "kaba", "tiga", "bananku", "mangoro"]:
            assert word in AGRI_KEYWORDS, f"'{word}' manquant"

    def test_has_agri_keywords_positive(self):
        """Détecte un mot agricole dans le texte."""
        assert ASRChain._has_agri_keywords("je veux planter du malo")

    def test_has_agri_keywords_negative(self):
        """Aucun mot agricole détecté."""
        assert not ASRChain._has_agri_keywords("bonjour comment ça va")
