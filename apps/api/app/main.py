"""Lexoria API entrypoint.

Serves `app.main:app` on port 8000 (uvicorn). The Docker image runs
`alembic upgrade head` before starting this app; `/health` is the liveness
probe proxied by nginx and used by the compose healthcheck.

All business routes are mounted under `/api/v1`; every error is serialized
with the unified envelope: {"error": {"code", "message", "details"}}.
"""
import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    auth,
    daily_sheets,
    encounters,
    inbox,
    reviews,
    senses,
    sources,
    stats,
    user,
    words,
)
from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger("lexoria")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

# Exact-origin allowlist (credentials are allowed, so no wildcard origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)


# --- unified error envelope ------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"loc": ".".join(str(part) for part in err["loc"]), "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "请求参数不合法",
                "details": {"errors": details},
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail) or "请求失败",
                "details": None,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "服务器内部错误",
                "details": None,
            }
        },
    )


# --- routes ----------------------------------------------------------------
@app.get("/health", tags=["meta"], summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"app": settings.app_name, "docs": "/docs"}


_api_router = APIRouter(prefix="/api/v1")
for _module in (
    auth,
    user,
    inbox,
    words,
    senses,
    sources,
    encounters,
    stats,
    reviews,
    daily_sheets,
):
    _api_router.include_router(_module.router)
app.include_router(_api_router)
