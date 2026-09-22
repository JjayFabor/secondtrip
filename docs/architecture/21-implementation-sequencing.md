# 21 — Implementation Sequencing

Ordered so that each phase produces something verifiable, and so the riskiest assumptions are
tested early rather than discovered late.

**Three rules that govern the order:**

1. **The visual language is built before either surface is.** Tokens and primitives come
   before marketing pages or dashboard screens, so nothing gets built twice in two different
   visual languages. See [22-design-system.md](22-design-system.md).
2. **The detection engine is proven before the UI is built around it.** If the scoring approach
   does not produce believable results on real-shaped data, everything downstream is wasted
   effort. Phase 5 ends with a command-line proof, not a screen.
3. **Tenant isolation is built in Phase 2, not retrofitted.** RLS, the app role, and the
   repository base class come before the first business table. Adding isolation to an existing
   schema means auditing every query written before it.

Estimates assume one developer working part-time; they are for ordering, not for commitments.

---

## Phase 1 — Design system foundation — ✅ **done**

**Goal:** the tokens and primitive components both surfaces will build on, proven visually
before either surface consumes them. No product pages yet — this phase produces a component
library, not a website.

- `frontend/` scaffold: Next.js 16 (App Router) + TypeScript + Tailwind v4, no page content
- `src/styles/tokens.css` — colors, radius, shadow, motion custom properties, **and the
  Tailwind theme mapping** ([22 §3, §5, §8](22-design-system.md)). Tailwind v4's theme is
  CSS-native (`@theme` inside this file); there is no `tailwind.config.ts` — see
  [22 §15](22-design-system.md)
- `lucide-react` wired at the documented sizes; Recharts installed and wrapped in
  `components/charts/` (`LineChart`, `HorizontalBarChart`)
- Shared primitives in `src/components/ui/` (19 files): Button, Input, Textarea, Select,
  Checkbox, Radio Group, Switch, Badge, Card, Table, Dialog, Dropdown Menu, Tabs, Accordion,
  Tooltip, Popover, Skeleton, Separator, Label — vendored on the unified `radix-ui` package,
  styled with tokens only
- `Logo` in `src/components/brand/` with all four variants (the icon-mark slot shipped shortly
  after this phase — see [22 §7](22-design-system.md))
- `/dev/tokens` route (`src/app/dev/`) rendering the full palette, type scale, spacing steps,
  radius/shadow, every primitive variant (including disabled and `aria-invalid` states), the
  score-band vs. review-outcome mapping, both charts, icons, and logo variants — `noindex` via
  `src/app/dev/layout.tsx`
- `MarketingLayout` (`Nav` + `Footer`) and `DashboardLayout` (`Sidebar` + `TopBar`, drawer
  below 1024px) — structure and responsive behavior only, real navigation targets arrive with
  Phase 3

**Exit criteria**
- [x] `/dev/tokens` renders the full palette, type scale, and every primitive variant
      (including disabled/error states) without a single hard-coded hex or px value outside
      `tokens.css` — **verified live**: `pnpm build` succeeds, `next start` and `next dev` both
      serve `/` and `/dev/tokens` at `200`, and the compiled CSS was inspected directly to
      confirm the real token hex values, generated utility classes, and self-hosted Manrope
      `@font-face` rules are present
- [x] `--border-strong` and the score-band/review-outcome color rules from
      [22 §3.3–3.4](22-design-system.md) are implemented exactly as specified in `badge.tsx`
      and demonstrated side-by-side on `/dev/tokens`
- [x] `DashboardLayout`'s sidebar collapses to a drawer below 1024px (`lg:` breakpoint);
      `MarketingLayout` uses no fixed widths below it
- [x] No shadow appears anywhere except the two documented elevation cases (`--shadow-sm` on
      Select/Dropdown/Popover/Tooltip content, `--shadow-md` on Dialog) — confirmed no other
      component references a shadow utility
- [x] `pnpm typecheck` and `pnpm lint` pass clean, including the `dangerouslySetInnerHTML` ban
      (`react/no-danger` as a hard lint error)
- [ ] Automated contrast check (axe/Lighthouse) — not yet run; the palette pairs were verified
      by hand against the WCAG formula in [22 §3.3](22-design-system.md), which is evidence but
      not a substitute for a tooling pass. Do this before Phase 8 ships real marketing content.

**Real dependency-version findings from this pass, worth knowing before touching this code:**
TypeScript 7.0.2 (the native/`tsgo` line) is not yet supported by `typescript-eslint`
(pinned to **6.0.3** instead); ESLint 10 is not yet supported by `eslint-config-next`'s bundled
plugins (pinned to **9.39.5**); `eslint-config-next@16` exports a native flat-config array
directly — do **not** wrap it in `@eslint/eslintrc`'s `FlatCompat` (that legacy-shim path
throws a circular-JSON error on this package's already-resolved plugin objects). Re-check all
three the next time any of these packages are upgraded.

