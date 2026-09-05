"""Shared FastAPI dependencies: current-user resolution and origin checks."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import forbidden, unauthorized
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)

DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbDep,
) -> User:
    """Resolve the authenticated user from a verified access token."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise unauthorized()
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, TypeError, KeyError):
        raise unauthorized(code="token_invalid", message="登录凭证无效") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def check_origin(request: Request) -> None:
    """CSRF guard for cookie-authenticated endpoints (refresh/logout).

    A present Origin must be in the exact allowlist. Absent Origins (curl,
    tests, same-origin GET-style navigation) are accepted unless
    ``auth_origin_required`` demands one.
    """
    origin = request.headers.get("origin")
    if origin is None:
        if settings.auth_origin_required:
            raise forbidden(code="origin_required", message="缺少 Origin 头")
        return
    if origin not in settings.allowed_origin_list:
        raise forbidden(code="origin_denied", message="请求来源不被允许")
