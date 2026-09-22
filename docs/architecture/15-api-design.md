# 15 — API Design

---

## 1. Conventions

### Base path and versioning

```
https://api.<domain>/api/v1
```

**URI versioning**, not headers. It is visible in logs, trivially routable, cacheable, and
obvious to a developer reading a stack trace. Content negotiation is more elegant and buys
nothing here.

Within `v1` we make only **additive** changes: new optional request fields, new response
fields, new endpoints. Removing a field, changing a type, tightening validation, or altering
default behaviour requires `v2`. Both versions then run side by side from the same services,
with `v1` routers becoming thin translation layers. The internal deprecation policy is 6
months' notice with `Deprecation` and `Sunset` headers.

### Tenant scoping in the path

```
/api/v1/orgs/{organization_id}/jobs
```

The organization is a **path parameter**, which makes it impossible to write a tenant endpoint
that forgets to declare its scope — the route will not resolve without it, and the dependency
that consumes it performs the membership check. A header-based tenant makes scoping look
optional and is rejected for that reason ([02 §2](02-multi-tenancy.md)).

Non-tenant routes: `/auth/*`, `/me/*`, `/orgs` (list/create), `/plans`, `/health`.

### Pagination — cursor, always

```
GET /orgs/{org}/jobs?limit=50&cursor=eyJzIjoiMjAyNi0wMy0xMiIsImkiOiIwMTk0Li4uIn0
```

```json
{
  "data": [ ... ],
  "page": { "next_cursor": "eyJzIj...", "has_more": true, "limit": 50 }
}
```

The cursor is base64 of the sort key plus the tie-breaking `id`, matching the composite index
for that sort order. Offset pagination is wrong for this product specifically: an import
running while a user pages through jobs shifts rows under them, silently duplicating and
skipping records. `limit` defaults to 50, caps at 200.

**No total count by default.** `COUNT(*)` over a large filtered set is the most expensive query
in a list endpoint and is usually rendered as "1–50 of many" anyway. `?include_total=true` is
available where a customer genuinely needs it.

### Filtering & sorting

```
?status=completed&technician_id=...&service_date_from=2026-01-01&sort=-service_date
```

- Filter names are explicit Pydantic query-model fields. No generic `filter[field][op]` syntax —
  that is a query language, and query languages become injection surfaces and performance
  cliffs.
- `sort` accepts a whitelisted set only, `-` prefix for descending. An unknown key is a `422`.
- Every sortable field has a supporting composite index led by `organization_id`.

### Errors — RFC 9457 `application/problem+json`

```json
{
  "type": "https://secondtrip.dev/errors/entitlement-exceeded",
  "title": "Import limit reached",
  "status": 403,
  "detail": "You have imported 4,800 of 5,000 jobs this month on the Free plan.",
  "code": "ENTITLEMENT_EXCEEDED",
  "request_id": "01JQ8X...",
  "errors": [
    { "field": "row_count", "code": "LIMIT_EXCEEDED", "message": "Exceeds remaining quota of 200" }
  ]
}
```

`code` is the stable machine identifier the frontend switches on; `detail` is the human
sentence. Validation failures return `422` with a populated `errors[]`.

| Status | Used for |
| --- | --- |
| 400 | Malformed request |
| 401 | No/invalid session |
| 403 | Authenticated but not permitted, or entitlement exceeded |
| 404 | Not found **or not in your organization** — never distinguished |
| 409 | State conflict (e.g. committing an import that is already processing) |
| 422 | Validation failure |
| 429 | Rate limited (`Retry-After` header) |
| 5xx | Generic message + `request_id`; details only in logs |

### Idempotency

`Idempotency-Key` header, **required** on: `POST /imports/{id}/commit`,
`POST /exports`, `POST /billing/checkout`. The key plus the route and org is stored with the
response for 24 hours; a replay returns the stored response rather than repeating the effect.

### Other conventions

- Money is serialized as a **decimal string** (`"1234.50"`) with a sibling `currency` field.
  JSON numbers are IEEE-754 doubles in every JavaScript client, and `0.1 + 0.2` problems in a
  cost report are indefensible.
- Timestamps are ISO 8601 UTC with `Z`. Calendar dates are `YYYY-MM-DD`.
- Request models are `extra="forbid"` — an unexpected field is a `422`, not a silent ignore.
- All `/orgs/**` responses carry `Cache-Control: private, no-store`.
- `X-Request-Id` is echoed on every response.

---

## 2. Endpoint surface

Legend — **Auth:** ○ public · ◐ session · ● session + org membership. **Role** is the minimum
required.

### Authentication — `/auth`

