"""TenantContext — see docs/architecture/02-multi-tenancy.md §2 and
CLAUDE.md rules 2–5.

The only vehicle for tenant identity in this codebase. It is never carried
on a contextvar (that is exactly how tenant context leaks between
concurrently-running coroutines) — it is passed explicitly to every
repository, service call, and background job handler.
"""

from dataclasses import dataclass
from uuid import UUID

from app.core.permissions import OrganizationRole


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: UUID
    actor_user_id: UUID | None = None
    """None for system/worker-initiated work."""
    role: OrganizationRole | None = None
    """None means a system actor: permission checks are bypassed, but the
    context is still fully org-scoped — see CLAUDE.md rule 5."""
    request_id: str | None = None