This phase is small on purpose. It does not include a single page of real marketing or product
copy — that temptation is exactly how a design system ends up half-applied, with the first
page built as a one-off and everything after it inconsistent with it.

---

## Phase 2 — Foundation — ✅ **done**

**Goal:** an empty but correct application skeleton with tenancy enforced.

- `backend/` scaffold (uv, Python 3.12 pinned): `pyproject.toml`, ruff, mypy --strict,
  import-linter, pytest — see [16](16-repository-structure.md)
- `core/settings.py` with production-posture assertions ([17 §1](17-configuration.md)),
  scoped to what this phase needs — later modules add their own fields as they're built
  rather than stubbing unused variables ahead of time
- structlog + redaction processor, request-ID middleware ([18](18-observability.md))
- Async SQLAlchemy engine tuned for PgBouncer (`statement_cache_size=0`); Alembic configured
  with the async engine, running as `DATABASE_URL_MIGRATIONS`
- `infra/neon/local-role.sql` creates the local-only `secondtrip_app`; the shared
  `infra/neon/bootstrap.sql` fails closed unless that role already exists without elevated
  attributes, then applies `ALTER DEFAULT PRIVILEGES` so every future table is covered — both
  run via Docker's `initdb.d`, while production creates a unique credential before bootstrap
- `TenantContext` (`core/tenancy.py`), tenant-aware session factory (`db/session.py`)
  emitting `SELECT set_config('app.current_org_id', :org_id, true)` as the first statement
  of every transaction
- `TenantRepository` base (`db/repository.py`); `enable_rls(table)` / `disable_rls(table)`
  migration helpers (`migrations/rls_helpers.py`) applying `ENABLE` + `FORCE` together
- RFC 9457 problem+json error handlers, cursor pagination, UUIDv7 generation (`uuid6`)
- `docker-compose.yml` (repo root): `postgres:17` on a non-default port, bootstrap
  SQL mounted into `initdb.d`
- Root `Makefile` extended with real backend targets; `.github/workflows/backend.yml`

**Exit criteria**
- [x] `make dev` / `make db-up` starts Postgres from a clean checkout; API boots via
      `make dev-backend` — **verified live**: fresh `docker compose down -v` → `up -d` →
      `alembic upgrade head` → real `uvicorn` process → `curl` against `/health` and `/ready`,
      both `200`, `/ready` genuinely executing `SELECT 1` against the live database
- [x] A migration creates a dummy tenant table (`_rls_smoke_test`) with RLS enabled *and*
      forced — confirmed directly against `pg_class.relrowsecurity` /
      `relforcerowsecurity`, not inferred from the migration source
- [x] A test proves the app role cannot read another org's rows via raw SQL
      (`tests/security/test_rls.py`, 5 tests: cross-tenant read blocked, cross-tenant write
      blocked by `WITH CHECK`, missing context → zero rows, explicitly-cleared context → zero
      rows, owner role correctly bypasses RLS by contrast) — run against the real Postgres
      container, not a mock
- [x] `mypy --strict` and `import-linter` pass — **and** `ruff check`, on 34 source files
- [ ] CI green — `backend.yml`/`frontend.yml` are written to the spec in
      [16 §5](16-repository-structure.md) and every command they run was verified locally
      (this repo has no git remote / Actions runner in this environment to execute them
      against). Confirm on the first real push.

**A real bug found and fixed by testing the database directly, not by reasoning about the
SQL:** `set_config(key, NULL, true)` — the standard way to clear a GUC mid-session — does not
produce SQL `NULL`, it produces an **empty string**, and `''::uuid` raises rather than
comparing false. The original policy (`current_setting(..., true)::uuid`) only degraded
safely for a GUC that was *never* touched; an explicitly-cleared one would have thrown a 500.
Fixed with `NULLIF(current_setting(...), '')::uuid` in `migrations/rls_helpers.py`, verified
against a live session, propagated to
[02-multi-tenancy.md §2](02-multi-tenancy.md), and covered by a named regression test.

---

## Phase 3 — Identity & tenancy

**Goal:** users can register, verify, log in, create organizations, and invite colleagues.

- `users`, `user_credentials`, `user_sessions`, token tables
- `organizations`, `organization_memberships`, `organization_invitations`
- Argon2id, session issue/validate/revoke, cookie handling
- Email verification, password reset, email change ([03 §4](03-authentication.md))
- `EmailProvider` protocol + `console` and `resend` adapters
- Invitation flow (role from the row, email-bound)
- RBAC: `Permission` enum, rank map, `require_permission`
- Rate limiting on auth endpoints
- CSRF, CORS, security headers
- Frontend: `(auth)` routes and the `/app` shell built on Phase 1's `DashboardLayout` — org
  switcher, session guard middleware. No new visual components; this phase consumes Phase 1's
  library, it doesn't extend it
