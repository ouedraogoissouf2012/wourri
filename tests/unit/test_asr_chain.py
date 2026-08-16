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
import contextlib
import pytest
from typing import Optional

from app.services.asr import audio_utils
from app.services.asr.base import ASRProvider
from app.services.asr.chain import ASRChain, AGRI_KEYWORDS
from app.services.validation import lm_filter


# --- Mock providers pour les tests ---

class MockASRProvider(ASRProvider):
    """Provider de test configurable.

    #301 : l'inférence part d'un WAV déjà converti (`transcribe_wav`), la
    conversion étant faite une seule fois en amont par la chaîne.
    """

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

    def transcribe_wav(self, wav_path: str) -> Optional[str]:
        self.call_count += 1
        return self._result


class _FakeLMFilter:
    """Filtre LM déterministe : REJECT si le texte ∈ `reject_texts`, MEDIUM si
    ∈ `medium_texts`, HIGH sinon. Enregistre chaque texte scoré dans `scored`
    (pour vérifier que la chaîne score bien la forme NORMALISÉE). Évite toute
    dépendance à kenlm dans les tests de chaîne."""

    def __init__(self, reject_texts=(), medium_texts=()):
        self._reject = set(reject_texts)
        self._medium = set(medium_texts)
        self.scored = []

    def score(self, text: str) -> lm_filter.LMScore:
        self.scored.append(text)
        if text in self._reject:
            verdict = "REJECT"
        elif text in self._medium:
            verdict = "MEDIUM"
        else:
            verdict = "HIGH"
        return lm_filter.LMScore(
            ppl_norm={"REJECT": 999.0, "MEDIUM": 200.0, "HIGH": 5.0}[verdict],
            oov_ratio=0.0,
            repeat_max=0,
            verdict=verdict,
            logprob=-1.0,
            n_tokens=len(text.split()),
        )


@pytest.fixture(autouse=True)
def stub_conversion(monkeypatch):
    """Neutralise la conversion ffmpeg : la chaîne reçoit un WAV factice.

    `ASRChain.transcribe` convertit via `prepared_wav_16k` (#301). En test on
    remplace ce context manager par un yield d'un chemin bidon — aucune I/O ni
    ffmpeg, on teste uniquement l'orchestration de la chaîne.
    """
    @contextlib.contextmanager
    def fake_prepared(audio_bytes, file_extension, label):
        yield "/tmp/fake_16k.wav"

    monkeypatch.setattr(audio_utils, "prepared_wav_16k", fake_prepared)


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
            def transcribe_wav(self, wav_path):
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


