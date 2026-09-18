# 00 — Overview & Architectural Decisions

**Status:** Phase 0 (design only, no implementation)
**Last updated:** 2026-09-16

---

## 1. What SecondTrip is

SecondTrip is a multi-tenant SaaS **intelligence layer** that sits on top of a service
business's existing job history and surfaces *second trips*: callbacks, rework, warranty
visits, incomplete repairs, misdiagnoses, and recurring service problems.

It is **not** a field-service management system. It does not dispatch, schedule, invoice, or
own the operational record. It ingests a copy of the operational record, analyses it, and
returns explainable findings plus a review workflow that turns machine guesses into
human-confirmed truth.

The first vertical is HVAC. Nothing in the schema, the detection engine, or the API may
encode an HVAC-specific assumption. Vertical specificity lives in **configuration**
(rule sets, category sets, synonym dictionaries, cost models), never in code or columns.

### The product's actual value proposition

A shop owner knows some of their jobs are repeat visits. They do not know *how many*, *which
technicians*, *which equipment brands*, *which root causes*, or *what it costs them*. The
answer lives in their job history, but it is unreadable at scale because nobody labels a job
"this was a callback."

SecondTrip's job is to make that history legible, and to be **believable** while doing it. A
false positive that a manager cannot interrogate destroys trust faster than a missed
detection. This is why explainability is a first-class architectural requirement (§14 of the
brief, and [07-detection-engine.md](07-detection-engine.md)) rather than a feature.

---

## 2. The one idea that shapes everything else

Four categories of data exist in this system, and they must never be conflated:

| Layer | Examples | Who writes it | Can it be destroyed and rebuilt? |
| --- | --- | --- | --- |
| **1. Source / raw** | uploaded CSV file, `import_rows.raw_data` | The customer | No — it is evidence |
| **2. Normalized operational** | `jobs`, `customers`, `equipment` | Import pipeline | Yes, from layer 1 |
| **3. Derived analytical** | `rework_candidates`, signals, scores, embeddings, AI analyses | Detection pipeline | **Yes — must be safe to wipe and recompute** |
| **4. Human-confirmed truth** | `rework_reviews`, chosen category, chosen root cause | A manager | **No — never overwritten by a machine** |

Every design decision in this specification traces back to keeping these four separate.

The trap this avoids: a naive design stores a `jobs.is_callback` boolean that the detector
writes and the manager also edits. Six weeks later you change a detection weight, rerun, and
silently destroy months of human labelling. That data is the most valuable asset the product
accumulates — it is the training/evaluation set that lets you prove the detector works, and
it is the only reason a customer would resist churning.

**Rule:** the detection pipeline may freely delete and rebuild anything in layer 3. It may
never write to layer 4. Layer 4 rows survive rule changes, re-imports, and model swaps
because they are anchored to a *stable job-pair identity*, not to an ephemeral candidate row.
See [07-detection-engine.md §2](07-detection-engine.md).

---

## 3. Confirmed decisions (answered in Phase 0 kickoff)

| Decision | Choice | Consequence |
| --- | --- | --- |
| Authentication | Application-managed in FastAPI; opaque session token in an httpOnly cookie | No vendor cost, one authorization source of truth, revocation is a row delete. We build verification/reset/invite flows ourselves. See [03-authentication.md](03-authentication.md) |
| Year-one scale target | ≤ ~100k jobs per organization | Plain Postgres tables, no partitioning, in-process candidate generation. Partition triggers documented, not built. See [04-data-model.md §15](04-data-model.md) |
| V1 detection scope | Stages 1–4 + 6 (deterministic + embeddings + human review). Stage 5 (LLM classification) designed and feature-flagged **off** | Near-zero AI spend at launch; description similarity still available, which is what separates a real callback from two unrelated visits |

---

## 4. Architectural decision record

Each decision below states the choice, the reasoning, and what was rejected. Later agents
should treat these as binding unless a documented reason to revisit appears.

### ADR-001 — Modular monolith, not microservices

**Choice:** One FastAPI application, internally partitioned into domain modules with enforced
dependency rules. One Postgres database. One deployable backend artifact.

**Why:** A single maintainer. Every service boundary is a distributed-systems tax —
serialization, partial failure, eventual consistency, N deploy pipelines — paid in exchange
for independent scaling and team autonomy that a solo project cannot spend. The domain
boundaries we need (identity, imports, detection, billing) are enforceable at the module
level with a lint rule, at a fraction of the cost.

**Rejected:** microservices, service mesh, separate detection service.

**Revisit when:** the detection pipeline's CPU profile genuinely starves request handling and
vertical scaling is exhausted — extract *detection workers* first, not the API.

---

### ADR-002 — PostgreSQL is the queue, the vector store, and the analytics store

**Choice:** No Redis, no Kafka, no Celery, no Elasticsearch, no Pinecone/Weaviate in V1.
Background jobs run on a `background_jobs` table claimed with `FOR UPDATE SKIP LOCKED`.
Embeddings live in a `pgvector` column. Analytics are SQL aggregates over Postgres.

