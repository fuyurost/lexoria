"""Pure tests for app/core/security (no DB, no network)."""
import uuid

import pytest

from app.core.config import settings
from app.core.security import (
    constant_time_eq,
    create_access_token,
    decode_access_token,
    hash_password,
    new_refresh_token,
    parse_refresh_token,
    sha256_hex,
    verify_password,
)
from app.core.errors import AppError


def test_password_hash_argon2id_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("correct horse battery staple", "not-a-hash")


def test_password_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_constant_time_eq():
    assert constant_time_eq("abc", "abc")
    assert not constant_time_eq("abc", "abd")
    assert not constant_time_eq("", "a")


def test_sha256_hex_stable():
    assert sha256_hex("x") == sha256_hex("x")
    assert len(sha256_hex("x")) == 64


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    claims = decode_access_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["type"] == "access"


def test_access_token_rejects_wrong_secret():
    token = create_access_token(uuid.uuid4())
    original = settings.jwt_secret
    try:
        settings.jwt_secret = "other-secret"
        with pytest.raises(AppError) as excinfo:
            decode_access_token(token)
        assert excinfo.value.code in ("token_invalid", "token_expired")
    finally:
        settings.jwt_secret = original


def test_refresh_token_format_and_hash():
    token, session_id, token_hash = new_refresh_token()
    parsed_session, parsed_secret = parse_refresh_token(token)
    assert parsed_session == session_id
    assert parsed_secret
    assert token == f"{session_id}.{parsed_secret}"
    assert token_hash == sha256_hex(token)


def test_parse_refresh_token_rejects_malformed():
    assert parse_refresh_token("") is None
    assert parse_refresh_token("no-dot-here") is None
    assert parse_refresh_token("not-a-uuid.secret") is None
    assert parse_refresh_token(f"{uuid.uuid4()}.") is None
