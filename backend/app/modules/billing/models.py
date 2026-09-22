"""Plan, entitlement, subscription, and usage ORM models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin


class Plan(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("key", name="plans_key_key"),)

    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    annual_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    is_public: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))


class PlanEntitlement(Base, PrimaryKeyMixin):
    __tablename__ = "plan_entitlements"
    __table_args__ = (
        UniqueConstraint("plan_id", "entitlement_key", name="plan_entitlements_plan_key"),
    )

    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
    )
    entitlement_key: Mapped[str] = mapped_column(Text, nullable=False)
    limit_value: Mapped[int | None] = mapped_column(BigInteger)
    is_boolean: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    period: Mapped[str | None] = mapped_column(Text)


class OrganizationSubscription(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "organization_subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", name="organization_subscriptions_org_key"),
    )

    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    billing_provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="noop")
    provider_customer_id: Mapped[str | None] = mapped_column(Text)
    provider_subscription_id: Mapped[str | None] = mapped_column(Text)
    current_period_start: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    trial_ends_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class OrganizationEntitlementOverride(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "organization_entitlement_overrides"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entitlement_key",
            name="organization_entitlement_overrides_org_key",
        ),
    )

    entitlement_key: Mapped[str] = mapped_column(Text, nullable=False)
    limit_value: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class UsageCounter(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "metric_key", "period_start", name="usage_counters_org_period_key"
        ),
    )

    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class BillingEvent(Base, PrimaryKeyMixin):
    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="billing_events_provider_event_key"),
        Index("billing_events_org_created_idx", "organization_id", text("created_at DESC")),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
