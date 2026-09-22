"""Structured logging — see docs/architecture/18-observability.md.

The redaction processor is a safety net, not the policy (CLAUDE.md rule
30): the policy is that sensitive fields are never passed to a logger in
the first place. This processor exists because that policy will
eventually be violated by a debugging line someone forgets to remove.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.settings import Settings

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "token_hash",
        "secret",
        "api_key",
        "authorization",
        "cookie",
        "session",
        "signed_url",
        "email",
        "customer_name",
        "address",
        "phone",
        "note",
        "body",
        "description",
        "symptoms_text",
        "diagnosis_text",
        "resolution_text",
        "raw_data",
    }
)

_SENSITIVE_PATH_PREFIXES = ("/api/v1/storage/local/",)


def redact_request_path(path: str) -> str:
    """Remove capability tokens and other credentials embedded in request paths."""
    for prefix in _SENSITIVE_PATH_PREFIXES:
        if path.startswith(prefix):
            return f"{prefix}[REDACTED]"
    return path


class CapabilityPathRedactionFilter(logging.Filter):
    """Redact capability URLs emitted by Uvicorn's built-in access logger."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # Uvicorn access records use:
        # (client_addr, method, full_path, http_version, status_code).
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            redacted_args = list(args)
            redacted_args[2] = redact_request_path(args[2])
            record.args = tuple(redacted_args)
        return True


def redact_sensitive_fields(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***"
        # Catch a signed URL logged under an unrelated key name.
        value = event_dict.get(key)
        if isinstance(value, str) and "X-Amz-Signature" in value:
            event_dict[key] = "***"
    return event_dict


def configure_logging(settings: Settings) -> None:
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_sensitive_fields,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level.upper()]
        ),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level.upper())

    uvicorn_access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, CapabilityPathRedactionFilter) for item in uvicorn_access.filters):
        uvicorn_access.addFilter(CapabilityPathRedactionFilter())
