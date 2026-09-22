"""Plan-independent entitlement resolution and usage accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.modules.billing.entitlements.defaults import FREE_PLAN_DEFAULTS
from app.modules.billing.entitlements.keys import EntitlementKey
from app.modules.billing.models import (
    OrganizationEntitlementOverride,
    OrganizationSubscription,
    Plan,
    PlanEntitlement,
    UsageCounter,
)
from app.modules.organizations.service import get_organization_timezone


@dataclass(frozen=True, slots=True)
class EntitlementCheck:
    allowed: bool
    key: EntitlementKey
    limit: int | None
    current: int
    reason: str | None
    upgrade_suggested: bool


class EntitlementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def limit(self, tenant: TenantContext, key: EntitlementKey) -> int | None:
        now = datetime.now(UTC)
        override = (
            await self._session.execute(
                select(OrganizationEntitlementOverride).where(
                    OrganizationEntitlementOverride.organization_id == tenant.organization_id,
                    OrganizationEntitlementOverride.entitlement_key == key.value,
                    (
                        OrganizationEntitlementOverride.expires_at.is_(None)
                        | (OrganizationEntitlementOverride.expires_at > now)
                    ),
                )
            )
        ).scalar_one_or_none()
        if override is not None:
            return int(override.limit_value) if override.limit_value is not None else None

        subscription = (
            await self._session.execute(
                select(OrganizationSubscription).where(
                    OrganizationSubscription.organization_id == tenant.organization_id
                )
            )
        ).scalar_one_or_none()
        plan_id = None
        if subscription is not None:
            active = subscription.status in {"active", "trialing"}
            in_grace = (
                subscription.status == "past_due"
                and subscription.updated_at + timedelta(days=14) > now
            )
            if active or in_grace:
                plan_id = subscription.plan_id

        if plan_id is None:
            plan_id = (
                await self._session.execute(select(Plan.id).where(Plan.key == "free"))
            ).scalar_one_or_none()
        if plan_id is None:
            return FREE_PLAN_DEFAULTS[key]

        entitlement = (
            await self._session.execute(
                select(PlanEntitlement).where(
                    PlanEntitlement.plan_id == plan_id,
                    PlanEntitlement.entitlement_key == key.value,
                )
            )
        ).scalar_one_or_none()
        if entitlement is None:
            return FREE_PLAN_DEFAULTS[key]
        return int(entitlement.limit_value) if entitlement.limit_value is not None else None

    async def check(
        self,
        tenant: TenantContext,
        key: EntitlementKey,
        *,
        amount: int = 1,
    ) -> EntitlementCheck:
        if amount < 0:
            raise ValueError("entitlement amount must not be negative")
        limit = await self.limit(tenant, key)
        current = await self._current_usage(tenant, key)
        allowed = limit is None or current + amount <= limit
        reason = None
        if not allowed:
            reason = f"Usage for {key.value} is {current} of {limit}."
        return EntitlementCheck(
            allowed=allowed,
            key=key,
            limit=limit,
            current=current,
            reason=reason,
            upgrade_suggested=not allowed,
        )

    async def consume(
        self,
        tenant: TenantContext,
        key: EntitlementKey,
        *,
        amount: int,
    ) -> None:
        if amount < 1:
            raise ValueError("consumed entitlement amount must be positive")
        period_start, period_end = await self._month_period(tenant)
        statement = insert(UsageCounter).values(
            organization_id=tenant.organization_id,
            metric_key=key.value,
            period_start=period_start,
            period_end=period_end,
            value=amount,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                UsageCounter.organization_id,
                UsageCounter.metric_key,
                UsageCounter.period_start,
            ],
            set_={"value": UsageCounter.value + amount},
        )
        await self._session.execute(statement)

    async def reserve(
        self,
        tenant: TenantContext,
        key: EntitlementKey,
        *,
        amount: int = 1,
    ) -> EntitlementCheck:
        """Atomically check and consume a quota within the caller's transaction."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"{tenant.organization_id}:{key.value}"},
        )
        result = await self.check(tenant, key, amount=amount)
        if result.allowed:
            await self.consume(tenant, key, amount=amount)
        return result

    async def _current_usage(self, tenant: TenantContext, key: EntitlementKey) -> int:
        period_start, period_end = await self._month_period(tenant)
        value = (
            await self._session.execute(
                select(UsageCounter.value).where(
                    UsageCounter.organization_id == tenant.organization_id,
                    UsageCounter.metric_key == key.value,
                    UsageCounter.period_start == period_start,
                    UsageCounter.period_end == period_end,
                )
            )
        ).scalar_one_or_none()
        return int(value or 0)

    async def _month_period(self, tenant: TenantContext) -> tuple[date, date]:
        timezone_name = await get_organization_timezone(
            self._session, tenant.organization_id
        )
        try:
            local_today = datetime.now(ZoneInfo(timezone_name)).date()
        except ZoneInfoNotFoundError:
            local_today = datetime.now(UTC).date()
        period_start = local_today.replace(day=1)
        if period_start.month == 12:
            period_end = date(period_start.year + 1, 1, 1)
        else:
            period_end = date(period_start.year, period_start.month + 1, 1)
        return period_start, period_end
