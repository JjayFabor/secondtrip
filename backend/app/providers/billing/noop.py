"""V1 billing adapter: entitlements work, payment operations do not."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.providers.billing.base import (
    BillingCustomer,
    BillingNotConfiguredError,
    BillingStateChange,
    CheckoutSession,
    PortalSession,
    SubscriptionSnapshot,
    WebhookEvent,
)


class NoopBillingProvider:
    @staticmethod
    def _not_configured() -> BillingNotConfiguredError:
        return BillingNotConfiguredError("Billing checkout is not configured.")

    async def create_customer(
        self, *, organization_id: UUID, email: str, name: str
    ) -> BillingCustomer:
        del organization_id, email, name
        raise self._not_configured()

    async def create_checkout(
        self,
        *,
        customer_ref: str,
        plan_key: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        del customer_ref, plan_key, success_url, cancel_url
        raise self._not_configured()

    async def create_portal(self, *, customer_ref: str, return_url: str) -> PortalSession:
        del customer_ref, return_url
        raise self._not_configured()

    async def get_subscription(self, *, subscription_ref: str) -> SubscriptionSnapshot:
        del subscription_ref
        raise self._not_configured()

    async def cancel_subscription(
        self, *, subscription_ref: str, at_period_end: bool = True
    ) -> SubscriptionSnapshot:
        del subscription_ref, at_period_end
        raise self._not_configured()

    async def verify_webhook(
        self, *, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookEvent:
        del raw_body, headers
        raise self._not_configured()

    async def parse_webhook(self, event: WebhookEvent) -> BillingStateChange | None:
        del event
        raise self._not_configured()
