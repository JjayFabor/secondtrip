"""Application configuration — the ONLY place `os.environ` is read.

See docs/architecture/17-configuration.md. Grows one module at a time —
each phase adds only the fields it actually uses, rather than stubbing
unused variables ahead of time. Phase 2 added app/db; Step 3 adds
sessions/cookies/email/CORS-for-credentials.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
        populate_by_name=True,
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

    # --- Sessions & cookies ------------------------------------------------
    # See docs/architecture/03-authentication.md §2. cookie_domain must be a
    # parent domain shared by the frontend and API in staging/production —
    # see 01-system-architecture.md §2. Left unset locally, where frontend
    # and API are different localhost ports and no Domain attribute is set.
    session_cookie_name: str = "st_session"
    session_idle_timeout_days: int = 14
    session_absolute_timeout_days: int = 30
    cookie_domain: str | None = None
    cookie_secure: bool = False
    csrf_cookie_name: str = "st_csrf"
    email_verification_ttl_hours: int = 24
    password_reset_ttl_minutes: int = 60
    invitation_ttl_days: int = 7
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    login_ip_limit: int = 20
    login_ip_window_seconds: int = 300
    register_ip_limit: int = 5
    register_ip_window_seconds: int = 3600
    verification_ip_limit: int = 5
    verification_ip_window_seconds: int = 3600
    password_reset_email_limit: int = 3
    password_reset_ip_limit: int = 10
    password_reset_window_seconds: int = 3600
    invitation_org_limit: int = 50
    invitation_org_window_seconds: int = 86400

    # --- Storage ------------------------------------------------------------
    # Local is the safe development default. Production must use R2; memory is
    # available only for tests and explicit ephemeral runs.
    storage_provider: Literal["local", "memory", "r2"] = "local"
    storage_bucket: str | None = None
    storage_endpoint_url: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None
    storage_region: str = "auto"
    storage_signed_url_ttl_seconds: int = 300
    storage_upload_url_ttl_seconds: int = 900
    storage_local_path: str = "./.storage"

    # --- Background worker --------------------------------------------------
    worker_enabled: bool = True
    worker_id: str | None = None
    worker_concurrency: int = 2
    worker_batch_size: int = 5
    worker_poll_min_seconds: float = 0.5
    worker_poll_max_seconds: float = 5.0
    worker_heartbeat_seconds: int = 15
    worker_stale_after_seconds: int = 120
    job_max_attempts: int = 5
    job_backoff_base_seconds: int = 10
    job_backoff_max_seconds: int = 3600

    # --- Import hard ceilings ----------------------------------------------
    import_max_file_bytes: int = 500 * 1024 * 1024
    import_max_rows: int = 2_000_000
    import_chunk_size: int = 500
    import_max_field_bytes: int = 32 * 1024
    import_max_columns: int = 200

    # --- Detection defaults for newly created organizations ----------------
    detection_default_window_days: int = 30
    detection_default_min_score_to_surface: Decimal = Decimal("40")
    detection_max_followups_per_job: int = 25

    # --- Local demo tooling -------------------------------------------------
    demo_password: str = Field(default="SecondTripDemo-2026!", validation_alias="DEMO_PASSWORD")
    demo_reset: bool = Field(default=False, validation_alias="RESET")

    # --- Billing ------------------------------------------------------------
    billing_provider: Literal["noop"] = "noop"

    # --- Email --------------------------------------------------------------
    email_provider: Literal["console", "resend"] = "console"
    email_api_key: str | None = None
    email_from_address: str = "noreply@secondtrip.example.com"
    email_from_name: str = "SecondTrip"

    @model_validator(mode="after")
    def _validate_production_posture(self) -> "Settings":
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false when APP_ENV=production")
            if not self.app_url.startswith("https://"):
                raise ValueError("APP_URL must be https in production")
            if not self.frontend_url.startswith("https://"):
                raise ValueError("FRONTEND_URL must be https in production")
            if not self.app_secret or self.app_secret.startswith("dev-secret"):
                raise ValueError("APP_SECRET must be set to a real secret in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if not self.cookie_domain:
                raise ValueError("COOKIE_DOMAIN is required in production")
            cookie_parent = self.cookie_domain.lstrip(".").lower()
            public_hosts = {
                urlparse(self.app_url).hostname,
                urlparse(self.frontend_url).hostname,
            }
            if any(
                host is None
                or (
                    host.lower() != cookie_parent
                    and not host.lower().endswith(f".{cookie_parent}")
                )
                for host in public_hosts
            ):
                raise ValueError(
                    "COOKIE_DOMAIN must be a shared parent of APP_URL and FRONTEND_URL"
                )
            normalized_origins = {origin.rstrip("/") for origin in self.cors_allowed_origins}
            if self.frontend_url.rstrip("/") not in normalized_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must include FRONTEND_URL in production")
            if self.email_provider == "console":
                raise ValueError("EMAIL_PROVIDER must not be 'console' in production")
            if self.storage_provider != "r2":
                raise ValueError("STORAGE_PROVIDER must be 'r2' in production")
        if "*" in self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard")
        if len(self.app_secret) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters")
        if self.email_provider == "resend" and not self.email_api_key:
            raise ValueError("EMAIL_API_KEY is required when EMAIL_PROVIDER=resend")
        if self.storage_provider == "r2":
            required_storage_values = {
                "STORAGE_BUCKET": self.storage_bucket,
                "STORAGE_ENDPOINT_URL": self.storage_endpoint_url,
                "STORAGE_ACCESS_KEY_ID": self.storage_access_key_id,
                "STORAGE_SECRET_ACCESS_KEY": self.storage_secret_access_key,
            }
            missing = [name for name, value in required_storage_values.items() if not value]
            if missing:
                raise ValueError(f"R2 storage requires: {', '.join(missing)}")
            if self.storage_region != "auto":
                raise ValueError("STORAGE_REGION must be 'auto' for R2")
            if self.app_env != "local" and not str(self.storage_endpoint_url).startswith(
                "https://"
            ):
                raise ValueError("STORAGE_ENDPOINT_URL must be https outside local development")
        if not 1 <= self.storage_signed_url_ttl_seconds <= 604_800:
            raise ValueError("STORAGE_SIGNED_URL_TTL_SECONDS must be within 1-604800")
        if not 1 <= self.storage_upload_url_ttl_seconds <= 604_800:
            raise ValueError("STORAGE_UPLOAD_URL_TTL_SECONDS must be within 1-604800")
        if self.worker_concurrency < 1 or self.worker_batch_size < 1:
            raise ValueError("WORKER_CONCURRENCY and WORKER_BATCH_SIZE must be positive")
        if self.worker_heartbeat_seconds < 1:
            raise ValueError("WORKER_HEARTBEAT_SECONDS must be positive")
        if not 0 < self.worker_poll_min_seconds <= self.worker_poll_max_seconds:
            raise ValueError("worker poll bounds must be positive and ordered")
        if self.worker_stale_after_seconds <= self.worker_heartbeat_seconds * 4:
            raise ValueError("WORKER_STALE_AFTER_SECONDS must be more than 4x heartbeat")
        if self.job_max_attempts < 1:
            raise ValueError("JOB_MAX_ATTEMPTS must be positive")
        if not 0 < self.job_backoff_base_seconds <= self.job_backoff_max_seconds:
            raise ValueError("job backoff bounds must be positive and ordered")
        if not 0 < self.import_max_file_bytes <= 500 * 1024 * 1024:
            raise ValueError("IMPORT_MAX_FILE_BYTES must be within the 500 MB hard ceiling")
        if not 0 < self.import_max_rows <= 2_000_000:
            raise ValueError("IMPORT_MAX_ROWS must be within the 2,000,000-row hard ceiling")
        if self.import_chunk_size < 1:
            raise ValueError("IMPORT_CHUNK_SIZE must be positive")
        if not 0 < self.import_max_field_bytes <= 64 * 1024:
            raise ValueError("IMPORT_MAX_FIELD_BYTES must be within the 64 KB hard ceiling")
        if not 0 < self.import_max_columns <= 200:
            raise ValueError("IMPORT_MAX_COLUMNS must be within the 200-column hard ceiling")
        if self.detection_default_window_days < 1:
            raise ValueError("DETECTION_DEFAULT_WINDOW_DAYS must be positive")
        if not Decimal(0) <= self.detection_default_min_score_to_surface <= Decimal(100):
            raise ValueError("DETECTION_DEFAULT_MIN_SCORE_TO_SURFACE must be within 0-100")
        if self.detection_max_followups_per_job < 1:
            raise ValueError("DETECTION_MAX_FOLLOWUPS_PER_JOB must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Tests override via dependency_overrides, not env mutation."""
    return Settings()  # values come from the environment via pydantic-settings
