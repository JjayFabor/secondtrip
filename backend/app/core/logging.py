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
