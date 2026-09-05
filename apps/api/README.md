# Lexoria API (apps/api)

FastAPI backend: Python 3.12, uv, SQLAlchemy 2 (sync, psycopg v3), Alembic,
Postgres 16. Entrypoint `app.main:app` on port 8000.

## Layout

- `app/main.py` — FastAPI app, CORS allowlist, unified error envelope,
  `/api/v1/*` router wiring and `/health`.
- `app/core/` — `config.py` (env settings), `security.py` (Argon2id, JWT,
  opaque refresh tokens), `errors.py`, `normalization.py` (pure text/ts
  helpers), `deps.py` (auth + origin-check dependencies).
- `app/db/` — declarative base + naming convention, engine/session.
- `app/models/` — SQLAlchemy models (`user`, `word`, `review`, `sheet`).
- `app/api/` — routers: auth, user (me/settings), inbox (capture), words,
  senses, sources, encounters, stats. Reviews / daily-sheets land later.
- `alembic/` — migrations; `alembic.ini` + `env.py` read `DATABASE_URL` from
  app settings.

## Run (host dev, needs Postgres)

```bash
uv sync
DATABASE_URL=postgresql+psycopg://lexoria:...@127.0.0.1:5432/lexoria uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

`docker compose -f ../../docker-compose.dev.yml up -d` (repo root) starts the
dev Postgres on 127.0.0.1:5432.

## Tests

```bash
uv run pytest                      # unit tests always run
TEST_DATABASE_URL=postgresql+psycopg://.../lexoria_test uv run pytest  # + PG integration
```

PG integration tests rebuild the schema per test via `Base.metadata`
(`tests/conftest.py`) — point `TEST_DATABASE_URL` at a disposable database.

## Conventions

- All timestamps are UTC `timestamptz`; day-boundary logic is computed in
  Python with `zoneinfo` and queried with UTC instants.
- Every user-owned table carries `user_id`; `words` is a global dictionary
  (created only via POST /inbox captures).
- Errors use the envelope `{"error": {code, message, details}}`.
