"""Régressions des traductions validées par le locuteur pour l'issue #32."""

import json
from pathlib import Path

import pytest

from app.services.translation.dictionary_repository import DictionaryRepository
from app.services.translation.interfaces import Direction
from app.services.translation.word_translator import WordTranslator

DICTIONARIES_DIR = Path(__file__).parents[2] / "dictionnaires"

VALIDATED_FRENCH_TO_BAMBARA = (
    ("Bonjour", "i ni sogoma"),
    ("Bonjour (matin)", "i ni sogoma"),
    ("Bonsoir", "i ni wula"),
    ("Bonne nuit", "i ni su"),
    ("Bonjour à tous", "aw ni ce"),
    ("Bonjour à tous (matin)", "aw ni sogoma"),
    ("Merci pour ton travail", "i ni baara"),
    ("Merci", "a ni ce"),
    ("Comment vas-tu ?", "i ka kɛnɛ wa"),
    ("Ça va bien", "here sira"),
    ("Oui", "ɔwɔ"),
    ("Non", "ayi"),
    ("Comment tu t'appelles ?", "i tɔgɔ ye mun ye"),
    ("Bonjour, comment tu t'appelles ?", "ani sɔgɔ ma i tɔgɔ"),
    ("Je veux cultiver du riz", "ne bɛ fɛ ka malo sɛnɛ"),
    ("Je veux cultiver du maïs", "ne bɛ fɛ ka kaba sɛnɛ"),
    ("Je veux cultiver des arachides", "ne bɛ fɛ ka tiga sɛnɛ"),
    ("Est-ce qu'il va pleuvoir ?", "sanji bɛna na wa"),
    ("Je veux de l'aide", "ne bɛ fɛ ka dɛmɛ sɔrɔ"),
    ("Mon champ", "ne ka foro"),
    ("Ma culture", "ne ka sɛnɛfɛn"),
    ("Il fait soleil", "tile bɛ"),
    ("Il pleut", "sanji bɛ na"),
    ("Mon nom est", "ne tɔgɔ ye"),
    ("Je viens de", "ne bɛ bɔ"),
    ("Je peux", "ne bɛ se ka"),
    ("Qu'est-ce que c'est ?", "mun ye"),
    ("Comment ?", "cogo di"),
    ("S'il te plaît", "n'i ko dɛ"),
    ("Au revoir", "k'an bɛn"),
    ("Que Dieu te protège", "ala k'i kisi"),
    ("Je suis agriculteur", "ne ye sɛnɛkɛla ye"),
    ("Je veux faire de l'agriculture", "ne bɛ fɛ ka sɛnɛ kɛ"),
    ("Il y a une maladie sur ma culture", "bana bɛ ne ka sɛnɛfɛn kan"),
    ("Il faut arroser", "jii ka kan"),
    ("Quand est-ce que je peux cultiver ?", "waati jumɛn na ne bɛ se ka sɛnɛ"),
    ("Qu'est-ce qui est bon à cultiver ?", "fɛn jumɛn ka ɲi ka sɛnɛ"),
    ("Je veux cultiver du mil", "ne bɛ fɛ ka ɲɔ sɛnɛ"),
    ("Je veux cultiver un champ", "ne bɛ fɛ ka foro sɛnɛ"),
    ("Je veux arroser", "ne bɛ fɛ ka jii di"),
    ("Comment cultiver du riz", "malo sɛnɛ cogo"),
    ("Comment cultiver du maïs", "kaba sɛnɛ cogo"),
    ("Le sol est bon", "dugukolo ka ɲi"),
    ("Je veux savoir", "ne bɛ fɛ ka dɔn"),
    ("C'est possible", "a bɛ se ka kɛ"),
    ("Ce n'est pas possible", "a tɛ se ka kɛ"),
    ("Je veux cultiver", "ne bɛ fɛ ka sɛnɛ"),
    ("Tu veux cultiver du riz", "i bɛ fɛ ka malo sɛnɛ"),
    ("Tu veux cultiver du maïs", "i bɛ fɛ ka kaba sɛnɛ"),
    ("Nous voulons cultiver", "an bɛ fɛ ka sɛnɛ"),
)


