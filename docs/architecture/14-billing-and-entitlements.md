# 14 — Billing Readiness & Entitlements

No payment processing in V1. What V1 *does* build is the entitlement system, because
authorization decisions ("can this org import another file?") must never be rewritten later to
accommodate a billing provider.

**The rule:** application code asks the **entitlement service**. It never asks the billing
provider, never reads a plan key, and never branches on a provider's subscription status.

```python
# ✅  Right
if not await entitlements.can_import_jobs(tenant, row_count=250_000):
    raise EntitlementExceeded(...)

# ❌  Wrong — couples business logic to a plan name
if org.plan == "free" and row_count > 10_000: ...

# ❌❌ Catastrophically wrong — couples business logic to a vendor
sub = stripe.Subscription.retrieve(org.stripe_subscription_id)
if sub.status != "active": ...
```

---

## 1. Entitlement keys

| Key | Type | Free | Pro | Business | Period |
| --- | --- | --- | --- | --- | --- |
| `jobs_imported` | limit | 5,000 | 100,000 | 1,000,000 | month |
| `jobs_retained` | limit | 10,000 | 500,000 | unlimited | total |
| `retention_months` | limit | 6 | 24 | 84 | total |
| `import_file_bytes` | limit | 5 MB | 50 MB | 200 MB | per-op |
| `imports_per_month` | limit | 3 | 50 | unlimited | month |
| `concurrent_imports` | limit | 1 | 2 | 3 | concurrent |
| `team_members` | limit | 2 | 10 | unlimited | total |
| `ai_analyses` | limit | 0 | 500 | 5,000 | month |
| `ai_spend_cents` | limit | 0 | 500 | 5,000 | month |
| `embeddings_enabled` | boolean | ✅ | ✅ | ✅ | — |
| `exports_enabled` | boolean | ✅ | ✅ | ✅ | — |
| `exports_per_month` | limit | 5 | 100 | unlimited | month |
| `api_access` | boolean | ❌ | ❌ | ✅ | — |
| `integrations` | boolean | ❌ | ❌ | ✅ | — |
| `custom_detection_rules` | boolean | ❌ | ✅ | ✅ | — |
| `audit_retention_months` | limit | 3 | 24 | 84 | total |

`embeddings_enabled` is ✅ on free deliberately: semantic similarity is what makes the free
tier's results good enough to convert. The AI *classification* budget is where the cost gate
sits, because that is where the real spend is.

`ai_spend_cents` is a second, independent guard alongside `ai_analyses` — a per-call cost
ceiling protects against a model price change or an unexpectedly long prompt in a way a
request count cannot.

---

## 2. Resolution order

```
1. organization_entitlement_overrides   (non-expired) — support grants, beta access, custom deals
2. plan_entitlements for the org's current plan
3. FREE_PLAN_DEFAULTS                   — the fallback when there is no subscription row
```

`limit_value IS NULL` means unlimited. The override table is what lets you say "give this
design partner 10× the AI budget for three months" without inventing a plan, and its
`expires_at` means you do not have to remember to take it away.

### Degradation when a subscription lapses

```
active | trialing → full plan entitlements
past_due          → full entitlements for a 14-day grace period; in-app warning
canceled | grace expired → FREE tier limits, data RETAINED (read-only beyond free limits)
```

**Data is never deleted for non-payment.** An org over the free retention limit after
downgrading keeps its data and loses the ability to *import more* until it is under the limit
or upgrades. Deleting a paying-customer-turned-lapsed-customer's history is how you guarantee
they never come back.

---

## 3. The service

```python
class EntitlementService:
    async def check(self, tenant: TenantContext, key: str, *, amount: int = 1) -> EntitlementCheck: ...
    async def limit(self, tenant: TenantContext, key: str) -> int | None: ...
    async def consume(self, tenant: TenantContext, key: str, *, amount: int) -> None: ...

    # Intention-revealing wrappers used by domain code
    async def can_import_jobs(self, tenant, *, row_count: int) -> EntitlementCheck: ...
    async def can_use_ai(self, tenant) -> EntitlementCheck: ...
    async def can_invite_member(self, tenant) -> EntitlementCheck: ...
    async def can_export(self, tenant) -> EntitlementCheck: ...


@dataclass(frozen=True, slots=True)
class EntitlementCheck:
    allowed: bool
    key: str
    limit: int | None
    current: int
    reason: str | None          # human-readable, shown in the UI
    upgrade_suggested: bool
```

Returning a rich result rather than a bare boolean means the API can produce a genuinely
useful denial — *"You've imported 4,800 of 5,000 jobs this month on the Free plan"* — instead
of a blank 403. That message is the entire conversion surface of a freemium product.

### Where checks happen

| Action | Checked at |
| --- | --- |
| Create import | `POST /imports` — before the presigned URL is issued |
| Commit import | Re-checked with the **actual** row count from validation |
| Invite member | `POST /invitations` |
| Trigger AI | Inside the Stage 5 gate, before dispatch |
| Generate export | `POST /exports` |
| Configure detection rules | `PUT /settings/detection` |

