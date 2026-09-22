# PLAN.md — SecondTrip

Durable task state. Read this and `CLAUDE.md` before starting any feature or fix.
Source of truth is files, not chat history.

**Last updated:** 2026-09-22
**Current phase:** Phase 6 review workflow is in progress. Its core APIs and first thin review
UI are complete. Phase 5's real-data quality review and Phase 4's manual Excel exit check remain.

---

## Goal

Build SecondTrip: a multi-tenant SaaS that detects callbacks, rework, warranty visits and
recurring service problems in a service business's historical job records, explains why each
was flagged, and turns manager judgements into confirmed truth and business-impact analytics.

First vertical HVAC; nothing HVAC-specific in code or schema. CSV ingestion first; FSM
integrations designed for but not built.

Full specification: [`docs/architecture/`](docs/architecture/) — 23 documents,
index in [`00-overview-and-decisions.md §6`](docs/architecture/00-overview-and-decisions.md).

---

## Steps

### 0. Architecture & technical specification — ✅ **DONE**

Complete design covering system architecture, multi-tenancy, auth, data model, ERDs, CSV
ingestion, deterministic detection, deferred AI research, background jobs, storage, threat model, privacy,
audit, billing/entitlements, API, repo structure, configuration, observability, testing, SEO,
design system, and sequencing.

### 1. Design system foundation — ✅ **DONE**

The shared visual language both the marketing site and the dashboard build on: tokens
(`frontend/src/styles/tokens.css`, Tailwind v4 `@theme` — no `tailwind.config.ts` needed),
19 primitive components (`components/ui/`), brand/logo, two chart wrappers, and the two layout
shells (marketing nav/footer, dashboard sidebar/topbar with a drawer below 1024px). No product
pages — a component library, verified against `/dev/tokens` (`noindex`).

**Verified live, not just statically checked:** `pnpm install`, `pnpm typecheck`, `pnpm lint`,
and `pnpm build` all pass clean; `next start` and `next dev` were both booted and `curl`'d at
`/` and `/dev/tokens` (`200` on all four); the compiled CSS chunk was fetched and inspected
directly to confirm real token hex values, generated utility classes, `color-mix()` with
automatic `@supports` fallbacks, and self-hosted Manrope `@font-face` rules are actually
present in the output — not just present in source.

