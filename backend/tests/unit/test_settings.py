from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def production_values(settings: Settings) -> dict[str, object]:
    values = settings.model_dump()
    values.update(
        {
            "app_env": "production",
            "app_secret": "production-secret-with-at-least-32-characters",
            "app_url": "https://api.secondtrip.example.com",
            "frontend_url": "https://secondtrip.example.com",
            "cors_allowed_origins": ["https://secondtrip.example.com"],
            "debug": False,
            "cookie_domain": ".secondtrip.example.com",
            "cookie_secure": True,
            "storage_provider": "r2",
            "storage_bucket": "secondtrip-production",
            "storage_endpoint_url": "https://account.r2.cloudflarestorage.com",
            "storage_access_key_id": "access",
            "storage_secret_access_key": "secret",
            "email_provider": "resend",
            "email_api_key": "resend-key",
        }
    )
    return values


def test_production_posture_accepts_shared_cookie_domain(settings: Settings) -> None:
    configured = Settings.model_validate(production_values(settings))

    assert configured.app_env == "production"


def test_neon_libpq_urls_are_normalized_for_asyncpg(settings: Settings) -> None:
    values = settings.model_dump()
    neon_url = (
        "postgresql://secondtrip_app:encoded%2Fpassword@"
        "ep-example-pooler.ap-southeast-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    values.update(
        {
            "database_url": neon_url,
            "database_url_migrations": neon_url.replace("-pooler", ""),
        }
    )

    configured = Settings.model_validate(values)

    assert configured.database_url.startswith("postgresql+asyncpg://")
    assert "encoded%2Fpassword" in configured.database_url
    assert "ssl=require" in configured.database_url
    assert "sslmode" not in configured.database_url
    assert "channel_binding" not in configured.database_url
    assert "-pooler" not in configured.database_url_migrations


def test_demo_reset_ignores_render_terminal_reset_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESET", "\x1b(B\x1b[m")
    monkeypatch.setenv("DEMO_RESET", "true")

    configured = Settings(
        _env_file=None,
        app_secret="test-secret-with-at-least-32-characters",
        database_url="postgresql+asyncpg://app:app@localhost/secondtrip",
        database_url_migrations="postgresql+asyncpg://owner:owner@localhost/secondtrip",
        debug=False,
    )

    assert configured.demo_reset is True


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"cookie_domain": None}, "COOKIE_DOMAIN is required"),
        (
            {"cookie_domain": ".other.example.com"},
            "COOKIE_DOMAIN must be a shared parent",
        ),
        (
            {"cors_allowed_origins": ["https://other.example.com"]},
            "CORS_ALLOWED_ORIGINS must include FRONTEND_URL",
        ),
        (
            {"app_secret": "dev-secret-change-me-please-32-chars-min"},
            "APP_SECRET must be set to a real secret",
        ),
    ],
)
def test_production_posture_rejects_broken_cross_origin_auth(
    settings: Settings,
    updates: dict[str, object],
    message: str,
) -> None:
    values = production_values(settings)
    values.update(updates)

    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(values)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"worker_heartbeat_seconds": 0}, "WORKER_HEARTBEAT_SECONDS"),
        ({"job_max_attempts": 0}, "JOB_MAX_ATTEMPTS"),
        (
            {"job_backoff_base_seconds": 20, "job_backoff_max_seconds": 10},
            "job backoff bounds",
        ),
        ({"import_max_file_bytes": 500 * 1024 * 1024 + 1}, "IMPORT_MAX_FILE_BYTES"),
        ({"import_max_rows": 2_000_001}, "IMPORT_MAX_ROWS"),
        ({"import_max_field_bytes": 64 * 1024 + 1}, "IMPORT_MAX_FIELD_BYTES"),
        ({"import_max_columns": 201}, "IMPORT_MAX_COLUMNS"),
        ({"detection_default_window_days": 0}, "DETECTION_DEFAULT_WINDOW_DAYS"),
        (
            {"detection_default_min_score_to_surface": 101},
            "DETECTION_DEFAULT_MIN_SCORE_TO_SURFACE",
        ),
        ({"detection_max_followups_per_job": 0}, "DETECTION_MAX_FOLLOWUPS_PER_JOB"),
        ({"storage_signed_url_ttl_seconds": 604_801}, "STORAGE_SIGNED_URL_TTL_SECONDS"),
        ({"storage_upload_url_ttl_seconds": 0}, "STORAGE_UPLOAD_URL_TTL_SECONDS"),
    ],
)
def test_worker_settings_reject_unsafe_bounds(
    settings: Settings,
    updates: dict[str, object],
    message: str,
) -> None:
    values = settings.model_dump()
    values.update(updates)
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(values)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"storage_region": "us-east-1"}, "STORAGE_REGION"),
        (
            {"app_env": "staging", "storage_endpoint_url": "http://r2.example.test"},
            "STORAGE_ENDPOINT_URL",
        ),
    ],
)
def test_r2_settings_reject_invalid_endpoint_configuration(
    settings: Settings,
    updates: dict[str, object],
    message: str,
) -> None:
    values = settings.model_dump()
    values.update(
        {
            "storage_provider": "r2",
            "storage_bucket": "secondtrip-test",
            "storage_endpoint_url": "https://account.r2.cloudflarestorage.com",
            "storage_access_key_id": "access",
            "storage_secret_access_key": "secret",
        }
    )
    values.update(updates)
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(values)
