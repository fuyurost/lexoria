"""Auth: register / login / refresh / logout.

- Access tokens travel in `Authorization: Bearer` (JWT, 15 min).
- Refresh tokens are opaque `session_uuid.secret` values set as an HttpOnly
  cookie scoped to /api/v1/auth; only the SHA-256 hash is stored.
- Rotation keeps the SAME session selector (row id) and rewrites the hash in
  one guarded UPDATE (`token_hash == presented`) so a stolen old token cannot
  rotate a second time and two concurrent refreshes cannot both win.
- refresh/logout are cookie-authenticated, so they enforce an Origin check.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.serializers import user_dict
from app.core.config import settings
from app.core.deps import DbDep, check_origin
from app.core.errors import AppError, conflict, unauthorized, validation_error
from app.core.normalization import normalize_email, normalize_username
from app.core.security import (
    constant_time_eq,
    create_access_token,
    hash_password,
    new_refresh_token,
    parse_refresh_token,
    rotate_refresh_token,
    sha256_hex,
    verify_password,
)
from app.models.user import RefreshSession, User, UserSetting

router = APIRouter(prefix="/auth", tags=["auth"])

_USERNAME_RE = re.compile(r"^[a-z0-9._-]+$")
_COOKIE_PATH = "/api/v1/auth"  # refresh cookie only rides auth requests


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue_refresh(db: DbDep, user: User) -> tuple[str, RefreshSession]:
    token, session_id, token_hash = new_refresh_token()
    session = RefreshSession(
        id=uuid.UUID(session_id),
        user_id=user.id,
        token_hash=token_hash,
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    return token, session


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: DbDep) -> dict:
    if not settings.allow_registration:
        raise AppError(403, "registration_disabled", "当前不允许注册新账号")

    raw = body.username
    if raw != raw.strip():
        raise validation_error("用户名首尾不能有空格", {"field": "username"})
    username = normalize_username(raw)
    if not username or not _USERNAME_RE.match(username):
        raise validation_error(
            "用户名只能包含字母、数字、点、下划线与连字符", {"field": "username"}
        )
    try:
        valid = validate_email(body.email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise validation_error("邮箱地址格式不正确", {"field": "email"}) from exc
    email = body.email.strip()
    email_normalized = normalize_email(valid.normalized)

    user = User(
        username=raw.strip(),  # display keeps the user's casing
        username_normalized=username,
        email=email,
        email_normalized=email_normalized,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if name == "uq_users_email_normalized":
            raise conflict("duplicate_email", "该邮箱已被注册") from exc
        if name == "uq_users_username_normalized":
            raise conflict("duplicate_username", "该用户名已被注册") from exc
        raise conflict("duplicate", "账号已存在") from exc
    db.add(UserSetting(user_id=user.id))
    db.commit()
    return user_dict(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: DbDep) -> dict:
    identifier = body.identifier.strip()
    if "@" in identifier:
        key = normalize_email(identifier)
        user = db.execute(
            select(User).where(User.email_normalized == key)
        ).scalar_one_or_none()
    else:
        key = normalize_username(identifier)
        user = db.execute(
            select(User).where(User.username_normalized == key)
        ).scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise unauthorized(code="invalid_credentials", message="账号或密码不正确")
    if not user.is_active:
        raise unauthorized(code="account_disabled", message="账号已被停用")

    token, _session = _issue_refresh(db, user)
    db.commit()
    _set_refresh_cookie(response, token)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": user_dict(user),
    }


@router.post("/refresh")
def refresh(request: Request, response: Response, db: DbDep) -> dict:
    check_origin(request)
    cookie = request.cookies.get(settings.refresh_cookie_name)
    parsed = parse_refresh_token(cookie) if cookie else None
    if parsed is None:
        raise unauthorized(code="refresh_invalid", message="刷新凭证无效")
    session_id, secret = parsed

    session = db.get(RefreshSession, uuid.UUID(session_id))
    now = _now()
    presented = sha256_hex(f"{session_id}.{secret}")
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or not constant_time_eq(presented, session.token_hash)
    ):
        raise unauthorized(code="refresh_invalid", message="刷新凭证无效或已过期")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise unauthorized(code="account_disabled", message="账号已被停用")

    # Atomic rotation on the SAME row (selector never changes): the WHERE also
    # pins token_hash to the presented token, so two concurrent refreshes with
    # the same old token cannot both win — the loser gets rowcount 0 -> 401.
    new_token, new_hash = rotate_refresh_token(session.id)
    result = db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == session.id,
            RefreshSession.token_hash == presented,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .values(
            token_hash=new_hash,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise unauthorized(code="refresh_invalid", message="刷新凭证无效或已过期")
    db.commit()

    _set_refresh_cookie(response, new_token)
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.post("/logout")
def logout(request: Request, response: Response, db: DbDep) -> Response:
    check_origin(request)
    cookie = request.cookies.get(settings.refresh_cookie_name)
    parsed = parse_refresh_token(cookie) if cookie else None
    if parsed is not None:
        session_id, _secret = parsed
        session = db.get(RefreshSession, uuid.UUID(session_id))
        if session is not None and session.revoked_at is None:
            db.execute(
                update(RefreshSession)
                .where(RefreshSession.id == session.id)
                .values(revoked_at=_now())
            )
            db.commit()
    _clear_refresh_cookie(response)
    # Clear the cookie on THIS response (a fresh Response would drop it).
    response.status_code = 204
    return response