**Why:** Each of those services costs money at idle, and at our scale each solves a problem we
do not have. `SKIP LOCKED` is a correct, well-understood work-queue primitive. pgvector's
exact search over a few hundred thousand rows is comfortably fast, and — critically — most of
our vector work is *pairwise comparison of two known rows*, which needs no index at all.

**Rejected:** Redis + Celery/Dramatiq, dedicated vector DB, OpenSearch.

**Revisit when:** the specific triggers in [09-background-jobs.md §9](09-background-jobs.md)
and [08-ai-and-embeddings.md §5](08-ai-and-embeddings.md) are hit.

---

### ADR-003 — Tenant isolation is enforced in three independent layers

**Choice:** (1) Postgres Row-Level Security on every tenant-owned table, with the application
connecting as a **non-owner role** so RLS cannot be bypassed; (2) a repository layer that
requires an explicit `TenantContext` and injects `organization_id` into every query; (3) API
dependencies that resolve and verify membership before a handler runs.

**Why:** Layers 2 and 3 are where bugs happen — a forgotten `WHERE organization_id = ...` in a
hand-written join, a background job that loses its tenant context, an `/jobs/{id}` lookup by
primary key alone. Layer 1 is the backstop that turns those bugs from a data breach into an
empty result set. RLS is essentially free in Postgres; the only real cost is remembering that
**a table's owner bypasses its own RLS policies by default**, which is why the app role must
not own the tables.

**Rejected:** relying on the repository layer alone (one missed filter is a breach);
schema-per-tenant (migration and connection-pool cost that does not pay for itself below
thousands of tenants); database-per-tenant (absurd at this scale).

See [02-multi-tenancy.md](02-multi-tenancy.md).

---

### ADR-004 — The detection engine must work with the AI provider switched off

**Choice:** Stages 1, 2, 4 and 6 are pure deterministic SQL and Python. Stage 3 (embeddings)
degrades to "similarity signal unavailable" if the provider is down. Stage 5 (LLM) is optional
and off by default.

**Why:** Two independent reasons. **Reliability** — an OpenAI outage must not stop a customer
importing a file and seeing findings. **Credibility** — "the AI says so" is not an argument a
manager can take to a technician. A score built from *8 days apart, same equipment, $0
invoice* is. The LLM's role is to add a readable narrative and a root-cause hypothesis on top
of a score that already stands on its own.

**Rejected:** an LLM-first pipeline that classifies every pair.

---

### ADR-005 — Configuration in the database, logic in code

**Choice:** `detection_rules` rows store `signal_key`, `weight`, `params`, `enabled`, and a
rule kind. The *evaluator* for each `signal_key` is a Python class registered in a signal
registry. The database never stores executable logic or an expression language.

**Why:** Organizations need to tune weights, windows, and thresholds without a deploy. They do
not need to author arbitrary predicates, and giving them a DSL means building a parser,
sandbox, and injection surface for a capability nobody asked for. If a genuinely new signal is
required, that is a code change plus a migration row — a day of work, not an architecture.

**Rejected:** a rules DSL / expression evaluator stored in the DB; hard-coded weights in
Python.

---

### ADR-006 — Rule sets are immutable versions, not mutable rows

**Choice:** Editing detection settings creates a **new** `detection_rule_set_version`. Every
candidate score records the version that produced it.

**Why:** Without this, a score is unreproducible and unexplainable the moment settings change —
the UI would show "8 days apart, +20" next to a total that was computed when the weight was
30. It also makes the audit trail meaningful and lets us answer "did detection quality improve
after the change?"

---

### ADR-007 — Monorepo

**Choice:** One repository containing `frontend/`, `backend/`, and shared contract types.

**Why:** A single maintainer making cross-cutting changes (add an API field, consume it in the
UI) should make one commit, one PR, one CI run. Two repos buy independent release cadence,
which one person does not need, at the cost of version skew between the API and its only
client.

See [16-repository-structure.md](16-repository-structure.md).

---

### ADR-008 — Providers behind protocols, adapters at the edge

**Choice:** `AIProvider`, `StorageProvider`, `EmailProvider`, `BillingProvider` are
`typing.Protocol` definitions in `app/providers/<kind>/base.py`. Domain services depend only
on the protocol. Concrete adapters (OpenAI, R2, Resend) are constructed once in composition
root and injected.

**Why:** This is the smallest abstraction that delivers the brief's requirement (no domain
dependency on OpenAI/Stripe) without building an enterprise plugin framework. The protocols
are narrow — four to five methods each — and shaped by *our* needs, not by the vendor's SDK.

**Anti-goal:** do not build a generic "provider registry with dynamic loading." Two
implementations of each protocol (real + fake-for-tests) is the expected count.

---

### ADR-009 — Cursor pagination, RFC 9457 errors, `/api/v1` prefix

See [15-api-design.md](15-api-design.md). Offset pagination is wrong for a dataset that is
actively being imported into (rows shift under the reader); cursor pagination costs one extra
composite index and removes the class of bug entirely.