Real ecosystem findings from doing this for real (recorded in
[21 Phase 1](docs/architecture/21-implementation-sequencing.md) so they aren't rediscovered):
TypeScript 7 isn't yet supported by `typescript-eslint` (pinned to 6.0.3); ESLint 10 isn't yet
supported by `eslint-config-next`'s bundled plugins (pinned to 9.39.5); `eslint-config-next@16`
ships a native flat-config array and must **not** be wrapped in `@eslint/eslintrc`'s
`FlatCompat`.

Not yet done: an automated contrast/a11y tool pass (the palette was hand-verified against the
WCAG formula, which is evidence but not a substitute) — do this before Phase 8.

Detail + exit criteria: [21 Phase 1](docs/architecture/21-implementation-sequencing.md). Full
spec: [22-design-system.md](docs/architecture/22-design-system.md).

### 2. Foundation — ✅ **DONE**

`backend/` scaffold (uv, Python 3.12), settings, logging, async SQLAlchemy + Alembic, **RLS
and the non-owner app role**, `TenantContext` + `TenantRepository`, RFC 9457 error handling,
cursor pagination, UUIDv7 generation, root-level Docker Compose Postgres, CI workflows.

**Verified live:** fresh Postgres container → `alembic upgrade head` → RLS confirmed
enabled+forced at the `pg_class` level → real `uvicorn` process → `curl`'d `/health` and
`/ready` (both 200, `/ready` genuinely hit the database) → structured access logs observed
with correct `request_id` correlation. 23 tests pass against the live database (not mocked),
including 5 that exercise `secondtrip_app` directly over raw SQL. `ruff`, `mypy --strict`,
and `import-linter` (3 contracts) all pass on 34 source files.

**A real bug found by testing the database directly:** `set_config(key, NULL, true)` produces
an empty string, not SQL NULL, and `''::uuid` raises rather than comparing false — the
original RLS policy only degraded safely for a GUC that was *never* set, not one explicitly
cleared. Fixed with `NULLIF(..., '')` in `migrations/rls_helpers.py`, propagated to
[02-multi-tenancy.md §2](docs/architecture/02-multi-tenancy.md), covered by a named
regression test. See D35.

Detail + exit criteria: [21 Phase 2](docs/architecture/21-implementation-sequencing.md).

### 3. Identity & tenancy — ✅ **DONE**

Users, sessions, orgs, memberships, invitations, RBAC, email flows, CSRF/CORS, audit service,
app shell (built on Step 1's `DashboardLayout`).

#### Continuation scope from the current worktree

The worktree contains an uncommitted partial implementation under `backend/app/modules/`,
`backend/app/api/`, `backend/app/core/`, `backend/app/providers/email/`, and migration
`52ffdd774e8b_identity_organizations_audit.py`. Those changes were preserved and completed
with forward repairs; the uncommitted state is intentional in this workspace.

#### Completed in the current continuation

- Applied forward repairs through Alembic head `a47d9c3e1f20`: tenant foreign keys and checks,
  soft-delete-safe email uniqueness, email-change/rate-limit tables, split SELECT/write RLS,
  email-bound pending-invitation lookup, forced-RLS privilege checks, append-only audit grants,
  and the deferred serialized active-owner guard.
- Completed session idle/absolute expiry and active-user checks, atomic token locking, failed
  login persistence, verification resend, profile/password/email changes, session revocation,
  canonical logout-all, invitation resend/rotation/acceptance locking, pending invitations,
  and Postgres-backed rate limits with email delivery outside the main transaction.
- Replaced stale smoke-table security tests with live identity/tenancy proofs. Final backend
  verification: 33 tests pass; Ruff, mypy, import-linter, and `alembic check` pass.
- Added the audit allowlist/repository/schemas, admin-only cursor reads, safe CSV export,
  API security headers, private no-store tenant responses, and `Retry-After` on rate limits.
- Added browser routes for `/`, `/login`, `/register`, `/forgot-password`, `/verify`,
  `/reset-password`, `/accept-invite`, `/confirm-email-change`, and `/app/dashboard` with
  typed API/CSRF handling, a responsive app shell, an organization switcher, and a Next.js
  16 session-presence proxy. Frontend lint, typecheck, and production build pass.

#### Exit evidence — 2026-09-19

- Two isolated browser contexts completed signup → email verification → organization creation
  → invitation preview → invitation acceptance → dashboard access.
- Password reset invalidated every previous owner session; the reset-created session worked.
- Removing a member immediately made organization and member reads return 404; an inaccessible
  second organization also returned 404, with no cross-tenant data leakage.
- A sole-owner removal attempt returned the expected `409 LAST_OWNER` conflict.
- Owner audit reads and CSV export returned `private, no-store`; member audit reads returned
  `403`; malformed cursors returned `422 INVALID_CURSOR`.
- Email-change confirmation was exercised through the live console-email link and refreshed the
  session with the new address.
- Final validation: 34 backend tests, the route audit, Ruff, mypy, import-linter, Alembic check,
  frontend lint, typecheck, and production build all pass. The local API and frontend remain
  running with a disposable demo workspace seeded for inspection.

### 4. Ingestion — 🟨 **IN PROGRESS**

Background job queue, storage provider, operational schema, import pipeline (profile → map →
validate → commit → process), normalization, entity resolution, error reporting, entitlements,
import wizard UI, demo seed data.

#### Foundation completed — 2026-09-19

- Added the architecture-defined operational/import/commercial schema through Alembic head
  `9ee6a75b5acd`: native enums, partial indexes, tenant relationships, API idempotency,
  background jobs, plans, subscriptions, overrides, and usage counters.
- Enabled and forced RLS on all 18 new tenant/worker tables. Queue and billing-event access
  use an explicit transaction-local worker context; ordinary sessions remain fail-closed.
- Seeded free/pro/business plus all 48 documented entitlement values.
- Added vendor-neutral local/in-memory storage and noop billing providers, signed local
  upload/download URLs, key/filename hardening, and storage-aware readiness.
- Added the PostgreSQL queue runtime: transactional enqueue, active-job deduplication,
  `SKIP LOCKED` claims, Pydantic payload validation, heartbeat, cancellation, stale recovery,
  timeout/retry handling, graceful shutdown, and the idempotent `storage.cleanup` handler.
- Verification: 58 backend tests pass against live Postgres; Ruff, strict mypy,
  import-linter, Alembic drift, frontend lint/typecheck, and production build all pass. The
  restarted local API (`:8000`) and frontend (`:3000`) are live; `/health` and storage-aware
  `/ready` return 200. The disposable local demo login was recreated after destructive DB
  security tests.

#### Queue correctness completed — 2026-09-19

- Proved two simultaneous workers claim disjoint batches while both transactions retain their
  locks, exercising PostgreSQL `FOR UPDATE SKIP LOCKED` through the real app role.
- Proved domain state and its queued side effect roll back atomically, active idempotency keys
  deduplicate, stale final attempts fail, and queued cancellations never execute.
- Proved tenant context reconstruction, successful completion, bounded retry+jitter,
  exhausted attempts, handler timeouts, malformed payloads as permanent failures, cooperative
  in-flight cancellation, and graceful shutdown.
- Hardened worker IDs, restart behavior, heartbeat failure isolation, poll-loop survival, and
  configuration bounds. Persisted errors contain only exception classes, not provider or
  imported-data details.

#### CSV primitives completed — 2026-09-19

- Added a bounded streaming profiler that retains at most 1 MiB while enforcing file and row
  limits over the full stream. It handles UTF-8/UTF-16 BOMs, tab/comma/semicolon/pipe dialects,
  mixed line endings, duplicate headers, type samples, ragged rows, uncertain encodings, and
  clear rejection of workbooks, compressed files, null bytes, malformed CSV, and hard limits.
- Added the complete 38-field mapping catalogue, versioned/strict mapping document, stable
  template signatures, synonym and type-gated fuzzy suggestions, and source-column validation.
- Added source-neutral normalization for ambiguous dates and timezone-aware datetimes, Decimal
  money, booleans, Unicode text, names, phones, natural identity keys, plus the immutable
  `SourceRecord` integration boundary. Equipment remains unresolved instead of being invented.
- Centralized formula-injection protection in `shared/csv_safety.py`, including tab/CR prefixes,
  and added a committed adversarial fixture corpus with generated byte/size edge cases.
- Verification: 112 backend tests pass; Ruff, strict mypy, import-linter, Alembic drift, and the
  dependency lock all pass.

#### Upload, profile, preview, and mapping completed — 2026-09-19

- Added tenant-scoped, cursor-paged import create/list/detail endpoints, signed upload creation,
  independent object existence/size/SHA-256 verification, byte-identical duplicate detection
  with explicit override, and strict state transitions through mapping confirmation.
- Registered the real idempotent `import.profile` worker. It streams from storage, persists
  encoding/dialect/columns/samples/row estimate/profile issues, reports clean permanent failures,
  and moves successful batches to `awaiting_mapping`.
- Added exact template-signature lookup plus synonym/fuzzy preview suggestions, source-column
  validation, mapping snapshots, template usage accounting, audit events, and manager/member
  permissions matching the API matrix.
- Added the architecture-defined entitlement service boundary with free-plan fallback,
  subscription/override resolution, organization-local monthly periods, transactional usage
  counters, and advisory-lock quota reservation that remains correct under concurrent creates.
- Added forward migration `b31c8f6d2a40` for persisted profile warnings. Capability tokens in
  local signed-upload paths are redacted from both structured and Uvicorn access logs.
  Verification: 120 backend tests pass; Ruff, strict mypy, import-linter, Alembic drift, and
  lock checks pass.

#### Dry-run validation and error reporting completed — 2026-09-19

- Added the registered `import.validate` worker with an anonymous disk-backed, memory-bounded
  reader. File and row ceilings are enforced during the storage stream; parsing, date-order
  inference, normalization, duplicate/filter handling, and persistence run in bounded chunks.
- Every source row now lands in `import_rows` with its 1-based source row number, immutable raw
  data, deterministic hash, status, and stable structured issue codes. Validation constructs
  the source-neutral `SourceRecord` boundary but does not write operational entities.
- Added transactional validation enqueue, deterministic retry/rebuild behavior, cooperative
  batch/job cancellation, exact progress and outcome counters, cursor-paged issue reads, and
  the registered `import.error_report` worker.
- Error reports are streamed to private storage, every cell passes through `csv_safe`, and the
  API returns only a short-lived signed download URL. Capability tokens remain redacted from
  structured and Uvicorn access logs.
- Verification: 127 backend tests pass; Ruff, strict mypy, all 3 import contracts, Alembic drift,
  dependency lock, and diff checks pass. A real local HTTP flow completed upload → profile →
  mapping → validation → paged issues → signed report download with 7 rows and formula payloads.

#### Commit and operational processing completed — 2026-09-19

- Added required `Idempotency-Key` handling for import commits with transactional request
  claims, stable request hashing, exact response replay, and conflict detection for key reuse.
- Commit now serializes concurrent-import admission, re-checks and reserves `jobs_imported`
  using the actual importable row count, transitions the batch, audits the request, and
  enqueues exactly one `import.process` job in the same transaction.
- Added checkpointed operational processing from persisted validation rows. Resolution follows
  customer → location → equipment → technician → service category → job → note, enriches
  existing entities without blanking known values, never invents equipment, and treats mapped
  job fields as authoritative.
- External and natural job identities are tenant-scoped and replay-safe. Re-imports update
  existing jobs, maintain created/updated counters, and natural-key collisions add a
  `POSSIBLE_DUPLICATE` warning while still updating the job.
- Each chunk commits its entity writes, row/job links, and batch checkpoint atomically. A
  simulated interruption after the first chunk resumed through the real queue and produced the
  exact entity/job counts; cancellation retains committed chunks.
- Verification: 131 backend tests pass. Ruff, strict mypy, all import contracts, dependency
  lock, Alembic drift, and diff checks pass. Integration coverage includes exact-file re-import,
  changed authoritative re-import, interruption/resume, missing equipment, notes, quota rollback,
  and HTTP idempotency storage semantics.
- Real local HTTP verification also passed: registration/login → organization creation → signed
  upload → profiling → mapping → validation → commit → processing. Batch
  `01a0ba20-9143-76d1-a77b-2c2ea990504b` in organization
  `01a0ba20-9111-7697-badb-7c1fccf999ca` completed 2/2 rows with 2 created jobs. Direct database
  verification found 2 customers, 2 locations, 1 equipment record (the identifier-free row
  correctly stayed unlinked), 2 technicians, 2 categories, 2 jobs, 2 notes, 2 linked source
  rows, and `jobs_imported = 2`. Replaying `slice-f-live-commit` returned the exact original
  response without another job or usage charge. The local API remains available on `:8000`.

Detection chaining remains intentionally dormant until Phase 5 registers `detection.run`;
enqueueing an unregistered job now would turn a successful import into a permanent queue
failure. Phase 5 must add that enqueue in the final import chunk transaction.

#### Import application UI completed — 2026-09-19

- Added the shared authenticated `/app/*` shell and organization-aware navigation, preserving
  the existing dashboard while moving session, role, organization switching, and logout into
  one reusable boundary.
- Added `/app/imports`, `/app/imports/new`, and `/app/imports/[id]`: cursor-paged history,
  signed CSV upload, duplicate confirmation, the complete 38-field mapping workbench, source
  preview, full-file validation, paged row issues and error-report download, idempotent commit,
  two-second status polling, cancellation, progress, and terminal batch results.
- Manager mutations are role-gated while members retain read access. Commit idempotency keys
  survive refresh in local storage, and login return paths accept only same-origin `/app/*`
  destinations.
- Extended import batch detail with the applied mapping, duplicate lineage, safe report-ready
  state, cancellation state, and processing timestamps; private storage keys remain server-only.
- Verification: frontend lint, strict typecheck, production build, and diff checks pass. A live
  browser run completed upload → mapping → validation → issue review → commit → processing on
  desktop and mobile. An independent design evaluation found targeted accessibility/responsive
  issues in attempt 1; all were corrected, and attempt 2 passed with no confirmed new defects.
  The local API (`:8000`) and frontend (`:3000`) remain available for inspection.

#### Performance proof and deterministic HVAC demo completed — 2026-09-20

- Added a deterministic 39-column `hvac-v1` generator shared by local seed and benchmark tooling.
  The performance shape is 50,000 jobs, 10,000 fictional customers/locations, equipment for 90%
  of customers, 25 technicians, eight categories, and four years of service dates.
- Replaced per-row operational writes with bounded owning-module bulk APIs, retained sorted
  advisory locks and 500-row transactions, persisted the validated source-neutral record, and
  eliminated duplicate job-ID recovery queries. Existing replay, collision, resume, note,
  aggregate, and RLS behavior remains covered.
- Three separately isolated full lifecycle trials all passed the strict `<120s` gate with exact
  cardinalities and zero updates/errors/warnings/skips: **109.29s, 93.70s, 112.31s**
  (min/median/max **93.70/109.29/112.31s**). Fixture: 50,000 rows, 23,417,798 bytes,
  SHA-256 `3d95eb4f6139a9f2df15799abe353003edcf78fe889bb64fb292889eed409081`.
  Environment: Python 3.12.13, PostgreSQL 17.11, 16 CPUs, 31,435 MiB RAM, 500-row chunks;
  max process RSS 213,544 KiB. Raw evidence is local at
  `/tmp/secondtrip-import-50k-result.json` and is intentionally not committed.
- `make seed-demo` imports 96 fictional HVAC jobs into reserved tenant
  `secondtrip-hvac-demo`: 12 callback pairs, eight maintenance veto pairs, four planned
  multi-visit veto pairs, eight unrelated pairs, and 32 standalone jobs. A second run was a
  verified no-op with stable organization/job IDs; ground truth remains external to operational
  rows in `backend/seeds/data/hvac_demo_expectations.json`.

The literal Microsoft Excel error-report safety check remains unchecked. Phase 5 implementation
has started at the user's direction, but that does not substitute for or close the named manual
Phase 4 exit criterion.

#### Excel safety handoff prepared — 2026-09-21

- Generated `/tmp/secondtrip-excel-safety-check.csv` through the application error-report
  writer with one row for each dangerous prefix: `=`, `+`, `-`, `@`, tab, and carriage return.
- As supporting evidence only, LibreOffice imported the CSV and saved a 42-cell workbook whose
  worksheet XML contained zero formula nodes. Microsoft Excel is not installed locally, and
  Excel for the web requires Microsoft authentication, so the named manual exit criterion stays
  unchecked until the CSV is opened in Microsoft Excel and visually confirmed.

### 5. Detection engine (no UI) — ⬜

Rule sets, signal registry, candidate generation, scoring, explainability persistence,
CLI proof. **Gate: results must be plausible on real data
before Step 6 begins.**

#### Pure scoring and canonical pairing foundation completed — 2026-09-21

- Added the architecture-defined `SignalOutcome` / `SignalResult` contract, `RuleKind` and
  `ScoreBand` enums, immutable scoring inputs, score outcomes, and fixed band boundaries.
- The pure `Decimal` calculator excludes `NOT_EVALUABLE` signals from numerator and
  denominator, applies vetoes before arithmetic, supports gates and order-independent
  multipliers, clamps normalized scores to 0–100, and fails closed when signal and rule keys
  differ.
- Added the sole Python canonical pair constructor using
  `(service_date, COALESCE(started_at, service_date midnight UTC), id)`, including null-start,
  same-day, and self-pair protections.
- Verification: 20 focused tests; full backend suite 154 tests; Ruff, strict mypy, and all three
  import-linter contracts pass. The full suite requires `DEBUG=false` in this shell because the
  host exports the invalid unrelated value `DEBUG=release`.

#### Detection persistence and default configuration completed — 2026-09-22

- Added the six Phase 5 tenant tables: immutable rule-set versions and rules, detection runs,
  stable pair-identity candidates, per-run signal evidence, and score history. Composite tenant
  foreign keys protect all candidate/run/rule relationships, while candidate identity remains
  upsertable on `(organization_id, prior_job_id, followup_job_id)`.
- Added the global 15-signal catalogue and an idempotent version-1 default rule set for API,
  demo, and benchmark organization creation. The migration backfills every existing active
  organization; environment defaults are copied into the immutable row rather than read during
  scoring.
- Resolved a specification inconsistency: persisted evidence now stores the native three-state
  `signal_outcome` (`matched`, `not_matched`, `not_evaluable`) instead of a lossy `matched`
  boolean. Updated the authoritative data model, ERD, module layout, and domain glossary.
- All six tenant tables have forced RLS and four operation-specific policies; the migration was
  verified downgrade → upgrade, Alembic reports no schema drift, and the live demo has one
  active rule set with all 15 rules.
- Verification: 26 focused persistence/scoring tests; full backend suite 165 tests; Ruff,
  strict mypy across app/tests/seeds, and all import-linter contracts pass. Live API `/ready`
  and frontend `/login` both return 200.

#### Blocked candidate generation completed — 2026-09-22

- Kept the implementation deliberately small: one named-bind SQL query for blocking and
  canonical ordering, plus one async runner that streams and upserts in bounded 500-row chunks.
  No generic query framework or repository layer was added.
- Candidate selection covers shared customer, location, or equipment; completed and unknown
  statuses; inclusive date-window boundaries; deterministic same-day ordering; tenant and
  soft-delete filters; and the configured per-prior-job follow-up guard.
- Stable `ON CONFLICT` upserts preserve candidate IDs across reruns while refreshing denormalized
  pair data and current run/rule references. The runner reports exact created and updated counts.
- The real-Postgres integration test covers null start times, same-day ordering, 30/31-day
  boundaries, cancelled exclusion, equipment-only matching, cross-tenant isolation, fan-out,
  tiny chunks, and identity-preserving reruns.
- Verification: full backend suite 166 tests; Ruff, strict mypy across app/tests/seeds, and all
  three import-linter contracts pass. A live run through the RLS-bound application role evaluated
  24 demo pairs and created 24 candidates for run
  `01a0c839-6a9b-7163-b0cd-8d4d073e5c82`.

#### Deterministic signals, evidence, and scoring completed — 2026-09-22

- Implemented the complete 15-key registry with pure evaluators for entity identity, temporal
  bands, commercial and warranty facts, repeated parts, recurrence density, semantic degradation,
  and both categorical vetoes. Missing facts produce `NOT_EVALUABLE`, never a false non-match.
- Added one bounded coordinator: it reads 500 candidates at a time, bulk-loads equipment, part,
  and recurrence context, calls the existing pure scorer, and upserts evidence and score history.
  Evidence writes are capped at 1,000 rows per statement to stay below PostgreSQL parameter limits.
- Every persisted evidence row freezes its outcome, strength, raw value, configured weight,
  contribution, and reviewer-facing explanation. Re-running the same run updates those stable
  unique rows instead of duplicating them.
- Corrected the fictional demo to `hvac-v2`: maintenance returns now fall inside the configured
  30-day detection window, while planted unrelated visits retain the customer blocking key but
  use a different location, unit, and technician.
- Verification: full backend suite 177 tests; Ruff, strict mypy across 189 files, and all three
  import-linter contracts pass. The RLS-bound live proof created and scored 32 candidates with
  480 evidence rows and 32 history rows. All top-decile results were callbacks (scores
  93.10–94.29), all 8 maintenance and 4 planned visits were veto-suppressed, and all unrelated
  pairs scored 22.86–27.59 below the configured 40-point surface threshold. Live run:
  `01a0c85d-bd89-7c01-a46f-1338149c0b77`.

#### Detection orchestration and architecture alignment completed — 2026-09-22

- Added one transactional `detection.run` path for queued/running/completed/failed/cancelled
  lifecycle, candidate generation, deterministic scoring, exact counters, cancellation, and
  automatic post-import enqueue. The local `make detect ORG=...` proof uses that same queue and
  handler instead of a second execution path.
- Added explicit candidate suppression causes. Rule vetoes persist `signal_veto` plus the signal
  key; pairs that leave a rerun's window persist `out_of_window` without deleting the stable
  candidate or its future reviews. A real-Postgres regression proves the candidate ID survives.
- Enforced sibling-module public boundaries with a fourth import-linter contract. Detection now
  consumes `jobs/read_models.py` and customer/job services rather than sibling ORM models or
  repositories; the signal catalogue is checked against the database at startup.
- Added live security regressions for password-reset session revocation, immediate membership
  revocation, last-owner protection, every role against every tenant route, and every tenant
  route against another organization.
- Closed small frontend/spec drift: authenticated routes send `X-Robots-Tag: noindex, nofollow`,
  unfinished navigation links are hidden, and control radii use the design token. The worker's
  direct monotonic stale sweep is now the documented KISS design; a generic scheduler is deferred
  until a second periodic domain task exists.
- Live proof: the demo import automatically ran detection over 32 pairs and suppressed all 12
  planted maintenance/planned pairs. The date-scoped CLI also completed through the real worker
  and printed scored candidates with their full signal evidence.
- Verification: **182 backend tests pass**; Alembic reports no drift; Ruff, strict mypy across
  193 files, and all four import-linter contracts pass. Frontend ESLint, TypeScript, and the
  production Next.js build pass.

#### Cloudflare R2 production storage completed — 2026-09-22

- Added the `aioboto3` R2 adapter behind the existing `StorageProvider`: byte and spooled
  streaming uploads, chunked downloads, metadata reads, idempotent deletes, boundary-safe
  paginated prefix purges, and short-lived SigV4 PUT/GET URLs. Composition now boots with R2
  when validated credentials are present instead of raising the former implementation error.
- Kept vendor types inside `providers/storage/r2/`. R2 uses the required `auto` region,
  SigV4/path-style addressing, standard retries, HTTPS outside local development, pinned upload
  `Content-Type`, sanitised download disposition, and the provider's seven-day signing ceiling.
- Corrected an outdated architecture assumption using current Cloudflare documentation: R2 does
  not support presigned POST policies, so a PUT URL cannot carry `content-length-range`. The
  browser pre-checks size; the API authoritatively checks `HEAD` plus streamed bytes and now
  immediately deletes any oversized object before rejecting it.
- Added the deployment CORS example and concise private-bucket setup checklist under `infra/r2/`.
  A real bucket smoke test remains external because this workspace has no R2 credentials.
- Verification: **194 backend tests pass**; the adapter tests include real SDK SigV4 generation
  without network access plus a stateful fake-client contract for every operation. Alembic has no
  drift; Ruff, strict mypy across 195 files, all four import-linter contracts, and
  `uv lock --check` pass.

#### Generated OpenAPI contracts completed — 2026-09-22

- Added a deterministic schema exporter and pinned `openapi-typescript` package under the sole
  shared package, `packages/contracts`. `make contracts` requires neither a running API nor a
  database connection, and consecutive generations produce an identical declaration.
- Replaced the frontend API boundary's duplicated DTOs with aliases to generated FastAPI schemas
  while keeping the small handwritten fetch transport. Stable lower-camel operation IDs come from
  one FastAPI generator and have uniqueness/readability regression coverage.
- Added contract-drift CI and made frontend CI run when the generated declaration changes. The
  architecture repository map now reflects the actual exporter, API wrapper, and Next.js proxy
  filenames.
- Verification: **195 backend tests pass**; Ruff, strict mypy across 198 files, and all four
  import-linter contracts pass. Contract installation with the frozen lockfile, deterministic
  regeneration, frontend ESLint, TypeScript, and the production Next.js build all pass.

#### Authenticated server-rendered reads completed — 2026-09-22

- Added one server-only, no-store API read boundary using the documented `API_INTERNAL_URL`.
  It forwards the incoming cookie and request ID to FastAPI, uses the generated contract types,
  and redirects expired sessions without exposing the opaque session token to client code.
- The `/app` shell now receives the current user and organizations during server rendering.
  Import history, batch detail, mapping preview, and the first issue page also arrive as initial
  server data; browser requests remain only for pagination, retry, mutation, and two-second status
  polling.
- Added the authenticated route error boundary and a frontend environment example. Missing and
  invalid session cookies both redirect locally, and the frontend/API remain live on ports 3000
  and 8000.
- Verification: frontend ESLint, strict TypeScript, the production Next.js build, workflow YAML,
  and diff checks pass. The production route report keeps every `/app` route dynamically rendered.

#### AI scope removed in favor of KISS — 2026-09-22

- Superseded the earlier V1 embedding decision. V1 detection is now deterministic only; AI and
  embeddings may be reconsidered only after real customer review data demonstrates a specific
  gap that simpler signals cannot close.
- Removed the unused AI provider boundary, configuration, tests, semantic signal, AI/embedding
  entitlements, and related persistence fields. A forward migration keeps existing databases
  aligned without rewriting migration history.
- Replaced the local pgvector image with plain PostgreSQL 17; no vector extension is required.
- Kept `docs/architecture/08-ai-and-embeddings.md` only as explicitly deferred, non-binding
  research so it cannot be mistaken for current implementation scope.
- Verification: migration applied locally, `alembic check` reports no drift, **192 backend
  tests pass**, Ruff and strict mypy pass, all four import contracts are kept, the lockfile is
  current, and local `/health` plus `/ready` both return 200.

### 6. Review workflow — 🚧

Categories, root causes, append-only reviews, cost model + snapshots, review queue, evidence
panel.

#### Review truth foundation and core write API completed — 2026-09-22

- Added tenant-owned rework categories and root causes with vertical-neutral defaults. Existing
  organizations are backfilled by migration; new organizations receive the same idempotent
  defaults during creation.
- Added append-only human reviews with score/rule snapshots, exactly one current review per
  candidate, and an explicit supersession chain for reclassification.
- Review writes lock the candidate, validate category outcome against the human decision, reject
  root causes on non-confirmed reviews, update queue status, and emit an audit event in the same
  transaction.
- PostgreSQL grants prevent the application role from deleting reviews or changing review
  content; it may update only `superseded_by_review_id`. RLS is enabled and forced on all three
  new tenant tables, and composite foreign keys prevent cross-tenant references.
- Added member-readable category, root-cause, and review-history endpoints plus the
  manager-only review endpoint. Posting another review is the single reclassification path and
  preserves the supersession chain; there is no separate mutable update route.
- Added the member-readable candidate queue and candidate-detail endpoints. The queue supports
  score/band/status/entity/follow-up-date filters, three descending sort modes, and stable cursor
  pagination; each row includes both jobs, current review, and its three strongest signals.
  Detail returns every current-run signal, including non-matches and `NOT_EVALUABLE` evidence,
  in the same response.
- Candidate hydration uses small owning-module read models for jobs, customers, equipment, and
  technicians, preserving the architecture boundary while batching reads instead of issuing
  per-row queries.
- Regenerated the OpenAPI/TypeScript contracts for the review surface.
- Verification: migration applied locally, `alembic check` reports no drift, **201 backend
  tests pass**, Ruff and strict mypy pass, all four import contracts are kept, and focused tests
  cover backfill, idempotency, API authorization, queue cursor/filter/sort behavior, complete
  evidence responses, HTTP reclassification history, validation, protected deletion, RLS, and
  append-only privileges.

#### Thin review UI completed — 2026-09-22

- Added the server-rendered possible-callback queue with explicit review-state and score-band
  filters, stable cursor paging, compact evidence summaries, and a truthful open-only default.
- Added the evidence detail view with both visits, every deterministic signal (including
  non-matches and `NOT_EVALUABLE`), and visually separate score strength and human outcome.
- Added the single-candidate classification form for managers, admins, and owners; members keep
  read-only evidence access. Reclassification still uses the append-only review API.
- Kept the slice deliberately small: no AI, bulk actions, keyboard shortcuts, taxonomy editor,
  cost model, or analytics were added.
- Verification: frontend typecheck and lint pass, `git diff --check` passes, and an independent
  desktop/mobile browser evaluation passed after checking the queue, evidence detail, form
  validation, responsive order, density, and score/outcome color semantics.

#### Visible append-only review history completed — 2026-09-22

- Added server-rendered review history to the candidate evidence page using the existing
  member-readable endpoint and generated contract.
- The newest classification is shown first; superseded decisions, category/root-cause labels,
  score snapshots, timestamps, and notes remain visible without exposing internal UUIDs.
- A successful reclassification updates the timeline immediately with ID-based deduplication.
- Independent desktop, tablet, mobile, empty-state, and accessibility evaluation passed.

#### Production-readiness audit started — 2026-09-22

- Added `docs/runbooks/production-launch.md` with the required staging/production services,
  domain/cookie topology, deployable processes, environment boundaries, release order, and
  blocking launch gates.
- Hardened production startup so a development secret, missing/wrong shared cookie domain, or
  missing frontend CORS origin fails fast instead of silently breaking cross-subdomain auth.
- Corrected the stale launch-cost assumption: a commercial deployment cannot use Vercel Hobby,
  and current vendor pricing must be checked before provisioning.
- Added and validated the one-stack deployment package: Render Blueprint, Vercel config,
  production environment templates, read-only deployment smoke script, and migration/rollback
  runbook. Render's own Blueprint validator reports the manifest valid; the smoke script passes
  locally across liveness, readiness, auth redirect, exact credentialed CORS, private cache
  policy, request IDs, and security headers.
- Promoted Python dependency auditing from advisory to a blocking CI gate after the locked
  production dependency export passed with no known vulnerabilities.

### 7. Analytics & settings — ⬜

Dashboard, trends, root-cause and technician analytics, detection settings with preview, cost
model settings, exports, retention.

### 8. Public site & launch readiness — ⬜

Marketing routes, calculators, content, SEO/AEO, deletion flows, observability, runbooks,
legal, security checklist.

#### Homepage product walkthrough — ✅ implemented early

- Added a server-rendered product-preview section after `#how-it-works`, with a narrow client
  boundary for a 34-second fictional HVAC walkthrough: CSV import → possible-return queue →
  evidence → human classification → estimated rework impact.
- Playback is deterministic and local-only, pauses offscreen/in hidden tabs, autoplays once on
  eligible desktop devices, and becomes manual static scenes for reduced motion and touch-width
  layouts. No backend or unfinished dashboard component is imported.
- Maintenance conventions and the future real-component replacement map live in
  `frontend/src/components/marketing/product-walkthrough/README.md`.

---

## Decisions

Each decision records **why** and **what was rejected**. Full reasoning in
[`00-overview-and-decisions.md §4`](docs/architecture/00-overview-and-decisions.md) for D1–D28,
[`22-design-system.md`](docs/architecture/22-design-system.md) for D29–D34, D37, and D38,
[`02-multi-tenancy.md`](docs/architecture/02-multi-tenancy.md) for D35, and
[`21-implementation-sequencing.md` Phase 2](docs/architecture/21-implementation-sequencing.md)
for D36.

| # | Decision | Why | Rejected |
| --- | --- | --- | --- |
| D1 | Modular monolith, one FastAPI app, one Postgres | Solo maintainer; service boundaries are a distributed-systems tax we cannot spend | Microservices, separate detection service |
| D2 | Postgres is the queue and analytics store | Each alternative costs money at idle and solves a problem we do not have. `SKIP LOCKED` is a correct queue primitive | Redis + Celery, Kafka, Elasticsearch |
| D3 | Tenant isolation in 3 independent layers (RLS + repository + API) | Realistic failure is one forgotten `WHERE`, not a missing design. RLS turns that bug into an empty result set | Repository-only scoping; schema-per-tenant |
| D4 | App connects as a **non-owner** role; RLS `FORCE`d | A table owner bypasses its own RLS by default — without this, RLS is decorative | Single DB role |
| D5 | ~~Detection works with AI off~~ — **superseded by D39** | V1 now has no AI path at all | LLM-first pipeline |
| D6 | Config in the DB, logic in code (signal registry) | Orgs need to tune weights without a deploy; they do not need a DSL, and a DSL is a parser + sandbox + injection surface | Rules DSL in the database; hard-coded weights |
| D7 | Rule sets are immutable versions | Otherwise a score is unreproducible the moment settings change | Mutable settings rows |
| D8 | Candidates are **upserted** on a stable job-pair key, never delete+insert | `rework_candidates.id` anchors human reviews; delete+insert on re-run would cascade away every manager decision ever made | Rebuild candidates per run |
| D9 | Four separated data layers (raw / normalized / derived / human truth) | Layer 4 is the product's compounding asset and the only way to measure detection quality | A single `jobs.is_callback` flag written by both machine and human |
| D10 | Signals have three outcomes, incl. `NOT_EVALUABLE` | Otherwise an org lacking equipment data is permanently capped below a good score and the product looks broken for them | Boolean matched/unmatched |
| D11 | App-managed auth in FastAPI, opaque server-side sessions | Auth + authz in one place; revocation is a row delete; $0 | Better Auth in Next.js (split identity/authz, stale claims); Clerk/WorkOS (cost, vendor-owned org model) |
| D12 | No active org in the session | Org in the session creates stale authorization — a removed user keeps access until expiry | Session-carried org |
| D13 | UUIDv7 PKs generated in the application | Unguessable (no enumeration) + time-ordered (index locality). Identity available before flush | Serial integers; UUIDv4 |
| D14 | `NUMERIC(14,2)` + explicit currency; `Decimal` end to end; money serialized as a string | Float money in a cost report is indefensible; JSON numbers are doubles in every JS client | Float; integer minor units |
| D15 | `timestamptz` + a separate org-local `service_date` | "8 days apart" is calendar days in the shop's timezone, not a UTC delta | UTC-only arithmetic |
| D16 | Selective soft delete | Blanket `deleted_at` silently breaks every unique constraint and join | Soft-delete everything; hard-delete everything |
| D17 | `RESTRICT` on FKs from reviews to users/categories/root causes | The database refuses to let the product destroy its own evidence | `CASCADE`; `SET NULL` |
| D18 | Cursor pagination, no default total count | An import running during paging shifts rows under an offset reader | Offset pagination |
| D19 | Org in the URL path, not a header | A route cannot forget a scope it needs to resolve | `X-Organization-Id` header |
| D20 | Monorepo | One maintainer, atomic cross-cutting changes, cheap OpenAPI↔types contract check | Split repos |
| D21 | Providers behind narrow `Protocol`s; vendor SDKs confined by lint rule | Smallest abstraction that delivers vendor independence | Vendor types in domain code; a generic plugin framework |
| D22 | Authorization asks entitlements, never billing | Plan keys and vendor status must never appear in business logic | `if org.plan == "free"` |
| D23 | Worker in-process in V1, behind `WORKER_ENABLED` | Saves $7/mo; splitting is a config change, not a refactor | Dedicated worker service from day one |
| D24 | ~~Embeddings in V1, LLM classification deferred~~ — **superseded by D39** | Real-data evidence should determine whether similarity is worth another subsystem | Deterministic-only V1; full pipeline at launch |
| D25 | ~~No ANN index on `job_embeddings` in V1~~ — **superseded by D39** | Embeddings are no longer part of V1 | Build HNSW upfront |
| D26 | Design for ≤100k jobs/org, document the 1M path | Matches the SMB target; partitioning-compatible keys mean the upgrade is a migration, not a redesign | Partition now |
| D27 | ~~Prompts live in code, not the database~~ — **superseded by D39** | V1 now has no prompts | `ai_prompt_templates` table |
| D28 | ~~AI output is advisory and structurally inert~~ — **superseded by D39** | V1 now has no AI output | Injection classifier; AI-written reviews |
| D29 | Design system built before either frontend surface (Phase 1, ahead of backend Phase 2) | Cheap to get right early, expensive to retrofit once pages exist in two visual languages; every later phase becomes consumption, not design | Design-as-you-go per page |
| D30 | One Next.js app, one token file, one `components/ui/` — no `packages/ui` | Marketing and dashboard are route groups in one app; a shared package earns its cost only with a second real consumer, which doesn't exist | A separate design-system package |
| D31 | `--border-strong` added alongside the brief's Soft Border token | Soft Border on white measures ~1.3:1 — far under the 3:1 WCAG 1.4.11 target for a boundary that must read as one. Reserved for decorative dividers only; functional boundaries (inputs, selects, tables) use the new token (~3.2:1) | Using Soft Border everywhere as specified |
| D32 | Score band (confidence) and review outcome (human decision) use two different, non-overlapping color mappings | A high score is a strong signal, not a bad one — coloring it red would argue the opposite of the product's own premise. A rejected candidate is a healthy outcome and is styled neutral, never as an error | One score→color gradient reused for both axes |
| D33 | Apricot is background-only; never text, never a stand-alone focus ring | White-on-apricot measures ~1.8:1 (fails); apricot alone against white also fails the 3:1 non-text target. Focus rings use Teal | Apricot as an accent text/ring color per a literal reading of the brief |
| D34 | Font self-hosted via `next/font/google`, not the `fonts.googleapis.com` CSP allowance | No runtime request to Google Fonts at all — stricter than the general CSP carve-out already documented for cases that don't self-host | Runtime Google Fonts request behind CSP |
| D35 | RLS policy wraps `current_setting` in `NULLIF(..., '')` before the `::uuid` cast | `set_config(key, NULL, true)` — the SQL way to clear a GUC — produces an empty string, not NULL; `''::uuid` raises. Verified against a live Postgres session. Without this, "never set" fails safe but "explicitly cleared" throws a 500 — two paths meant to behave identically, diverging | The literal `current_setting(..., true)::uuid` pattern as originally drafted in Phase 0 |
| D36 | Backend pinned to Python 3.12, not the system's 3.14 | Learned from the Phase 1 TS7 lesson: verify ecosystem compatibility empirically rather than assume the newest version works. 3.12 has full wheel coverage for asyncpg and every other C-extension dependency; 3.14 is too new to trust blindly | System Python 3.14 |
| D37 | ~~The shipped logo mark keeps its own fixed navy/indigo colors, independent of the app's teal/petrol/apricot token palette~~ — **superseded by D38** | A logotype legitimately has its own brand-mark colors distinct from UI accent colors — same as a wordmark's ink not changing with a product's theme. Documented explicitly (rather than left as a silent mismatch) because indigo sits close to the "purple/blue AI-startup palette" §2's own anti-pattern checklist warns against | Re-deriving the UI palette from the logo's indigo; recoloring the logo to match teal |
| D38 | Logo recolored to match the UI palette (navy→`--brand-deep`, indigo→`--brand-primary`, dark-variant tint→a derived lighter teal) | Seeing the mark and a teal button side by side in the actual nav layout made the mismatch D37 accepted look worse in practice than it read on paper. Fixed hex values in the SVGs/component still track the tokens only by hand, not by a shared source | Keeping D37's split; deriving the UI palette from the logo's indigo instead |
| D39 | V1 has no AI or embeddings; reconsider only after real-data review proves a specific unmet need | KISS: deterministic evidence is cheaper, easier to explain, and already sufficient to validate the product premise | Keeping an unused provider abstraction; implementing OpenAI or embeddings pre-emptively |

---

## Status

### Done

- Phase 0: full architecture and technical specification (23 documents in `docs/architecture/`)
- `CLAUDE.md` binding rules for coding agents
- Kickoff decisions confirmed: app-managed auth and ≤100k jobs/org. The earlier embedding
  decision was superseded by D39.
- Design system specification (`22-design-system.md`) from the product design brief, with
  three palette-specific accessibility corrections (D31–D33) and the sequencing decision to
  build it before either frontend surface (D29)
- **Step 1 — design system foundation, implemented and verified.** `frontend/` scaffolded
  (Next.js 16, TypeScript, Tailwind v4); `tokens.css` with the full palette, type scale, and
  `@theme` mapping; 19 primitives in `components/ui/`; `Logo`; two chart wrappers; `Nav` +
  `Footer` (`MarketingLayout`) and `Sidebar` + `TopBar` (`DashboardLayout`, drawer <1024px);
  `/dev/tokens` reference page (`noindex`). Install, typecheck, lint, and production build all
  verified clean; `next start` and `next dev` both booted and served `200`s with real compiled
  CSS confirmed present. Root `Makefile` added with frontend-scoped `dev`/`build`/`lint`/
  `typecheck` targets. See [21 Phase 1](docs/architecture/21-implementation-sequencing.md) for
  the full exit-criteria checklist and the dependency-version findings from this pass.
- **Step 2 — backend foundation, implemented and verified.** `backend/` scaffolded (uv, Python
  3.12); settings, structlog + redaction, request-ID middleware; async SQLAlchemy engine tuned
  for PgBouncer; Alembic on the two-role split; `infra/neon/bootstrap.sql` creating
  `secondtrip_app` (non-owner, no BYPASSRLS) with `ALTER DEFAULT PRIVILEGES` covering future
  tables automatically; `TenantContext`, tenant-aware session factory, `TenantRepository`;
  `enable_rls`/`disable_rls` migration helpers; RFC 9457 errors, cursor pagination, UUIDv7;
  root `docker-compose.yml` (pgvector/pgvector:pg17); CI workflows. 23 tests pass against a
  live Postgres container (not mocked); `ruff`, `mypy --strict`, `import-linter` (3 contracts)
  all clean. Found and fixed a real RLS policy gap (D35) by testing the database directly. See
  [21 Phase 2](docs/architecture/21-implementation-sequencing.md) for the full exit-criteria
  checklist.
- **Brand mark shipped, then recolored to match the UI palette.** The open-loop S logo (four
  variants) and favicon are real now — `frontend/src/components/brand/logo.tsx` renders the
  actual SVG marks, `frontend/public/brand/` holds the source assets, and
  `frontend/src/app/icon.svg` + `apple-icon.png` wire the favicon via Next.js's file
  convention. It shipped first with independent navy/indigo brand colors (D37); a visual
  comparison against the real nav layout showed the mismatch clearly enough to recolor it to
  `--brand-deep`/`--brand-primary` instead (D38) — superseding D37, not adding to it. Verified
  live at each step: production build lists `/icon.svg` and `/apple-icon.png` as generated
  routes with correct `<head>` `<link>` tags; after the recolor, a fresh build + running
  server confirmed zero occurrences of the old hex values anywhere in the rendered output. See
  [22 §7](docs/architecture/22-design-system.md).

### In progress

- Step 6 review persistence, taxonomy/review APIs, candidate queue/detail reads, and the first
  thin review UI are complete through deterministic evidence, append-only reclassification,
  visible history, audit, authorization, and database enforcement. Keyboard workflow, taxonomy
  management, and cost snapshots remain. Step 5's required 50-candidate review, Phase 4's
  literal Microsoft Excel verification, and the production launch gates also remain.

### Remaining

- Manual Excel exit verification and the remaining Steps 5–8 work (see Steps above).
- **Immediate engineering action:** create the single gated production stack from the committed
  deployment package, load only fictional data, then run credentialed R2 and Resend smoke tests.
  Do not accept customer data until the blocking gates in `docs/runbooks/production-launch.md`
  are satisfied.
- **Manual action:** open `/tmp/secondtrip-excel-safety-check.csv` in Microsoft Excel and confirm
  no formula execution.
- Before Phase 8 (real marketing content): run an automated contrast/a11y tool pass on
  `/dev/tokens` — the palette was hand-verified against the WCAG formula in
  [22 §3.3](docs/architecture/22-design-system.md), which is evidence but not a substitute.
- CI workflows (`backend.yml`, `frontend.yml`) are written and every command in them was
  verified locally, but have never actually run in GitHub Actions (no git remote in this
  environment yet). Confirm green on the first real push.

### Open questions to resolve before they block

- **Domain/DNS** — frontend and API must be subdomains of one registrable domain before auth
  works (`SameSite=Lax` fails across `*.vercel.app` ↔ `*.onrender.com`). Needed by Step 3.
  See [01 §2](docs/architecture/01-system-architecture.md).
- **Real customer CSV samples** — the synonym dictionary and adversarial corpus are guesses
  until real exports are seen. Worth obtaining before Step 4 finishes.
- **Neon production role setup** — `infra/neon/bootstrap.sql` is written and verified locally;
  it still needs a real one-time run against the actual Neon project (as its owner role)
  before any environment but local dev can work, with the dev-only password replaced per the
  script's own header comment. Needed before Step 3's auth flows can target staging/prod.