The import check happens twice on purpose: at creation we only have the file size, and at
commit we know the real row count. A user must not discover at row 4,999 that they are over
quota — but nor should a 5 MB file be waved through and then found to contain 2M rows.

### Consumption

```sql
INSERT INTO usage_counters (organization_id, metric_key, period_start, period_end, value)
VALUES (:org, :key, :start, :end, :amount)
ON CONFLICT (organization_id, metric_key, period_start)
DO UPDATE SET value = usage_counters.value + EXCLUDED.value;
```

Consumption is recorded **in the transaction that performs the work**, so a rolled-back import
does not consume quota. Periods are calendar months in the organization's timezone.

A nightly reconciliation recomputes `jobs_imported` from `import_batches` for the current
period and corrects drift, since a counter that diverges from reality is worse than no counter.

---

## 4. The billing provider protocol

```python
class BillingProvider(Protocol):
    async def create_customer(self, *, organization_id: UUID, email: str,
                              name: str) -> BillingCustomer: ...
    async def create_checkout(self, *, customer_ref: str, plan_key: str,
                              success_url: str, cancel_url: str) -> CheckoutSession: ...
    async def create_portal(self, *, customer_ref: str, return_url: str) -> PortalSession: ...
    async def get_subscription(self, *, subscription_ref: str) -> SubscriptionSnapshot: ...
    async def cancel_subscription(self, *, subscription_ref: str,
                                  at_period_end: bool = True) -> SubscriptionSnapshot: ...
    async def verify_webhook(self, *, raw_body: bytes,
                             headers: Mapping[str, str]) -> WebhookEvent: ...
    async def parse_webhook(self, event: WebhookEvent) -> BillingStateChange | None: ...
```

`SubscriptionSnapshot`, `BillingStateChange` and friends are **our** types. `plan_key` is our
key (`pro`), mapped to a provider price ID inside the adapter — domain code never sees a
`price_...` identifier.

`verify_webhook` and `parse_webhook` are separate for a security reason: verification operates
on **raw bytes** and must happen before any parsing ([11 §10](11-security-threat-model.md)).
A single combined method invites an implementation that parses first.

Implementations: `NoopBillingProvider` (V1 — every org is on `free`, `create_checkout` raises
`NotConfigured`), later `StripeBillingProvider`, `LemonSqueezyBillingProvider`, or
`PaddleBillingProvider`.

**Provider-specific identifiers stay in `organization_subscriptions`**
(`billing_provider`, `provider_customer_id`, `provider_subscription_id`). No `stripe_*` column
names anywhere — a schema that names a vendor is a schema that has to be migrated to change
one.

---

## 5. Webhook handling (design only)

```
POST /api/v1/billing/webhooks/{provider}
  → read RAW body
  → provider.verify_webhook(raw_body, headers)          # HMAC, constant-time, ≤5 min old
  → INSERT billing_events (provider_event_id UNIQUE)    # conflict ⇒ already seen, return 200
  → return 200 immediately
  → enqueue billing.process_event
```

The enqueue-then-return shape means our processing bugs never trigger provider retry storms,
and a duplicate delivery is a unique-constraint no-op.

`billing.process_event` resolves the organization **from our own `provider_customer_id`
mapping**, never from the payload, and applies the event as a **state reconciliation** — "set
the subscription to this state" — rather than a delta, because webhook ordering is not
guaranteed. An out-of-order `updated` followed by an older `created` must converge to the
correct state.

---

## 6. Module layout

```
backend/app/modules/billing/
├── router.py              # plans, subscription status, checkout/portal (503 in V1), webhooks
├── schemas.py
├── models.py              # plans, plan_entitlements, subscriptions, overrides,
│                          # usage_counters, billing_events
├── repository.py
├── entitlements/
│   ├── keys.py            # the entitlement key catalogue (typed constants)
│   ├── service.py         # EntitlementService
│   ├── usage.py           # counters + reconciliation
│   └── defaults.py        # FREE_PLAN_DEFAULTS
├── subscriptions/
│   └── service.py         # state reconciliation from provider events
└── webhooks/
    └── handler.py

backend/app/providers/billing/
├── base.py                # BillingProvider protocol + our types
├── noop.py                # V1
└── stripe/                # later; the only place `stripe` may be imported
```

Note that `entitlements/` lives inside the billing module but is imported by almost every other
module. That is acceptable and intentional: entitlements are the *interface* billing exposes to
the rest of the system, and the dependency points at a service ([01 §5](01-system-architecture.md)),
never at billing's repository or models.

---

## 7. V1 scope

**Built:** plans and entitlements seeded by migration, `EntitlementService` with real
enforcement at all six checkpoints, usage counters, override table, an in-app plan/usage view,
and `NoopBillingProvider`.

**Not built:** checkout, portal, webhooks, invoices, proration, tax, dunning.

Every organization is created on `free`. Raising a limit for an early customer is an
`organization_entitlement_overrides` row — which is exactly why that table exists in V1 rather
than being deferred with the rest of billing.
