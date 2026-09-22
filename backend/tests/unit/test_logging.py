"""Tests for access-log credential redaction."""

import logging

from app.core.logging import CapabilityPathRedactionFilter, redact_request_path


def test_redacts_local_storage_capability_token() -> None:
    token = "encoded-payload.secret-signature"

    assert redact_request_path(f"/api/v1/storage/local/{token}") == (
        "/api/v1/storage/local/[REDACTED]"
    )


def test_preserves_non_sensitive_path() -> None:
    assert redact_request_path("/api/v1/imports") == "/api/v1/imports"


def test_redacts_uvicorn_access_log_path() -> None:
    token = "encoded-payload.secret-signature"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "PUT", f"/api/v1/storage/local/{token}", "1.1", 204),
        None,
    )

    assert CapabilityPathRedactionFilter().filter(record)
    assert isinstance(record.args, tuple)
    assert record.args[2] == "/api/v1/storage/local/[REDACTED]"
    assert token not in record.getMessage()