| Method | Path | Purpose | Auth |
| --- | --- | --- | --- |
| POST | `/auth/register` | Create account, send verification | ○ |
| POST | `/auth/verify-email` | Consume token, create session | ○ |
| POST | `/auth/resend-verification` | Rate-limited resend | ○ |
| POST | `/auth/login` | Create session, set cookie | ○ |
| POST | `/auth/logout` | Revoke current session | ◐ |
| POST | `/auth/logout-all` | Revoke all sessions | ◐ |
| POST | `/auth/password-reset/request` | Always 202 | ○ |
| POST | `/auth/password-reset/confirm` | Reset + revoke all sessions | ○ |
| POST | `/auth/invitations/accept` | Redeem an invitation token | ◐ |
| GET | `/auth/invitations/{token}` | Preview an invitation (org name, role) before signup | ○ |

### Current user — `/me`

| Method | Path | Purpose | Auth |
| --- | --- | --- | --- |
| GET | `/me` | Profile + organizations + roles | ◐ |
| PATCH | `/me` | Update name, timezone | ◐ |
| POST | `/me/password` | Change password (requires current) | ◐ |
| POST | `/me/email` | Request email change | ◐ |
| GET | `/me/sessions` | Active sessions (device list) | ◐ |
| DELETE | `/me/sessions/{id}` | Revoke one session | ◐ |
| GET | `/me/invitations` | Pending invitations for my address | ◐ |
| POST | `/me/export` | Request personal data export | ◐ |
| DELETE | `/me` | Delete/anonymise account | ◐ |

`GET /me` is the frontend's bootstrap call and must stay fast — one query for the user, one for
memberships with organization names.

### Organizations — `/orgs`

| Method | Path | Purpose | Auth | Role |
| --- | --- | --- | --- | --- |
| GET | `/orgs` | My organizations | ◐ | — |
| POST | `/orgs` | Create (creator becomes owner) | ◐ | — |
| GET | `/orgs/{id}` | Details + plan + usage summary | ● | member |
| PATCH | `/orgs/{id}` | Name, timezone, currency, retention, ai_enabled | ● | admin |
| POST | `/orgs/{id}/deletion-request` | Begin 30-day deletion | ● | owner |
| DELETE | `/orgs/{id}/deletion-request` | Cancel deletion | ● | owner |

### Members & invitations

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/orgs/{id}/members` | List members | member |
| PATCH | `/orgs/{id}/members/{user_id}` | Change role | admin (owner role: owner) |
| DELETE | `/orgs/{id}/members/{user_id}` | Remove member | admin |
| POST | `/orgs/{id}/members/transfer-ownership` | Transfer owner role | owner |
| GET | `/orgs/{id}/invitations` | Pending invitations | admin |
| POST | `/orgs/{id}/invitations` | Invite by email + role | admin |
| DELETE | `/orgs/{id}/invitations/{inv_id}` | Revoke | admin |
| POST | `/orgs/{id}/invitations/{inv_id}/resend` | Re-send (rotates token) | admin |

### Imports

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/orgs/{id}/imports` | List batches | member |
| POST | `/orgs/{id}/imports` | Create batch + presigned upload URL | manager |
| GET | `/orgs/{id}/imports/{bid}` | Status, counts, progress | member |
| POST | `/orgs/{id}/imports/{bid}/uploaded` | Confirm upload; trigger profiling | manager |
| GET | `/orgs/{id}/imports/{bid}/preview` | Columns, samples, suggested mapping | manager |
| PUT | `/orgs/{id}/imports/{bid}/mapping` | Apply mapping | manager |
| POST | `/orgs/{id}/imports/{bid}/validate` | Dry run | manager |
| GET | `/orgs/{id}/imports/{bid}/issues` | Paged row issues | member |
| GET | `/orgs/{id}/imports/{bid}/issues/export` | Signed URL to the error CSV | member |
| POST | `/orgs/{id}/imports/{bid}/commit` | Process (Idempotency-Key) | manager |
| POST | `/orgs/{id}/imports/{bid}/cancel` | Cooperative cancel | manager |
| DELETE | `/orgs/{id}/imports/{bid}` | Delete batch + derived data | admin |
| GET | `/orgs/{id}/imports/{bid}/delete-preview` | **What would be destroyed** | admin |
| GET | `/orgs/{id}/import-templates` | Saved mappings | manager |
| POST | `/orgs/{id}/import-templates` | Save a mapping | manager |
| DELETE | `/orgs/{id}/import-templates/{tid}` | Delete | manager |

`delete-preview` returns `{jobs_deleted, jobs_retained, candidates_deleted, reviews_destroyed}`
and exists so the confirmation dialog can state the cost of the action
([12 §5](12-privacy-and-data-lifecycle.md)).

