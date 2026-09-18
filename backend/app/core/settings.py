"""Application configuration — the ONLY place `os.environ` is read.

See docs/architecture/17-configuration.md. Scoped to what Phase 2 (backend
foundation) actually needs; later modules (identity, imports, AI, storage,
email, billing) add their own settings fields when they are built, rather
than stubbing unused variables ahead of time.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    # --- Application -----------------------------------------------------
    app_env: Literal["local", "ci", "staging", "production"] = "local"
    app_name: str = "SecondTrip"
    app_secret: str
    app_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    debug: bool = False
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # --- Database ----------------------------------------------------------
    # Two URLs by design — see docs/architecture/02-multi-tenancy.md §2 and
    # CLAUDE.md rule 4. `database_url` is the non-owner, RLS-bound app role
    # (pooled, in production); `database_url_migrations` is the owner role
    # that runs Alembic (direct/unpooled, in production).
    database_url: str
    database_url_migrations: str
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
    db_statement_timeout_ms: int = 30_000
    db_echo: bool = False

    @model_validator(mode="after")
    def _validate_production_posture(self) -> "Settings":
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false when APP_ENV=production")
            if not self.app_url.startswith("https://"):
                raise ValueError("APP_URL must be https in production")
            if not self.frontend_url.startswith("https://"):
                raise ValueError("FRONTEND_URL must be https in production")
            if self.app_secret in {"", "dev-secret-change-me"}:
                raise ValueError("APP_SECRET must be set to a real secret in production")
        if "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard")
        if len(self.app_secret) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Tests override via dependency_overrides, not env mutation."""
    return Settings()  # values come from the environment via pydantic-settings
