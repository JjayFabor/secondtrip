"""TenantRepository — see docs/architecture/02-multi-tenancy.md §2 and
CLAUDE.md rule 2.

Cannot be constructed without a TenantContext (a required constructor
argument), and every query it issues is org-filtered by construction.
`get_by_id` is always `WHERE id = :id AND organization_id = :org` — never
`session.get(Model, id)` — so a missing row and a wrong-tenant row are
indistinguishable to the caller, which is what makes 404-not-403 the
uniform answer (CLAUDE.md rule 3).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.db.base import Base


class TenantRepository[ModelT: Base]:
    """`ModelT` is bound to `Base` rather than a richer protocol carrying
    `id`/`organization_id`: every real subclass also mixes in
    `PrimaryKeyMixin` and `TenantMixin` (app/db/base.py), which supply
    those columns, but SQLAlchemy's declarative mixin attributes aren't
    expressible in the generic bound without more ceremony than the two
    `type: ignore`s below cost. Both are scoped to the exact line that
    needs them, not blanket-suppressed for the module."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    def _scoped(self, stmt: Select[Any]) -> Select[Any]:
        return stmt.where(self.model.organization_id == self._tenant.organization_id)  # type: ignore[attr-defined]

    async def get_by_id(self, id: UUID) -> ModelT | None:
        stmt = self._scoped(select(self.model).where(self.model.id == id))  # type: ignore[attr-defined]
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