@pytest.fixture(scope="module")
def translator() -> WordTranslator:
    repository = DictionaryRepository(str(DICTIONARIES_DIR))
    return WordTranslator(repository)


@pytest.mark.parametrize(
    ("french", "expected_bambara"),
    VALIDATED_FRENCH_TO_BAMBARA,
)
def test_50_native_validated_phrases_are_canonical_outputs(
    translator: WordTranslator,
    french: str,
    expected_bambara: str,
) -> None:
    result = translator.translate(french, Direction.FR_TO_BAM)

    assert result is not None
    assert result.text == expected_bambara
    assert result.confidence == 1.0


@pytest.mark.parametrize(
    "french",
    (
        "Comment vas-tu ?",
        "Comment tu t'appelles ?",
        "Bonjour, comment tu t'appelles ?",
        "Est-ce qu'il va pleuvoir ?",
        "Qu'est-ce que c'est ?",
        "Comment ?",
        "Quand est-ce que je peux cultiver ?",
        "Qu'est-ce qui est bon à cultiver ?",
    ),
)
def test_trailing_punctuation_uses_the_validated_dictionary_phrase(
    translator: WordTranslator,
    french: str,
) -> None:
    with_punctuation = translator.translate(french, Direction.FR_TO_BAM)
    without_punctuation = translator.translate(
        french.rstrip(" ?"),
        Direction.FR_TO_BAM,
    )

    assert with_punctuation is not None
    assert without_punctuation is not None
    assert with_punctuation.text == without_punctuation.text
    assert with_punctuation.strategy_used == "dictionnaire"


@pytest.mark.parametrize(
    "bambara",
    (
        "i ni ce",
        "a ni ce",
        "ani ce",
        "inice",
        "anice",
        "abarika",
        "i ni baraji",
    ),
)
def test_validated_thanks_forms_translate_to_french(
    translator: WordTranslator,
    bambara: str,
) -> None:
    result = translator.translate(bambara, Direction.BAM_TO_FR)

    assert result is not None
    assert result.text == "Merci"
    assert result.confidence == 1.0


@pytest.mark.parametrize(
    ("french", "expected_bambara"),
    VALIDATED_FRENCH_TO_BAMBARA,
)
def test_tts_services_share_the_validated_exact_translations(
    french: str,
    expected_bambara: str,
) -> None:
    from app.services.tts_bambara import translate_to_bambara
    from app.services.tts_dioula import translate_to_dioula

    assert translate_to_bambara(french) == expected_bambara
    assert translate_to_dioula(french) == expected_bambara


def test_tts_bambara_does_not_treat_thanks_as_hello() -> None:
    from app.services.tts_bambara import translate_to_french

    assert translate_to_french("i ni ce") == "Merci"
    assert translate_to_french("i ni sogoma") == "Bonjour"


@pytest.mark.parametrize(
    ("asr_variant", "expected_french"),
    (
        ("anisɔgɔma", "Bonjour"),
        ("anisɔgɔ ma", "Bonjour"),
        ("anisogoma", "Bonjour"),
        ("anisogo ma", "Bonjour"),
        ("a ni sɔgɔma", "Bonjour"),
        ("a ni sogoma", "Bonjour"),
        ("an ni sɔgɔma", "Bonjour"),
        ("an ni sogoma", "Bonjour"),
        ("anice", "Merci"),
        ("iniwula", "Bonsoir"),
        ("ini wula", "Bonsoir"),
        ("a ni wula", "Bonsoir"),
        ("inisu", "Bonne nuit"),
        ("ini su", "Bonne nuit"),
        ("a ni su", "Bonne nuit"),
        ("inibaara", "Merci pour ton travail"),
        ("ini baara", "Merci pour ton travail"),
    ),
)
def test_existing_asr_greeting_variants_remain_supported(
    asr_variant: str,
    expected_french: str,
) -> None:
    from app.services.tts_bambara import translate_to_french

    assert translate_to_french(asr_variant) == expected_french


def test_phrase_metadata_matches_the_file_content() -> None:
    data = json.loads(
        (DICTIONARIES_DIR / "bambara_phrases.json").read_text(encoding="utf-8")
    )

    assert data["metadata"]["total_phrases"] == len(data["phrases"])
