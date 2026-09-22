"""Billing protocol; provider SDK types never cross this package boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class BillingNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BillingCustomer:
    reference: str


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    url: str


@dataclass(frozen=True, slots=True)
class PortalSession:
    url: str


@dataclass(frozen=True, slots=True)
class SubscriptionSnapshot:
    reference: str
    status: str


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    provider_event_id: str
    event_type: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class BillingStateChange:
    customer_reference: str
    subscription: SubscriptionSnapshot


class BillingProvider(Protocol):
    async def create_customer(
        self, *, organization_id: UUID, email: str, name: str
    ) -> BillingCustomer: ...

    async def create_checkout(
        self,
        *,
        customer_ref: str,
        plan_key: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    async def create_portal(self, *, customer_ref: str, return_url: str) -> PortalSession: ...

    async def get_subscription(self, *, subscription_ref: str) -> SubscriptionSnapshot: ...

    async def cancel_subscription(
        self, *, subscription_ref: str, at_period_end: bool = True
    ) -> SubscriptionSnapshot: ...

    async def verify_webhook(
        self, *, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookEvent: ...

    async def parse_webhook(self, event: WebhookEvent) -> BillingStateChange | None: ...
