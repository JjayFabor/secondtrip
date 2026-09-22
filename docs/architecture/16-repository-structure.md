# 16 — Repository Structure

**Recommendation: a single monorepo.**

One maintainer making cross-cutting changes (add an API field, consume it in the UI) should
make one commit, one PR, one CI run. Two repositories buy independent release cadence — which
one person does not need — at the cost of version skew between the API and its only client,
and a second set of CI, dependency, and review overhead. The contract check in
[15 §4](15-api-design.md) only works cheaply when both sides live together.

Revisit if a second team owns the frontend, or if a public API with external consumers needs
its own release train.

---

## 1. Top level

```
secondtrip/
├── README.md
├── CLAUDE.md                     # instructions for coding agents
├── PLAN.md                       # durable task state
├── docs/
│   ├── architecture/             # this specification
│   ├── runbooks/                 # deploy, rotate secrets, restore, incident response
│   └── decisions/                # ADRs added after Phase 0
├── backend/
├── frontend/
├── packages/
│   └── contracts/                # generated TS types from OpenAPI — the ONLY shared package
├── infra/
│   ├── render.yaml
│   └── neon/                     # role + RLS bootstrap SQL
├── .github/workflows/
│   ├── backend.yml
│   ├── frontend.yml
│   └── contracts.yml             # regenerates types, fails on drift
├── .gitignore
├── .gitleaks.toml
└── Makefile                      # one entry point for every common task
```

`packages/` contains exactly one package, and should stay that way. A monorepo's failure mode
is a proliferation of shared packages that turn every change into a cross-package refactor.
Generated API types are the one thing genuinely shared between a Python backend and a
TypeScript frontend.

A `Makefile` rather than per-directory scripts, so `make dev`, `make test`, `make migrate` work
identically from the repo root regardless of which half you are working in.

---

## 2. Backend

Domain-oriented modules, not layer-oriented folders. A change to detection touches
`modules/detection/` — not `routers/`, `services/`, `models/`, and `schemas/` in four places.

```
backend/
├── pyproject.toml                # uv; ruff, mypy, pytest config
├── uv.lock
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
├── app/
│   ├── main.py                   # app factory, lifespan, middleware
│   ├── composition.py            # the composition root: builds providers, wires DI
│   │
│   ├── core/
│   │   ├── settings.py           # pydantic-settings; the ONLY os.environ reader
│   │   ├── logging.py            # structlog config + redaction processor
│   │   ├── errors.py             # domain exception hierarchy + problem+json handlers
│   │   ├── ids.py                # UUIDv7 generation
│   │   ├── openapi.py            # stable generated-contract operation IDs
│   │   ├── pagination.py         # cursor encode/decode
│   │   ├── permissions.py        # Permission enum, rank map
│   │   ├── tenancy.py            # TenantContext
│   │   ├── money.py              # Decimal helpers, serialization
│   │   ├── time.py               # org-timezone-aware date math
│   │   └── rate_limit.py
│   │
│   ├── db/
│   │   ├── engine.py             # async engine; asyncpg tuned for PgBouncer
│   │   ├── session.py            # tenant-aware session factory (emits SET LOCAL)
│   │   ├── base.py               # DeclarativeBase, TimestampMixin, TenantMixin
│   │   ├── types.py              # custom types (Vector, Money, CIText)
│   │   └── repository.py         # TenantRepository base
│   │
│   ├── api/
│   │   ├── v1/router.py          # assembles every module router
│   │   ├── deps.py               # require_session, require_org_context, require_permission
│   │   └── middleware/
│   │       ├── request_id.py
│   │       ├── logging.py
│   │       ├── csrf.py
│   │       └── security_headers.py
│   │
│   ├── modules/
│   │   ├── identity/
│   │   ├── organizations/
│   │   ├── customers/
│   │   ├── workforce/
│   │   ├── jobs/
│   │   ├── imports/              # layout in [06 §10]
│   │   ├── detection/            # layout in [07 §9]
│   │   ├── reviews/
│   │   ├── analytics/
│   │   ├── costs/
│   │   ├── billing/              # layout in [14 §6]
│   │   ├── audit/
│   │   └── tasks/                # queue, worker, registry, stale recovery
│   │
│   ├── providers/
│   │   ├── ai/                   # layout in [08 §8]
│   │   ├── storage/              # layout in [10]
│   │   ├── email/
│   │   │   ├── base.py
│   │   │   ├── templates/
│   │   │   ├── resend.py
│   │   │   └── console.py        # dev: prints to stdout
│   │   └── billing/
│   │
│   └── shared/
│       ├── csv_safety.py         # the formula-injection escaper
│       ├── hashing.py
│       ├── text.py               # normalization used by imports AND detection
│       └── result.py
│
├── scripts/
│   └── export_openapi.py         # deterministic schema export; no live API/database required
├── seeds/                        # industry packs, default categories, signal definitions
└── tests/
    ├── conftest.py
    ├── factories/
    ├── fixtures/csv/             # including the adversarial corpus
    ├── unit/
    ├── integration/
    ├── security/
    └── contract/
```

