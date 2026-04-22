"""Tests de anonymize_user_id (app/core/pii_utils.py)."""
import string

from app.core.pii_utils import anonymize_user_id


def test_empty_string_returns_anon():
    assert anonymize_user_id("") == "usr_anon"


def test_none_returns_anon():
    assert anonymize_user_id(None) == "usr_anon"


def test_same_input_same_output():
    """Déterminisme : vital pour corrélation logs support client."""
    u = "22544210112"
    assert anonymize_user_id(u) == anonymize_user_id(u)


def test_different_input_different_output():
    assert anonymize_user_id("22544210112") != anonymize_user_id("22544210113")


def test_output_format_prefix():
    result = anonymize_user_id("22544210112")
    assert result.startswith("usr_")


def test_output_format_length():
    # 'usr_' (4) + 16 chars hex = 20 chars
    result = anonymize_user_id("22544210112")
    assert len(result) == 20


def test_output_hexadecimal():
    result = anonymize_user_id("22544210112")
    hash_part = result[4:]
    assert all(c in string.hexdigits for c in hash_part)


def test_different_numbers_no_collision_sample():
    """Petit échantillon : 100 numéros distincts → 100 hashes distincts."""
    hashes = {anonymize_user_id(f"2254421{i:04d}") for i in range(100)}
    assert len(hashes) == 100


def test_handles_non_ascii_user_ids():
    """Robustesse : user_ids avec caractères unicode (ex: tests édge)."""
    result = anonymize_user_id("usér_tëst_😀")
    assert result.startswith("usr_")
    assert len(result) == 20
