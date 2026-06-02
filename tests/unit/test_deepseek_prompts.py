"""
Tests pour `app/services/deepseek_prompts.py` (ADR-0015 PR 3/4).

Couvre :
    - Registres SYSTEM_PROMPTS et DEEPSEEK_PARAMS contiennent les 3 langues
      actuelles (FRENCH, DIOULA, BOTH)
    - Les prompts sont non vides et contiennent les marqueurs critiques
    - Les params ont les cles `max_tokens` et `temperature`
    - `get_deepseek_params` retourne defaults sur langue inconnue (defense
      en profondeur)
    - Mode BOTH reutilise le prompt DIOULA (compatibilite historique)

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #278 (PR 3/4)
"""
from __future__ import annotations

import pytest

from app.models.schemas import Language
from app.services.deepseek_prompts import (
    DEEPSEEK_PARAMS,
    DIOULA_PROMPT,
    FRENCH_PROMPT,
    SYSTEM_PROMPTS,
    get_deepseek_params,
)


# ─────────────────────────────────────────────
# SYSTEM_PROMPTS registry
# ─────────────────────────────────────────────


class TestSystemPromptsRegistry:
    """Verifie le registre des system prompts."""

    def test_contains_all_current_languages(self):
        """FRENCH + DIOULA + BOTH doivent etre enregistres."""
        assert Language.FRENCH in SYSTEM_PROMPTS
        assert Language.DIOULA in SYSTEM_PROMPTS
        assert Language.BOTH in SYSTEM_PROMPTS

    def test_all_prompts_are_non_empty_strings(self):
        for lang, prompt in SYSTEM_PROMPTS.items():
            assert isinstance(prompt, str), f"Prompt {lang} doit etre str"
            assert len(prompt.strip()) > 100, f"Prompt {lang} suspect court"

    def test_french_prompt_contains_marker(self):
        """Le prompt FR doit mentionner 'français' explicitement."""
        assert "français" in SYSTEM_PROMPTS[Language.FRENCH].lower()

    def test_dioula_prompt_contains_role_marker(self):
        """Le prompt DIOULA doit definir le role Wourri."""
        assert "Wourri" in SYSTEM_PROMPTS[Language.DIOULA]
        assert "PHRASES" in SYSTEM_PROMPTS[Language.DIOULA]

    def test_both_uses_dioula_prompt(self):
        """Mode BOTH reutilise le prompt DIOULA (texte FR simple traduisible)."""
        assert SYSTEM_PROMPTS[Language.BOTH] is SYSTEM_PROMPTS[Language.DIOULA]

    def test_french_dioula_prompts_are_distinct(self):
        assert SYSTEM_PROMPTS[Language.FRENCH] is not SYSTEM_PROMPTS[Language.DIOULA]

    def test_constants_match_registry(self):
        """Les constantes FRENCH_PROMPT et DIOULA_PROMPT doivent etre les memes
        objets que ceux enregistres (pas de copie cachee)."""
        assert SYSTEM_PROMPTS[Language.FRENCH] is FRENCH_PROMPT
        assert SYSTEM_PROMPTS[Language.DIOULA] is DIOULA_PROMPT


# ─────────────────────────────────────────────
# DEEPSEEK_PARAMS registry
# ─────────────────────────────────────────────


class TestDeepseekParamsRegistry:
    """Verifie le registre des parametres d'inference."""

    def test_contains_all_current_languages(self):
        assert Language.FRENCH in DEEPSEEK_PARAMS
        assert Language.DIOULA in DEEPSEEK_PARAMS
        assert Language.BOTH in DEEPSEEK_PARAMS

    @pytest.mark.parametrize("lang", [Language.FRENCH, Language.DIOULA, Language.BOTH])
    def test_params_have_required_keys(self, lang):
        params = DEEPSEEK_PARAMS[lang]
        assert "max_tokens" in params
        assert "temperature" in params

    @pytest.mark.parametrize("lang", [Language.FRENCH, Language.DIOULA, Language.BOTH])
    def test_params_are_sensible(self, lang):
        params = DEEPSEEK_PARAMS[lang]
        # Bornes raisonnables
        assert 1 <= params["max_tokens"] <= 1000
        assert 0.0 <= params["temperature"] <= 2.0

    def test_french_has_more_tokens_than_dioula(self):
        """FR : 200 tokens (4-5 phrases detaillees) > DIOULA : 150 tokens
        (3-5 phrases traduisibles)."""
        assert (
            DEEPSEEK_PARAMS[Language.FRENCH]["max_tokens"]
            > DEEPSEEK_PARAMS[Language.DIOULA]["max_tokens"]
        )

    def test_both_matches_dioula_params(self):
        """Mode BOTH doit avoir les memes parametres que DIOULA
        (reponse FR simple traduisible)."""
        assert (
            DEEPSEEK_PARAMS[Language.BOTH]["max_tokens"]
            == DEEPSEEK_PARAMS[Language.DIOULA]["max_tokens"]
        )
        assert (
            DEEPSEEK_PARAMS[Language.BOTH]["temperature"]
            == DEEPSEEK_PARAMS[Language.DIOULA]["temperature"]
        )


# ─────────────────────────────────────────────
# get_deepseek_params helper
# ─────────────────────────────────────────────


class TestGetDeepseekParams:
    """Verifie le helper get_deepseek_params avec fallback defaults."""

    @pytest.mark.parametrize("lang", [Language.FRENCH, Language.DIOULA, Language.BOTH])
    def test_returns_registered_params(self, lang):
        result = get_deepseek_params(lang)
        assert result == DEEPSEEK_PARAMS[lang]

    def test_fallback_on_unknown_language(self):
        """Si une langue n'est pas enregistree (cas defense en profondeur),
        retourne des defaults raisonnables au lieu de KeyError."""
        # On utilise un sentinel non-Language pour simuler l'absence
        # (Language est une Enum donc tout member existant est dans le dict
        # — on triche en passant un faux objet pour exercer le fallback)
        class FakeLanguage:
            value = "klingon"

        result = get_deepseek_params(FakeLanguage())
        assert "max_tokens" in result
        assert "temperature" in result
        assert isinstance(result["max_tokens"], int)
        assert isinstance(result["temperature"], float)
