"""Pure tests for app/core/normalization."""
from app.core.normalization import (
    normalize_email,
    normalize_identifier,
    normalize_lemma,
    normalize_source_name,
    normalize_username,
    to_iso,
    utcnow,
)


def test_normalize_username_trims_and_casefolds():
    assert normalize_username("  Alice  ") == "alice"
    assert normalize_username("ALICE") == "alice"
    # Internal whitespace is PRESERVED (register's character-set check then
    # rejects it) — never silently removed or collapsed.
    assert normalize_username("A  LICE") == "a  lice"
    assert normalize_username("  ") == ""


def test_normalize_email_casefold_and_trim():
    assert normalize_email("  User@Example.COM ") == "user@example.com"


def test_normalize_lemma_collapses_whitespace_and_casefolds():
    assert normalize_lemma("  Ice   Cream ") == "ice cream"
    assert normalize_lemma("DON'T") == "don't"


def test_normalize_source_name():
    assert normalize_source_name("  New   Concept  ") == "new concept"


def test_normalize_identifier():
    assert normalize_identifier("  SomeUser ") == "someuser"
    assert normalize_identifier("  USER@Example.COM ") == "user@example.com"


def test_to_iso_formats_utc_aware():
    assert to_iso(None) is None
    assert to_iso(utcnow()).endswith("Z")


def test_utcnow_is_timezone_aware_utc():
    now = utcnow()
    assert now.utcoffset().total_seconds() == 0


def test_clean_surface_curly_and_unicode_whitespace():
    from app.core.normalization import clean_surface

    # Curly apostrophes become straight; the left double quote is kept; the
    # U+2003 em space collapses into a single regular space.
    assert clean_surface("\u201cCan\u2019t\u2003stop\u2019") == "\u201cCan't stop'"
    assert clean_surface("\u3000 padded \u00a0 ") == "padded"


def test_clean_surface_nfkc_fullwidth():
    from app.core.normalization import clean_surface

    assert clean_surface("\uff28ello") == "Hello"  # NFKC: full-width H -> H


def test_clean_surface_rejects_control_and_oversize():
    import pytest

    from app.core.normalization import clean_surface

    with pytest.raises(ValueError):
        clean_surface("bad\x00text")
    with pytest.raises(ValueError):
        clean_surface("x" * 201)
    with pytest.raises(ValueError):
        clean_surface("   ")


def test_normalize_lemma_nfkc_casefold():
    assert normalize_lemma("\uff29ce Cream") == "ice cream"
