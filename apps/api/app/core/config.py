"""Application settings loaded from environment variables.

docker compose passes every value explicitly; a local `.env` (repo root or
`apps/api`) is also picked up for host-based development.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lexoria API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Synchronous SQLAlchemy with the psycopg (v3) driver.
    database_url: str = (
        "postgresql+psycopg://lexoria:lexoria_dev_password@127.0.0.1:5432/lexoria"
    )

    # --- Auth -----------------------------------------------------------
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    # Auth cookies (refresh token only; access token travels in Authorization).
    refresh_cookie_name: str = "lexoria_refresh"
    cookie_secure: bool = False
    # When True, auth/refresh and auth/logout reject requests without an
    # Origin header (browser protection). Tests / non-browser clients may
    # leave it False so Origin-less requests are accepted.
    auth_origin_required: bool = False

    # CORS / policy.
    allowed_origins: str = "http://localhost:8080,http://localhost:5173"
    allow_registration: bool = True

    # Generated-PDF storage (mounted as the private `pdfs` volume).
    pdf_storage_dir: str = "/data/pdfs"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