- `audit_events` + the audit service (identity actions audited from day one)

**Exit criteria**
- [x] Full signup → verify → create org → invite → accept flow works in a browser
- [x] Password reset revokes all sessions (tested)
- [x] Revoked membership denied on the next request (tested)
- [x] Route audit test passes
- [x] Permission matrix test passes for all four roles
- [x] Last owner cannot be removed or demoted

---

## Phase 4 — Ingestion

**Goal:** a real CSV becomes real jobs, idempotently, with a usable error report.

- `background_jobs` + worker loop + registry + direct stale recovery ([09](09-background-jobs.md))
- `StorageProvider` protocol + local and R2 adapters; presigned upload
- Operational schema: `source_systems`, `customers`, `locations`, `equipment`, `technicians`,
  `service_categories`, `jobs`, `job_notes`, `job_line_items`
- Import schema: `import_batches`, `import_rows`, `import_column_mappings`
- Profiling → mapping suggestion → validation → processing, chunked and checkpointed
- Normalization and entity-resolution modules ([06 §5–6](06-csv-ingestion.md))
- Error catalogue + error report CSV with `csv_safe`
- `EntitlementService` + plans/entitlements seed ([14](14-billing-and-entitlements.md))
- Frontend: import wizard (`ImportColumnMapper`, `ImportIssueTable` from Phase 1) and import
  list/detail, built on `DashboardLayout`
- `make seed-demo` — realistic HVAC data with planted callbacks, maintenance pairs, and
  unrelated pairs

**Exit criteria**
- [x] A 50k-row real-shaped CSV imports in under 2 minutes
- [x] Re-importing the same file creates 0 new jobs
- [x] Interrupt-and-resume produces exactly the right job count
- [x] Adversarial CSV corpus produces clean errors, no crashes, no hangs
- [ ] Error report opens in Excel with no formula execution
- [x] Entitlement limits enforced at both create and commit

Phase 4 is the largest phase and the one most likely to overrun. It is worth the time: every
subsequent phase consumes its output, and a normalization bug found in Phase 7 invalidates
everything built in between.

**Production-readiness note:** local and R2 implementations exercise the same protocol, and
production fails closed unless R2 plus all credentials are configured. A real staging bucket
smoke test still requires external credentials and is part of the staging deployment checklist.

---

## Phase 5 — Detection engine (no UI)

**Goal:** prove the approach works, before building screens around it.

- `detection_signal_definitions` seed; `detection_rule_sets` + `detection_rules` with defaults
- Candidate generation SQL with canonical ordering and fan-out guard
- Signal registry with all deterministic signals ([07 §3](07-detection-engine.md))
- Scoring calculator (pure), bands, veto/gate handling
- `candidate_signals` persistence with rendered explanations
- `detection_runs`, upsert-based re-run semantics
- A CLI: `make detect ORG=...` printing the top 50 candidates with full evidence

**Exit criteria**
- [x] On the demo dataset, planted callbacks rank in the top decile
- [x] Planted maintenance pairs are suppressed by veto
- [x] Planted unrelated pairs score below `min_score_to_surface`
- [x] Re-running detection twice preserves candidate IDs
- [x] Scoring unit tests pass, including every `NOT_EVALUABLE` case
- [ ] **Manual review of 50 candidates on a real dataset finds the results plausible**

The last criterion is a judgement call and it is the most important one in this document. If
the top candidates are not obviously sensible to someone who knows the trade, the answer is to
tune signals and weights **here** — not to proceed and hope the UI makes them convincing.

---

## Phase 6 — Review workflow

**Goal:** human truth captured and protected.

- `rework_categories` + `root_causes` seeds and CRUD
- `rework_reviews` with append-only semantics and the supersession chain
- `organization_cost_models` + the cost calculator + `rework_cost_snapshots`
- Review queue (`CandidateListRow`) and evidence panel (`EvidencePanel`, `SignalRow`,
  `ScoreBadge`) — all consumed from Phase 1's library, not newly designed
- Keyboard navigation, bulk review, manual pair creation
- Audit events for every review action
- Category/root-cause management UI

**Implementation status (2026-09-22):** category/root-cause persistence and default seeding,
append-only reviews, supersession history, audit emission, tenant-safe foreign keys, RLS, and
database-level review write restrictions are complete. Member taxonomy/history reads and the
manager-only append/reclassification endpoint are also complete. Candidate queue/detail reads
now return both jobs, the current review, summary signals, and the complete current-run evidence
set. The first thin UI is also complete: a server-rendered queue, full evidence detail, and a
role-aware single-candidate review form. It intentionally excludes AI, bulk actions, keyboard
shortcuts, taxonomy management, cost snapshots, and analytics. Read-only append-only review
history is now visible on the evidence page; the remaining exclusions stay deferred.