### Jobs, customers, technicians

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/orgs/{id}/jobs` | List; filter by date, customer, technician, equipment, category, status; full-text `q` | member |
| GET | `/orgs/{id}/jobs/{jid}` | Detail + notes + line items | member |
| GET | `/orgs/{id}/jobs/{jid}/related` | Candidates where this job is prior or follow-up | member |
| PATCH | `/orgs/{id}/jobs/{jid}` | Correct a small set of fields (category, equipment link) | manager |
| GET | `/orgs/{id}/customers` | List/search | member |
| GET | `/orgs/{id}/customers/{cid}` | Detail + locations + equipment + job history | member |
| POST | `/orgs/{id}/customers/{cid}/erase` | GDPR erasure (with preview) | admin |
| GET | `/orgs/{id}/equipment/{eid}` | Detail + service history | member |
| GET | `/orgs/{id}/technicians` | List + rework stats | member |
| GET | `/orgs/{id}/technicians/{tid}` | Detail + job/rework history | manager |
| PATCH | `/orgs/{id}/technicians/{tid}` | Hourly cost, active flag | admin |

`PATCH /jobs/{jid}` is deliberately narrow. Jobs are layer-2 data derived from imports; freely
editing them would be overwritten on the next re-import and would break the "source of truth
is your FSM" positioning. The permitted corrections are link fixes (equipment, category) that
a re-import preserves.

`GET /technicians` returns rates only above the minimum-volume threshold
([12 §7](12-privacy-and-data-lifecycle.md)).

### Rework — candidates and reviews

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/orgs/{id}/rework` | Review queue. Filters: `min_score`, `band`, `status`, `include_suppressed`, `customer_id`, `equipment_id`, `technician_id`, date range. Sort: `-score`, `-days_between`, `-detected_at` | member |
| GET | `/orgs/{id}/rework/{cid}` | Candidate + **full signal breakdown** + both job records | member |
| POST | `/orgs/{id}/rework/{cid}/review` | Confirm / reject / uncertain + category + root cause + note | manager |
| GET | `/orgs/{id}/rework/{cid}/reviews` | Review history (reclassification chain) | member |
| POST | `/orgs/{id}/rework/{cid}/unsuppress` | Override a veto | manager |
| POST | `/orgs/{id}/rework/{cid}/dismiss` | Remove from the queue without judging | manager |
| POST | `/orgs/{id}/rework/manual` | Manually link two jobs as a pair | manager |
| POST | `/orgs/{id}/rework/bulk-review` | Review up to 50 candidates in one call | manager |
| GET | `/orgs/{id}/rework/{cid}/cost` | Current + snapshotted cost breakdown | member |

`GET /rework/{cid}` is the product's most important response. It must return everything the
evidence panel in [07 §5](07-detection-engine.md) renders — signals with contributions,
explanations, and `NOT_EVALUABLE` entries — in one round trip. A UI that has to make four calls
to explain a score will feel slow exactly where trust is being built.

The queue defaults to `status=open` and excludes suppressed candidates. Its date range applies
to the follow-up job's `service_date`; cursor order is the selected descending sort key followed
by candidate ID as the stable tie-breaker.

`POST /rework/manual` matters more than its size suggests: it is how a manager records a
callback the engine missed, which is the only source of **coverage** data in
[07 §8](07-detection-engine.md).

### Detection settings

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/orgs/{id}/settings/detection` | Active rule set + all rules + signal catalogue | manager |
| PUT | `/orgs/{id}/settings/detection` | **Creates a new version**; optionally triggers a re-run | admin |
| GET | `/orgs/{id}/settings/detection/versions` | Version history | admin |
| POST | `/orgs/{id}/settings/detection/preview` | Score a sample against proposed rules **without saving** | admin |
| GET | `/orgs/{id}/detection-runs` | Run history | member |
| POST | `/orgs/{id}/detection-runs` | Trigger a manual run | admin |

`POST /settings/detection/preview` is what makes the weights UI usable: change a weight, see
immediately how the top 20 candidates re-rank. Without it, tuning is blind and users will not
touch it.

### Categories, root causes, cost model

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET / POST | `/orgs/{id}/settings/categories` | List / create rework categories | member / admin |
| PATCH / DELETE | `/orgs/{id}/settings/categories/{cid}` | Update / deactivate | admin |
| GET / POST | `/orgs/{id}/settings/root-causes` | List / create | member / admin |
| PATCH / DELETE | `/orgs/{id}/settings/root-causes/{rid}` | Update / deactivate | admin |
| GET | `/orgs/{id}/settings/cost-model` | Active version | manager |
| PUT | `/orgs/{id}/settings/cost-model` | **Creates a new version** | admin |
| GET | `/orgs/{id}/settings/cost-model/versions` | History | admin |

`DELETE` on a category or root cause **deactivates** rather than deletes, because
`rework_reviews` references them with `ON DELETE RESTRICT` ([04 §13](04-data-model.md)). The
API returns `200` with the deactivated resource, not `204`, to make that explicit.

### Analytics

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| GET | `/orgs/{id}/analytics/summary` | Headline KPIs: rework rate, confirmed count, total cost, trend | member |
| GET | `/orgs/{id}/analytics/trends` | Time series by period | member |
| GET | `/orgs/{id}/analytics/root-causes` | Distribution + cost by root cause | member |
| GET | `/orgs/{id}/analytics/categories` | Distribution by category | member |
| GET | `/orgs/{id}/analytics/technicians` | By technician (volume-gated) | manager |
| GET | `/orgs/{id}/analytics/equipment` | Repeat-offender equipment and models | member |
| GET | `/orgs/{id}/analytics/cost` | Cost breakdown + assumptions used | member |

Every analytics response includes a `basis` object:

```json
{ "basis": { "confirmed_only": true, "period": "2026-Q1", "cost_model_version": 4,
             "jobs_considered": 12840, "candidates_reviewed": 312, "candidates_pending": 47 } }
