"""Auth primitives: Argon2id password hashing, JWT access tokens, opaque
refresh tokens (session_uuid.secret — only the SHA-256 hash is persisted).

Pure helpers are import-light so unit tests can exercise them standalone.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import unauthorized

_ph = PasswordHasher()  # argon2-cffi defaults: Argon2id, t=3, m=64MiB, p=4


# --- passwords (Argon2id) --------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification via argon2-cffi; never raises."""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


# --- generic constant-time compare / digests -------------------------------
def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --- JWT access tokens ------------------------------------------------------
def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Returns verified claims or raises a 401 AppError."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized(code="token_expired", message="登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized(code="token_invalid", message="登录凭证无效") from exc
    if claims.get("type") != "access":
        raise unauthorized(code="token_invalid", message="登录凭证无效")
    return claims


# --- opaque refresh tokens --------------------------------------------------
def new_refresh_token() -> tuple[str, str, str]:
    """Returns (opaque_token, session_uuid_str, token_hash_hex).

    Token wire format: ``<session-uuid>.<urlsafe-secret>``. Only the SHA-256
    hash of the full token is stored in refresh_sessions.token_hash.
    """
    session_uuid = uuid.uuid4()
    secret = secrets.token_urlsafe(48)
    token = f"{session_uuid}.{secret}"
    return token, str(session_uuid), sha256_hex(token)


def parse_refresh_token(token: str) -> tuple[str, str] | None:
    """Split an opaque token into (session_uuid_str, secret); None if malformed."""
    if "." not in token:
        return None
    session_part, secret = token.split(".", 1)
    if not secret:
        return None
    try:
        parsed = uuid.UUID(session_part)
    except (ValueError, AttributeError):
        return None
    if str(parsed) != session_part.lower():
        return None
    return session_part, secret


def rotate_refresh_token(session_uuid: uuid.UUID) -> tuple[str, str]:
    """New opaque token for an EXISTING session row.

    The selector (session id) MUST stay stable — it is the lookup key of the
    stored row — so only the secret half is regenerated. Returns
    (token, token_hash_hex) with token format ``<session-uuid>.<new-secret>``.
    """
    secret = secrets.token_urlsafe(48)
    token = f"{session_uuid}.{secret}"
    return token, sha256_hex(token)