**Exit criteria**
- [ ] A manager can work a 50-candidate queue end to end using the keyboard
- [ ] Re-running detection after reviews preserves every review (tested)
- [ ] Changing the cost model leaves historical snapshots unchanged
- [ ] Deactivating an in-use category is blocked from deletion and offered as deactivation
- [x] Reclassification produces a visible history
- [x] Score-band and review-outcome colors follow [22 §3.4](22-design-system.md) exactly — a
      rejected candidate never renders in the danger color

---

## Phase 7 — Analytics & settings

**Goal:** the business answer, and the ability to tune the engine.

- Analytics endpoints with the `basis` object ([15 §2](15-api-design.md))
- Dashboard, trends, root-cause distribution, technician view (volume-gated)
- Chart components (`LineChart`, `HorizontalBarChart`, `RankedList` from Phase 1) wired to
  real data
- Detection settings UI including the **preview** endpoint
- Cost model settings, organization settings, team management
- Export pipeline (jobs, candidates, reviews, full org export) with `csv_safe`
- Retention configuration + prune jobs
- Usage/plan view

**Exit criteria**
- [ ] Dashboard answers "how much is rework costing us?" with a stated basis
- [ ] Changing a detection weight previews its effect before saving
- [ ] Rule change creates a new version and triggers a re-run
- [ ] Technician rates hidden below the minimum volume threshold
- [ ] Full org export round-trips into a spreadsheet cleanly
- [ ] No chart series uses a color outside `--brand-primary`, `--accent`, and neutral grays

---

## Phase 8 — Public site & launch readiness

- Marketing routes, industry pages, both calculators — built on Phase 1's `MarketingLayout`
  and primitives, with the hero's product preview using the real `EvidencePanel` component and
  clearly marked sample data ([22 §10](22-design-system.md))
- First ten content pieces ([20 §6](20-frontend-and-seo.md))
- JSON-LD, sitemap, robots, OG images, `llms.txt`
- Organization deletion + purge job; user anonymisation
- Sentry, uptime monitoring, `/internal/metrics`, daily digest
- Runbooks: deploy, rotate secrets, restore, incident response
- Privacy policy, terms, DPA, subprocessor list
- **Full pre-launch security checklist** ([11 §16](11-security-threat-model.md))

**Exit criteria**
- [ ] Security checklist fully signed off
- [ ] Marketing pages render fully with JavaScript disabled
- [ ] Lighthouse ≥ 95 on marketing routes
- [ ] Organization deletion removes every row and every object (tested)
- [ ] A cold-start request completes within an acceptable time
- [ ] No fabricated metric, logo, or testimonial appears anywhere on the public site

---

## Deferred (post-launch, in rough priority order)

| Item | Trigger |
| --- | --- |
| **Reconsider AI or embeddings** | Only when real customer review data demonstrates a specific quality gap that simpler deterministic signals cannot close |
| Detection quality tuning from aggregate review data | ~500 reviews across customers |
| TOTP MFA | First customer security questionnaire |
| Billing (checkout, portal, webhooks) | First customer wanting to pay |
| Dedicated worker service | Import processing degrades API p95 |
| FSM integrations (ServiceTitan, Jobber, Housecall Pro) | Enough demand to justify per-vendor maintenance. `SourceRecord` boundary already exists |
| Public API + API keys | `api_access` entitlement demand |
| "Ask SecondTrip" | Everything above |
| Scheduled reports by email | Customer request |

---

## Standing risks

| Risk | Mitigation |
| --- | --- |
| **Detection quality is unconvincing on real data** | Phase 5 exit criteria force this to surface before UI investment. Mitigation is weight tuning and new signals, both of which the architecture supports without migration |
| Design system built but not actually followed once real pages get built under deadline pressure | Phase 1 ships a `/dev/tokens` reference page precisely so later phases have something to diff against, not just a document to remember |
| Real CSVs are messier than anticipated | Adversarial corpus; nothing is silently discarded, so problems are visible rather than corrupting |
| Entity resolution merges distinct customers | Natural-key rules are conservative and documented; equipment is never invented; `POSSIBLE_DUPLICATE` warns rather than merging silently |
| Phase 4 overruns | Accepted — it is the foundation everything consumes |
| In-process worker starves the API | Measured in Phase 7; the split is a config change |
| Neon free tier outgrown | Expected and cheap to resolve; retention policies already bound growth |
| Solo-maintainer context loss | This specification, `PLAN.md`, and `CLAUDE.md` exist for exactly this |
