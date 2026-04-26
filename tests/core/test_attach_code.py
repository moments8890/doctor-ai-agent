"""Tests for the patient attach code generator + normalizer."""
from infra.attach_code import generate_code, normalize, ALPHABET


def test_generate_code_default_length_is_4():
    code = generate_code()
    assert len(code) == 4


def test_generate_code_only_uses_alphabet():
    for _ in range(50):
        code = generate_code()
        assert all(c in ALPHABET for c in code), f"bad char in {code}"


def test_generate_code_custom_length():
    assert len(generate_code(8)) == 8
    assert len(generate_code(6)) == 6


def test_alphabet_excludes_ambiguous_chars():
    for bad in "01OIlo":
        assert bad not in ALPHABET


def test_alphabet_size_is_32():
    assert len(ALPHABET) == 32


def test_normalize_uppercases():
    assert normalize("ab2c") == "AB2C"


def test_normalize_strips_whitespace():
    assert normalize("  AB2C  ") == "AB2C"


def test_normalize_strips_hyphens():
    assert normalize("AB-2C") == "AB2C"
    assert normalize("AB-2-C") == "AB2C"


def test_normalize_handles_empty():
    assert normalize("") == ""
    assert normalize(None) == ""


def test_codes_are_unique_with_high_probability():
    codes = {generate_code() for _ in range(1000)}
    # 1000 samples in a 32^4 = ~1M space — collisions should be < 1%
    assert len(codes) >= 990
