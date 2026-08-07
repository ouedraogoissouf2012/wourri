"""
Tests unitaires pour app/data/constants.py (issue #46).

Valide :
- IVORIAN_CITY_NAMES contient les 60 villes
- SUPPORTED_LANGUAGES contient les 8 langues avec tous les champs requis
- LANGUAGE_ALIASES résout correctement vers les codes
- get_asr_languages() retourne le format (display_name, iso_code)
- get_tts_languages() retourne le format (display_name, tts_model, nllb_code)
- resolve_language_alias() résout alias, codes directs, et retourne None pour inconnus
- Cohérence entre constants.py, tts_ivoirian, schemas
"""
import pytest

from app.data.constants import (
    IVORIAN_CITY_NAMES,
    SUPPORTED_LANGUAGES,
    LANGUAGE_ALIASES,
    get_asr_languages,
    get_tts_languages,
    resolve_language_alias,
)


class TestIvorianCities:

    def test_city_count(self):
        """Au moins 59 villes dans la liste (source: cities.py)."""
        assert len(IVORIAN_CITY_NAMES) >= 59

    def test_major_cities_present(self):
        """Les grandes villes CI sont présentes."""
        for city in ["Abidjan", "Bouake", "Korhogo", "Yamoussoukro", "Daloa", "Man"]:
            assert city in IVORIAN_CITY_NAMES, f"{city} manquant"

    def test_sorted(self):
        """La liste est triée alphabétiquement."""
        assert IVORIAN_CITY_NAMES == sorted(IVORIAN_CITY_NAMES)

    def test_no_duplicates(self):
        """Aucun doublon."""
        assert len(IVORIAN_CITY_NAMES) == len(set(IVORIAN_CITY_NAMES))

    def test_all_strings(self):
        """Toutes les entrées sont des strings non vides."""
        for city in IVORIAN_CITY_NAMES:
            assert isinstance(city, str) and len(city) > 0


class TestSupportedLanguages:

    def test_language_count(self):
        """8 langues supportées."""
        assert len(SUPPORTED_LANGUAGES) == 8

    def test_required_fields(self):
        """Chaque langue a les 4 champs requis."""
        required = {"display_name", "iso_code", "tts_model", "nllb_code"}
        for code, lang in SUPPORTED_LANGUAGES.items():
            assert required.issubset(lang.keys()), f"{code} manque: {required - lang.keys()}"

    def test_bambara_present(self):
        """Le bambara (bam) est la langue principale."""
        assert "bam" in SUPPORTED_LANGUAGES
        bam = SUPPORTED_LANGUAGES["bam"]
        assert bam["display_name"] == "Bambara/Dioula"
        assert bam["nllb_code"] == "bam_Latn"
        assert "mms-tts-bam" in bam["tts_model"]

    def test_all_codes_are_3_chars(self):
        """Tous les codes langue font 3 caractères (ISO 639-3)."""
        for code in SUPPORTED_LANGUAGES:
            assert len(code) == 3, f"Code '{code}' n'est pas ISO 639-3"

    def test_only_bambara_has_nllb(self):
        """Seul le bambara a un code NLLB (traduction disponible)."""
        with_nllb = [c for c, l in SUPPORTED_LANGUAGES.items() if l["nllb_code"]]
        assert with_nllb == ["bam"]


class TestLanguageAliases:

    def test_dioula_resolves_to_bam(self):
        """'dioula' et 'bambara' résolvent vers 'bam'."""
        assert LANGUAGE_ALIASES["dioula"] == "bam"
        assert LANGUAGE_ALIASES["bambara"] == "bam"
        assert LANGUAGE_ALIASES["jula"] == "bam"

    def test_all_aliases_resolve_to_valid_codes(self):
        """Tous les alias pointent vers un code qui existe dans SUPPORTED_LANGUAGES."""
        for alias, code in LANGUAGE_ALIASES.items():
            assert code in SUPPORTED_LANGUAGES, f"Alias '{alias}' → '{code}' inconnu"


class TestHelpers:

    def test_get_asr_languages_format(self):
        """get_asr_languages() retourne {code: (display_name, iso_code)}."""
        result = get_asr_languages()
        assert len(result) == 8
        for code, (name, iso) in result.items():
            assert isinstance(name, str) and len(name) > 0
            assert isinstance(iso, str) and len(iso) == 3

    def test_get_tts_languages_format(self):
        """get_tts_languages() retourne {code: (display_name, tts_model, nllb_code)}."""
        result = get_tts_languages()
        assert len(result) == 8
        for code, (name, model, nllb) in result.items():
            assert isinstance(name, str)
            assert "facebook/mms-tts-" in model
            assert nllb is None or isinstance(nllb, str)

    def test_resolve_language_alias_direct_code(self):
        """resolve_language_alias() accepte un code direct."""
        assert resolve_language_alias("bam") == "bam"
        assert resolve_language_alias("dnj") == "dnj"

    def test_resolve_language_alias_alias(self):
        """resolve_language_alias() résout un alias."""
        assert resolve_language_alias("dioula") == "bam"
        assert resolve_language_alias("yacouba") == "dnj"

    def test_resolve_language_alias_case_insensitive(self):
        """resolve_language_alias() est insensible à la casse."""
        assert resolve_language_alias("DIOULA") == "bam"
        assert resolve_language_alias("Bambara") == "bam"

    def test_resolve_language_alias_unknown(self):
        """resolve_language_alias() retourne None pour un alias inconnu."""
        assert resolve_language_alias("klingon") is None
        assert resolve_language_alias("") is None


class TestConsistency:
    """Vérifie que les services utilisent bien constants.py."""

    def test_tts_languages_match_constants(self):
        """tts_ivoirian.IVORIAN_LANGUAGES == get_tts_languages()."""
        from app.services.tts_ivoirian import IVORIAN_LANGUAGES
        expected = get_tts_languages()
        assert IVORIAN_LANGUAGES == expected

    def test_schemas_enum_matches_constants(self):
        """IvorianLanguage enum values match SUPPORTED_LANGUAGES keys."""
        from app.models.schemas import IvorianLanguage
        enum_values = {member.value for member in IvorianLanguage}
        constant_codes = set(SUPPORTED_LANGUAGES.keys())
        assert enum_values == constant_codes