---

### ADR-010 — UUIDv7 primary keys, generated in the application

**Choice:** All primary keys are `uuid` columns holding UUIDv7 values generated in Python.

**Why:** Sequential integers are enumerable, which turns every authorization bug into a
scraping opportunity and leaks business volume in URLs. Random UUIDv4 fixes that but scatters
B-tree inserts across the whole index, hurting write throughput and index locality on our
hottest tables. UUIDv7 is time-ordered, so inserts stay at the right edge of the index like a
sequence, while remaining unguessable. Generating in the application means an object has its
identity before it is flushed, which simplifies constructing related rows in one unit of work.

**Note for implementers:** `uuidv7()` as a built-in is Postgres 18+; assume Neon is on 17 and
generate in Python (`uuid6` package or a vendored 30-line implementation). Keep
`gen_random_uuid()` as the column default purely as a safety net for out-of-band inserts.

---

### ADR-011 — One design system, one Next.js app; no separate `packages/ui`

**Choice:** Marketing and dashboard are route groups inside one Next.js application, sharing
one Tailwind config, one `tokens.css`, and one `components/ui/`. There is no published or
workspace-local design-system package.

**Why:** A shared package earns its cost when there is a second consumer to isolate it from.
There is one frontend app; splitting tokens into a package would add a build step and a
version-sync problem in exchange for nothing. The monorepo already made this call once for
`packages/contracts` — one shared package, kept to one, because package proliferation is this
project's specific failure mode at solo-maintainer scale ([16 §1](16-repository-structure.md)).

**Rejected:** `packages/ui` / `packages/design-tokens` as a workspace package.

**Revisit when:** a second frontend consumer genuinely exists (a native app, an embeddable
widget). The components are written with no route-group-specific imports, so extraction at
that point is mechanical.

See [22-design-system.md](22-design-system.md).

---

## 5. Non-goals for V1

Explicitly out of scope, listed so later agents do not "helpfully" add them:

- Any FSM/CRM integration (ServiceTitan, Jobber, Housecall Pro). Designed for, not built.
- Payment processing. Plans and entitlements exist; no checkout.
- Real-time collaboration, websockets, live dashboards.
- Mobile app.
- Multi-currency per organization (single currency per org, stored explicitly so the upgrade is additive).
- "Ask SecondTrip" natural-language querying. The embedding infrastructure anticipates it; the feature is not V1.
- SSO/SAML, SCIM.
- Public API for customers (API access is an entitlement key reserved for later).

---

## 6. Document map

| Doc | Covers |
| --- | --- |
| [01-system-architecture.md](01-system-architecture.md) | Runtime topology, deployment, request/processing flows, cost model |
| [02-multi-tenancy.md](02-multi-tenancy.md) | Tenant boundary, RBAC, RLS, cross-tenant threat surface |
| [03-authentication.md](03-authentication.md) | Sessions, passwords, verification, invitations, CSRF/CORS |
| [04-data-model.md](04-data-model.md) | Every entity, column, key, index, delete behaviour |
| [05-erd.md](05-erd.md) | Mermaid ERDs (core, operational, detection/system) |
| [06-csv-ingestion.md](06-csv-ingestion.md) | Upload → map → validate → commit → process |
| [07-detection-engine.md](07-detection-engine.md) | The six-stage pipeline, signals, scoring, explainability |
| [08-ai-and-embeddings.md](08-ai-and-embeddings.md) | AIProvider protocol, pgvector strategy, RAG boundaries |
| [09-background-jobs.md](09-background-jobs.md) | Postgres queue, retries, locking, graduation triggers |
| [10-storage.md](10-storage.md) | StorageProvider protocol, R2 keys, signed URLs |
| [11-security-threat-model.md](11-security-threat-model.md) | Threats, mitigations, prompt injection |
| [12-privacy-and-data-lifecycle.md](12-privacy-and-data-lifecycle.md) | Deletion, retention, export, PII minimisation |
| [13-audit.md](13-audit.md) | Audit event model and field allowlists |
| [14-billing-and-entitlements.md](14-billing-and-entitlements.md) | Plans, entitlements, BillingProvider |
| [15-api-design.md](15-api-design.md) | V1 endpoint surface, conventions, versioning |
| [16-repository-structure.md](16-repository-structure.md) | Monorepo layout, module rules |
| [17-configuration.md](17-configuration.md) | Environment variable specification |
| [18-observability.md](18-observability.md) | Logging, errors, metrics, AI cost tracking |
| [19-testing-strategy.md](19-testing-strategy.md) | What to test and what not to |
| [20-frontend-and-seo.md](20-frontend-and-seo.md) | Next.js structure, SEO/AEO architecture |
| [21-implementation-sequencing.md](21-implementation-sequencing.md) | Build order with exit criteria |
| [22-design-system.md](22-design-system.md) | Design tokens, component inventory, marketing + dashboard layout — shared by both surfaces |
