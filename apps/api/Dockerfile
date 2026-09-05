# syntax=docker/dockerfile:1

# Lexoria API — FastAPI (app.main:app, port 8000), Python 3.12, uv.
# Debian slim (NOT Alpine): WeasyPrint needs native Pango/cairo libs, and CJK
# PDF output needs Noto Sans CJK SC (fonts-noto-cjk).

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

# uv binary from the official image. Pin the tag for reproducibility.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# WeasyPrint system libraries (Debian bookworm) + Noto Sans CJK SC fonts
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        libjpeg62-turbo \
        libopenjp2-7 \
        libxml2 \
        libffi8 \
        libssl3 \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for layer caching (requires uv.lock committed).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# App source (junk excluded via .dockerignore)
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Non-root runtime user + private PDF storage dir (matches compose volume target)
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data/pdfs && chown app:app /data/pdfs

# Runtime uv cache must be writable by the non-root app user (/app is root-owned).
ENV UV_CACHE_DIR=/tmp/uv-cache

USER app
EXPOSE 8000

# Migrate, then serve. Requires DATABASE_URL (see docker-compose.yml).
# `--proxy-headers` lets uvicorn honor X-Forwarded-* set by nginx.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