class TestASRChainLMFilter:
    """Filtre LM anti-hallucination (ADR-0029, #94) câblé après normalisation.

    NOTE : le pass-through avec flag OFF (comportement historique préservé) est
    déjà couvert par TOUS les autres tests de ce fichier — ils s'exécutent avec
    la config réelle (ENABLE_LM_RESCORING=False → verdict HIGH → aucun impact).
    Cette classe couvre le comportement quand le filtre est ACTIF.
    """

    @pytest.fixture
    def identity_normalizer(self, monkeypatch):
        """Neutralise la normalisation post-ASR pour isoler la logique LM : le
        texte scoré par le filtre est exactement celui produit par le provider."""
        import app.services.asr.normalizer as nrm
        from app.services import asr_normalizer

        identity = lambda t: t
        monkeypatch.setattr(nrm, "normalize_asr_output", identity)
        monkeypatch.setattr(asr_normalizer, "normalize_asr_output", identity)

    @staticmethod
    def _patch_lm(monkeypatch, reject_texts=(), medium_texts=()):
        fake = _FakeLMFilter(reject_texts, medium_texts)
        monkeypatch.setattr(lm_filter, "get_lm_filter", lambda: fake)
        return fake

    @pytest.mark.asyncio
    async def test_reject_triggers_second_pass_despite_agri_keywords(
        self, monkeypatch, identity_normalizer,
    ):
        """Un verdict REJECT déclenche le 2e passage MÊME quand un mot agricole
        est présent (l'heuristique historique ne l'aurait pas déclenché), et un
        fallback plus naturel (LM != REJECT) est retenu même sans mot agricole."""
        primary = "kaba tigɛ min don"  # 'kaba' agri → heuristique agri inactive
        p1 = MockASRProvider("P1", result=primary)
        fallback = MockASRProvider("Fallback", result="an bɛ taa so")  # pas de mot agri
        self._patch_lm(monkeypatch, reject_texts={primary})  # primary REJECT, fallback HIGH

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "an bɛ taa so"  # fallback retenu car LM ne le rejette plus
        assert fallback.call_count == 1

    @pytest.mark.asyncio
    async def test_active_lm_high_verdict_is_inert(
        self, monkeypatch, identity_normalizer,
    ):
        """Un filtre ACTIF qui rend HIGH ne déclenche aucun 2e passage quand un
        mot agricole est présent (parité avec le comportement pass-through)."""
        primary = "kaba sɛnɛ wagati"
        p1 = MockASRProvider("P1", result=primary)
        fallback = MockASRProvider("Fallback", result="autre chose")
        self._patch_lm(monkeypatch, reject_texts=set())  # tout HIGH

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == primary
        assert fallback.call_count == 0

    @pytest.mark.asyncio
    async def test_reject_without_better_alternative_keeps_original(
        self, monkeypatch, identity_normalizer,
    ):
        """REJECT déclenche le 2e passage, mais si le fallback est lui aussi jugé
        REJECT (et non agricole), aucune alternative n'est meilleure → on garde
        l'original (marqué douteux dans les logs)."""
        primary = "kaba blalala"        # 'kaba' agri présent, mais LM REJECT
        fallback_text = "wolo wolo wolo"  # non agricole
        p1 = MockASRProvider("P1", result=primary)
        fallback = MockASRProvider("Fallback", result=fallback_text)
        self._patch_lm(monkeypatch, reject_texts={primary, fallback_text})

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == primary          # original conservé
        assert fallback.call_count == 1   # 2e passage tenté mais rejeté

    @pytest.mark.asyncio
    async def test_reject_no_retry_when_winner_is_agri_fallback(
        self, monkeypatch, identity_normalizer,
    ):
        """Garde-fou #358 préservé sous le nouveau déclencheur : si le gagnant
        est déjà l'agri_fallback, pas de re-transcription même sous REJECT."""
        dyu = MockASRProvider("MMS-dyu", result="kaba blabla")
        self._patch_lm(monkeypatch, reject_texts={"kaba blabla"})
        chain = ASRChain(providers=[dyu], agri_fallback=dyu)

        result = await chain.transcribe(b"audio", "ogg")

        assert result == "kaba blabla"
        assert dyu.call_count == 1  # une seule transcription, pas de 2e passage

    @pytest.mark.asyncio
    async def test_reject_triggers_second_pass_on_short_non_agri_text(
        self, monkeypatch, identity_normalizer,
    ):
        """CŒUR de #94 : un REJECT sur un texte COURT (<3 mots) et NON agricole —
        que l'heuristique historique ignore doublement (porte ≥3 mots ET porte
        agricole) — déclenche quand même le 2e passage grâce au LM."""
        p1 = MockASRProvider("P1", result="ka ka")  # 2 mots, non agricole
        fallback = MockASRProvider("Fallback", result="malo sɛnɛ")  # agricole
        self._patch_lm(monkeypatch, reject_texts={"ka ka"})

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "malo sɛnɛ"     # le LM a court-circuité les 2 portes
        assert fallback.call_count == 1

    @pytest.mark.asyncio
    async def test_lm_scores_normalized_text_not_raw(self, monkeypatch):
        """Le filtre reçoit la forme NORMALISÉE (exigence ADR "APRÈS
        normalisation"), pas le texte brut du provider. On N'utilise PAS
        identity_normalizer : un vrai normaliseur mute le texte, et on inspecte
        ce que le LM a réellement scoré."""
        import app.services.asr.normalizer as nrm
        from app.services import asr_normalizer

        mute = lambda t: t.replace("kabaa", "kaba")
        monkeypatch.setattr(nrm, "normalize_asr_output", mute)
        monkeypatch.setattr(asr_normalizer, "normalize_asr_output", mute)
        p1 = MockASRProvider("P1", result="kabaa foo barbaz")  # brut (faute)
        fake = self._patch_lm(monkeypatch, reject_texts=set())  # tout HIGH

        chain = ASRChain(providers=[p1])
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "kaba foo barbaz"          # normalisé
        assert fake.scored == ["kaba foo barbaz"]    # le LM a scoré la forme normalisée
        assert "kabaa foo barbaz" not in fake.scored  # jamais le texte brut

    @pytest.mark.asyncio
    async def test_active_high_lm_leaves_heuristic_path_unchanged(
        self, monkeypatch, identity_normalizer,
    ):
        """Parité : avec un LM ACTIF rendant HIGH, le chemin HEURISTIQUE (primary
        non agricole ≥3 mots) fonctionne comme sans LM — 2e passage déclenché par
        l'absence de mot agricole, fallback non-agricole rejeté, original conservé."""
        p1 = MockASRProvider("P1", result="an ni wula min ye")  # non agri, 5 mots
        fallback = MockASRProvider("Fallback", result="texte sans agriculture")
        self._patch_lm(monkeypatch, reject_texts=set())  # tout HIGH

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == "an ni wula min ye"  # heuristique déclenchée, fallback rejeté
        assert fallback.call_count == 1

    @pytest.mark.asyncio
    async def test_medium_verdict_does_not_trigger_second_pass(
        self, monkeypatch, identity_normalizer,
    ):
        """Verrou : seul REJECT déclenche, pas is_suspect. Un verdict MEDIUM sur
        un primary agricole (heuristique inactive) ne déclenche aucun 2e passage."""
        primary = "kaba sɛnɛ wagati"
        p1 = MockASRProvider("P1", result=primary)
        fallback = MockASRProvider("Fallback", result="autre chose")
        self._patch_lm(monkeypatch, medium_texts={primary})  # MEDIUM, pas REJECT

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == primary
        assert fallback.call_count == 0

    @pytest.mark.asyncio
    async def test_reject_with_empty_fallback_keeps_original(
        self, monkeypatch, identity_normalizer,
    ):
        """REJECT déclenche le 2e passage, mais si le fallback retourne None, les
        gardes préservent l'original sans crash (pas de normalize(None))."""
        primary = "ka ka ka"  # non agricole, REJECT
        p1 = MockASRProvider("P1", result=primary)
        fallback = MockASRProvider("Fallback", result=None)
        self._patch_lm(monkeypatch, reject_texts={primary})

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == primary          # original conservé
        assert fallback.call_count == 1   # 2e passage tenté, None ignoré

    @pytest.mark.asyncio
    async def test_reject_accepts_agri_fallback_even_if_lm_rejects_it(
        self, monkeypatch, identity_normalizer,
    ):
        """Précédence : dans _accept_fallback, le critère agricole prime AVANT la
        re-vérification LM. Un fallback agricole ET jugé REJECT par le LM est
        quand même retenu."""
        primary = "fereke fereke fereke"   # non agricole, REJECT
        fallback_text = "kaba sɛnɛ"        # agricole, mais AUSSI REJECT
        p1 = MockASRProvider("P1", result=primary)
        fallback = MockASRProvider("Fallback", result=fallback_text)
        self._patch_lm(monkeypatch, reject_texts={primary, fallback_text})

        chain = ASRChain(providers=[p1], agri_fallback=fallback)
        result = await chain.transcribe(b"audio", "ogg")

        assert result == fallback_text     # agricole prime sur le verdict LM
        assert fallback.call_count == 1