```

Stating the basis in the payload prevents the most damaging class of analytics
misunderstanding — a manager reading an unreviewed-candidate count as a confirmed callback
rate and taking it to a technician.

### Exports, audit, billing, system

| Method | Path | Purpose | Role |
| --- | --- | --- | --- |
| POST | `/orgs/{id}/exports` | Request an export (Idempotency-Key) | member |
| GET | `/orgs/{id}/exports` | List | member |
| GET | `/orgs/{id}/exports/{eid}` | Status + signed download URL | member |
| GET | `/orgs/{id}/audit` | Filterable audit log | admin |
| GET | `/orgs/{id}/audit/export` | Audit CSV | admin |
| GET | `/plans` | Public plan catalogue | ○ |
| GET | `/orgs/{id}/billing/subscription` | Plan, status, period | owner |
| GET | `/orgs/{id}/billing/usage` | Usage vs. every entitlement | admin |
| POST | `/orgs/{id}/billing/checkout` | **503 in V1** | owner |
| POST | `/orgs/{id}/billing/portal` | **503 in V1** | owner |
| POST | `/billing/webhooks/{provider}` | **Not mounted in V1** | ○ (signature) |
| GET | `/health` | Liveness — no DB call | ○ |
| GET | `/ready` | Readiness — DB + storage reachable | ○ |

`GET /billing/usage` is live in V1 even though billing is not, because entitlements are
enforced from day one and users need to see where they stand.

**Total: ~95 endpoints**, most of them thin list/detail pairs over eight resources.

---

## 3. Shared response shapes

```python
class CandidateSummary(BaseModel):
    id: UUID
    score: Decimal                      # serialized as a string
    band: ScoreBand
    days_between: int
    is_suppressed: bool
    suppression_reason: CandidateSuppressionReason | None
    suppressed_by_signal_key: str | None
    workflow_status: CandidateWorkflowStatus
    prior_job: JobSummary
    followup_job: JobSummary
    customer: CustomerSummary | None
    equipment: EquipmentSummary | None
    current_review: ReviewSummary | None
    top_signals: list[SignalSummary]    # 3 highest contributors, for the list view
    detected_at: datetime


class SignalSummary(BaseModel):
    key: str
    label: str
    outcome: SignalOutcome              # matched | not_matched | not_evaluable
    contribution: Decimal
    explanation: str
    raw_value: dict[str, Any]
```

`top_signals` on the list response is a deliberate denormalization: a review queue where each
row shows *"same equipment · 8 days · $0 invoice"* is triaged far faster than one showing only
a number, and it avoids N+1 detail fetches.

---

## 4. OpenAPI and the frontend contract

FastAPI generates the OpenAPI document. CI runs `openapi-typescript` to emit
`packages/contracts/src/api.d.ts`, and **fails if the generated file differs from the committed
one**. That single check is what keeps a monorepo's frontend and backend honest without
hand-written duplicate types.

Operation IDs come from one application-wide generator that removes the `_endpoint` suffix and
converts each route function name to lower camel case (`list_rework_candidates_endpoint` becomes
`listReworkCandidates`). A regression test enforces uniqueness and readable names. Renaming a
route function is therefore an intentional contract change.

---

## 5. What is deliberately absent from V1

| Not built | Why |
| --- | --- |
| Public customer-facing API | `api_access` entitlement is reserved; needs API keys, docs, stronger rate limits |
| GraphQL | One client, well-understood access patterns |
| Websockets / SSE | Import progress polls every 2 s; adequate and far simpler |
| Bulk job mutation | Jobs are derived data; correcting the source and re-importing is the intended path |
| Nested `?include=` expansion | Detail endpoints return what their screen needs; a generic expansion language is an optimisation for a problem we do not have |
| Search across organizations | Structurally forbidden |