### Standard module shape

```
modules/<domain>/
├── __init__.py       # public surface: the service class and its DTOs. Nothing else.
├── router.py         # HTTP only — validate, call service, serialize. No business logic.
├── schemas.py        # Pydantic request/response models
├── models.py         # SQLAlchemy ORM
├── repository.py     # tenant-scoped data access
├── service.py        # domain logic, transaction boundaries, audit emission
├── errors.py         # domain exceptions
└── <subpackages>/    # when a module earns them (detection, imports)
```

Modules stay flat until they don't. `identity` and `workforce` are five files; `detection` and
`imports` have subpackages because they genuinely have internal structure. Creating empty
`services/`/`handlers/` folders for a 200-line module is the enterprise-abstraction trap the
brief warns against.

### Dependency rules (CI-enforced)

`import-linter` contracts in `pyproject.toml`:

1. `core`, `db`, `shared` import nothing from `modules` or `api`.
2. `providers/*/base.py` imports nothing from `modules`.
3. A module may import another module's `service.py` and `schemas.py` — never its
   `repository.py` or `models.py`.
4. `api` imports modules; modules never import `api`.
5. Vendor SDKs are confined: `boto3`/`aioboto3` only under `providers/storage/r2/`, and
   `resend` only under `providers/email/`.
6. No import cycles between modules.

Rule 3 is the one that decays without enforcement, and it is the one that keeps the monolith
modular. Rule 5 is what makes ADR-008 real rather than aspirational.

The single sanctioned exception is `jobs/read_models.py` — a narrow exported selectable that
`detection` and `analytics` may use for bulk SQL ([01 §5](01-system-architecture.md)).

---

## 3. Frontend

```
frontend/
├── package.json
├── next.config.ts
├── postcss.config.mjs                      # @tailwindcss/postcss — no tailwind.config.ts;
│                                           # Tailwind v4's theme lives in tokens.css below
├── src/
│   ├── styles/
│   │   └── tokens.css                      # design tokens + Tailwind @theme — see [22-design-system.md]
│   ├── app/
│   │   ├── (marketing)/
│   │   │   ├── layout.tsx                 # public chrome
│   │   │   ├── page.tsx                   # /
│   │   │   ├── features/page.tsx
│   │   │   ├── pricing/page.tsx
│   │   │   ├── industries/[industry]/page.tsx    # generateStaticParams
│   │   │   ├── resources/
│   │   │   │   ├── page.tsx
│   │   │   │   └── [slug]/page.tsx
│   │   │   ├── tools/
│   │   │   │   ├── callback-cost-calculator/page.tsx
│   │   │   │   └── rework-cost-calculator/page.tsx
│   │   │   ├── glossary/[term]/page.tsx
│   │   │   ├── sitemap.ts
│   │   │   ├── robots.ts
│   │   │   └── opengraph-image.tsx
│   │   │
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   ├── register/page.tsx
│   │   │   ├── verify/page.tsx
│   │   │   ├── reset-password/page.tsx
│   │   │   └── accept-invite/page.tsx
│   │   │
│   │   ├── app/                            # authenticated; noindex
│   │   │   ├── layout.tsx                  # session guard + org switcher + nav
│   │   │   ├── page.tsx                    # redirects to dashboard
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── imports/
│   │   │   │   ├── page.tsx
│   │   │   │   ├── new/page.tsx            # upload → map → validate → commit wizard
│   │   │   │   └── [id]/page.tsx
│   │   │   ├── rework/
│   │   │   │   ├── page.tsx                # the review queue
│   │   │   │   └── [id]/page.tsx           # evidence panel — the product's core screen
│   │   │   ├── jobs/
│   │   │   │   ├── page.tsx
│   │   │   │   └── [id]/page.tsx
│   │   │   ├── customers/[id]/page.tsx
│   │   │   ├── technicians/page.tsx
│   │   │   ├── analytics/page.tsx
│   │   │   └── settings/
│   │   │       ├── organization/page.tsx
│   │   │       ├── detection/page.tsx
│   │   │       ├── cost-model/page.tsx
│   │   │       ├── categories/page.tsx
│   │   │       ├── team/page.tsx
│   │   │       └── billing/page.tsx
│   │   │
│   │   └── api/                            # thin BFF route handlers only
│   │
│   ├── components/
│   │   ├── ui/                             # vendored primitives — shared by every route group
│   │   ├── brand/                          # Logo (horizontal/icon/mono/dark)
│   │   ├── charts/                         # Recharts wrappers, pre-themed
│   │   ├── marketing/                      # Nav, Hero, PricingCard, FAQAccordion, Footer
│   │   └── dashboard/                      # Sidebar, TopBar, MetricPanel, ScoreBadge,
│   │                                       # SignalRow, EvidencePanel, CandidateListRow,
│   │                                       # ImportColumnMapper, ImportIssueTable, EmptyState
│   ├── lib/
│   │   ├── api.ts                          # browser fetch: credentials, CSRF, problem+json
│   │   ├── api-server.ts                   # no-store reads + cookie forwarding for RSCs
│   │   ├── format.ts                       # money/date formatting in org timezone
│   │   └── seo.ts                          # metadata + JSON-LD builders
│   ├── content/                            # MDX: resources, glossary, industry copy
│   └── proxy.ts                            # auth redirect + security headers (Next.js convention)
└── public/
```

