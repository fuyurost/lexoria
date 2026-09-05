"""Application errors with a stable machine-readable code, serialized into a
unified JSON envelope by the handlers installed in app.main.

Envelope: {"error": {"code": str, "message": str, "details": object|null}}
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Raise inside services/routers; translated to the HTTP response here."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# --- convenience constructors ---------------------------------------------
def bad_request(code: str, message: str, **kw: Any) -> AppError:
    return AppError(400, code, message, **kw)


def unauthorized(code: str = "unauthorized", message: str = "未登录或登录已过期") -> AppError:
    return AppError(401, code, message)


def forbidden(code: str = "forbidden", message: str = "没有权限执行此操作") -> AppError:
    return AppError(403, code, message)


def not_found(code: str = "not_found", message: str = "请求的资源不存在") -> AppError:
    return AppError(404, code, message)


def conflict(code: str, message: str, **kw: Any) -> AppError:
    return AppError(409, code, message, **kw)


def validation_error(message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(422, "validation_error", message, details=details)
