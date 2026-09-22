"""Safe audit payload and CSV rendering helpers.

Audit changes are deliberately allowlisted by resource type. A new model
field must not become an audit-data leak merely because a caller passes it to
``record`` or because a CSV consumer renders a JSON object.
"""

from __future__ import annotations

from typing import Any, Final

AUDITABLE_FIELDS: Final[dict[str, frozenset[str]]] = {
    "organization": frozenset({"name", "slug", "timezone", "currency_code", "status"}),
    "membership": frozenset({"role", "revoked_at"}),
    "organization_membership": frozenset({"role", "revoked_at"}),
    "organization_invitation": frozenset({"role", "revoked_at"}),
    "invitation": frozenset({"role", "revoked_at"}),
    "rework_review": frozenset(
        {"decision", "category_id", "root_cause_id", "supersedes_review_id"}
    ),
}
_MAX_VALUE_LENGTH = 200


def _truncate(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_MAX_VALUE_LENGTH]
    if isinstance(value, dict):
        return {str(key): _truncate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate(item) for item in value]
    return value


def sanitize_changes(
    resource_type: str | None, changes: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not changes or resource_type is None:
        return None
    allowed = AUDITABLE_FIELDS.get(resource_type, frozenset())
    sanitized = {key: _truncate(value) for key, value in changes.items() if key in allowed}
    return sanitized or None
