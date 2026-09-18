# PLAN.md — SecondTrip

Durable task state. Read this and `CLAUDE.md` before starting any feature or fix.
Source of truth is files, not chat history.

**Last updated:** 2026-09-18
**Current phase:** Phase 2 (backend foundation) complete → Phase 3 (identity & tenancy) not started

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
ingestion, detection engine, AI/embeddings, background jobs, storage, threat model, privacy,
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

### 3. Identity & tenancy — ⬜

Users, sessions, orgs, memberships, invitations, RBAC, email flows, CSRF/CORS, audit service,
app shell (built on Step 1's `DashboardLayout`).

### 4. Ingestion — ⬜

Background job queue, storage provider, operational schema, import pipeline (profile → map →
validate → commit → process), normalization, entity resolution, error reporting, entitlements,
import wizard UI, demo seed data.

### 5. Detection engine (no UI) — ⬜

Rule sets, signal registry, candidate generation, scoring, explainability persistence,
embeddings, similarity signal, CLI proof. **Gate: results must be plausible on real data
before Step 6 begins.**

### 6. Review workflow — ⬜

Categories, root causes, append-only reviews, cost model + snapshots, review queue, evidence
panel.

### 7. Analytics & settings — ⬜

Dashboard, trends, root-cause and technician analytics, detection settings with preview, cost
model settings, exports, retention.

### 8. Public site & launch readiness — ⬜

Marketing routes, calculators, content, SEO/AEO, deletion flows, observability, runbooks,
legal, security checklist.

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
| D2 | Postgres is the queue, vector store and analytics store | Each alternative costs money at idle and solves a problem we do not have. `SKIP LOCKED` is a correct queue primitive | Redis + Celery, Kafka, Pinecone, Elasticsearch |
| D3 | Tenant isolation in 3 independent layers (RLS + repository + API) | Realistic failure is one forgotten `WHERE`, not a missing design. RLS turns that bug into an empty result set | Repository-only scoping; schema-per-tenant |
| D4 | App connects as a **non-owner** role; RLS `FORCE`d | A table owner bypasses its own RLS by default — without this, RLS is decorative | Single DB role |
| D5 | Detection works with AI off | Reliability (outage ≠ downtime) and credibility ("the AI says so" is not an argument a manager can use) | LLM-first pipeline |
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
| D24 | Embeddings in V1, LLM classification deferred | Description similarity is what separates a callback from two unrelated visits; classification is where the cost and the injection surface are | Deterministic-only V1; full pipeline at launch |
| D25 | No ANN index on `job_embeddings` in V1 | V1 vector work is pairwise between two known rows — an HNSW index would never be used | Build HNSW upfront |
| D26 | Design for ≤100k jobs/org, document the 1M path | Matches the SMB target; partitioning-compatible keys mean the upgrade is a migration, not a redesign | Partition now |
| D27 | Prompts live in code, not the database | Prompt text and its Pydantic output schema must change together; git is the right versioner | `ai_prompt_templates` table |
| D28 | AI output is advisory and structurally inert | Bounds prompt-injection blast radius to one misleading sentence; filtering injected text is unreliable theatre | Injection classifier; AI-written reviews |
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

---

## Status

### Done

- Phase 0: full architecture and technical specification (23 documents in `docs/architecture/`)
- `CLAUDE.md` binding rules for coding agents
- Kickoff decisions confirmed: app-managed auth, ≤100k jobs/org, embeddings in V1 with LLM
  classification deferred
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

- Nothing

### Remaining

- Step 3 (identity & tenancy) through Step 8 (see Steps above)
- **Immediate next action:** Step 3 — `users`/`organizations`/`organization_memberships`/
  `organization_invitations`, Argon2id session auth, email verification + password reset,
  RBAC (`Permission` enum + rank map + `require_permission`, building on `OrganizationRole`
  which already exists from Step 2), the `(auth)` route group and `/app` shell on Step 1's
  `DashboardLayout`.
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
- **pgvector version on Neon** — confirm ≥ 0.8 for `hnsw.iterative_scan`. Not needed until
  vector search ships; verify before promising it.
- **Real customer CSV samples** — the synonym dictionary and adversarial corpus are guesses
  until real exports are seen. Worth obtaining before Step 4 finishes.
- **Verify current AI provider pricing** at Step 5; the figures in the spec are budgeting
  estimates.
- **Neon production role setup** — `infra/neon/bootstrap.sql` is written and verified locally;
  it still needs a real one-time run against the actual Neon project (as its owner role)
  before any environment but local dev can work, with the dev-only password replaced per the
  script's own header comment. Needed before Step 3's auth flows can target staging/prod.