The visual language — tokens, component inventory, layout patterns — is specified in full in
[22-design-system.md](22-design-system.md); this section only fixes where that system lives in
the file tree.

Route-group layout notes: `(marketing)` and `(auth)` are groups, so they add no URL segment.
`/app` is a real segment and matches the brief's routes. Marketing pages are statically
generated or ISR; everything under `/app` is dynamic and `noindex`.

**Deviation from the brief's route list:** `/app/rework` is placed above `/app/jobs` in the
navigation and is the post-login landing destination. The review queue is the product; the job
list is a supporting reference view. Beyond ordering, the routes are as specified.

---

## 4. Local development

```bash
make dev          # start postgres; print the two explicit API/web dev commands
make test         # backend pytest (frontend tests have not been added yet)
make lint         # ruff, mypy, import-linter, eslint, tsc
make migrate m="add detection tables"
make contracts    # export OpenAPI and regenerate packages/contracts
make seed-demo    # a realistic HVAC dataset with planted callbacks
make perf-import  # local 50k-row import release gate (real Postgres/RLS/worker path)
```

`make contracts` exports OpenAPI deterministically from the FastAPI application factory without
starting the API or connecting to the database, then runs the pinned `openapi-typescript`
generator. The generated declaration is committed; the frontend's small fetch wrapper imports
its request and response models from it, and CI rejects drift.

`make seed-demo` is worth building early. Developing a detection engine without believable data
means testing against fixtures that always confirm the behaviour you just wrote. The demo set
should contain known callbacks, known maintenance pairs that must be vetoed, and known
unrelated pairs — so a detection change's effect is immediately visible.

The seed is deterministic, local-only, and entirely fictional. It is installed through the same
storage, queue, validation, and processing services used by application imports. A matching second
run performs no writes and preserves organization and job IDs; `RESET=1 make seed-demo` rebuilds
only the reserved `secondtrip-hvac-demo` tenant. Ground-truth pair labels live in
`backend/seeds/data/hvac_demo_expectations.json`, never on operational rows.

Local Postgres runs `postgres:17` in Docker; the RLS app-role bootstrap from
`infra/neon/` is applied by `make dev` so local behaves like production. Developing against a
superuser connection that bypasses RLS and then discovering the policies are wrong in
production is a failure mode worth designing out on day one.

---

## 5. CI

| Workflow | Runs |
| --- | --- |
| `backend.yml` | ruff · mypy (strict) · import-linter · pytest with a real Postgres service · pip-audit |
| `frontend.yml` | eslint · tsc · next build (Vitest joins when frontend tests exist) |
| `contracts.yml` | Export OpenAPI, regenerate types, **fail on any diff** |
| (all) | gitleaks |

Type checking is `mypy --strict` on `app/`. It is painful for the first week and then pays for
itself continuously — particularly around `Decimal`/`float` confusion in money handling, which
is a class of bug that is otherwise invisible until a customer's cost report is wrong.
