# 01 — System Architecture

---

## 1. Runtime topology

```
                        ┌──────────────────────────────┐
   Browser ────────────▶│  Vercel — Next.js (App Router)│
                        │  • marketing (static/ISR)     │
                        │  • /app (dynamic, auth-gated) │
                        │  • route handlers = thin BFF  │
                        └───────────────┬───────────────┘
                                        │ HTTPS, cookie forwarded
                                        │ (server-side fetch)
                        ┌───────────────▼───────────────┐
                        │  Render — FastAPI (uvicorn)    │
                        │  ┌──────────────────────────┐  │
                        │  │ API process              │  │
                        │  │  + in-process worker loop│  │  ← V1 only; split later
                        │  └──────────────────────────┘  │
                        └───┬───────────┬────────────┬───┘
                            │           │            │
              ┌─────────────▼──┐  ┌─────▼──────┐  ┌──▼──────────────┐
              │ Neon Postgres  │  │ Cloudflare │  │ Providers        │
              │ + pgvector     │  │ R2         │  │ • OpenAI (AI)    │
              │ • operational  │  │ • imports  │  │ • Resend (email) │
              │ • derived      │  │ • exports  │  │ • (billing: none │
              │ • queue        │  │ (private)  │  │    yet)          │
              └────────────────┘  └────────────┘  └──────────────────┘
```

Direct browser → R2 uploads bypass the API entirely using presigned `PUT` URLs, so a 40 MB
CSV never occupies a Render request worker or Vercel's 4.5 MB body limit.

---

## 2. Why the frontend talks to the backend server-side

The session cookie is `httpOnly`, so client JavaScript cannot read it. Two viable patterns:

1. **Browser → FastAPI directly** with `credentials: "include"` and a CORS allowlist.
2. **Browser → Next.js route handler / RSC → FastAPI**, forwarding the cookie.

We use **(2) for all authenticated reads and mutations that benefit from server rendering**,
and allow **(1)** for interactive client-side calls (filtering a job table, polling an import's
progress) to avoid a pointless extra hop.

Both work only if the cookie is scoped to a **parent domain** shared by both origins:

- Frontend: `secondtrip.<root-domain>`
- API: `api.secondtrip.<root-domain>`
- Cookie `Domain=.secondtrip.<root-domain>`, `SameSite=Lax`, `Secure`, `HttpOnly`

**This is a hard deployment constraint.** If the API lives on `*.onrender.com` and the app on
`*.vercel.app`, they are cross-site: `SameSite=Lax` will not send the cookie and `SameSite=None`
is increasingly blocked by browser privacy defaults. Custom domains on both sides are required
before authentication works properly — not a polish item. The root domain is read from
`COOKIE_DOMAIN`; nothing hard-codes `secondtrip.jjayfabor.com`.

---

## 3. The two flows that matter

### 3.1 Synchronous request path

```
Request
  → RequestIdMiddleware        assign/propagate X-Request-Id
  → LoggingMiddleware          bind request_id, method, path to structlog contextvars
  → SessionAuthDependency      cookie → session row → user (or 401)
  → OrgContextDependency       path org_id → membership + role → TenantContext (or 403/404)
  → EntitlementDependency      optional, for gated actions
  → Router handler             pure I/O shape: validate in, call service, serialize out
      → Service                domain logic, transaction boundary, emits audit events
          → Repository         tenant-scoped queries only
              → Postgres       RLS enforces org scope as a backstop
```

The transaction boundary is the **service method**, not the request. A handler that calls two
services performs two transactions; if that is wrong, the operation belongs in one service
method. This keeps transaction scope legible and avoids a request-scoped `UnitOfWork` that
quietly holds a connection across an outbound HTTP call.

**Rule:** never hold a database transaction open across a provider call (AI, email, storage).
Commit, then call, then record the outcome in a second transaction.

### 3.2 Asynchronous processing path

```
Service enqueues background_jobs row (same transaction as the state change)
  → Worker loop polls: SELECT ... FOR UPDATE SKIP LOCKED
  → Rehydrate TenantContext from the row's organization_id  ← never from ambient state
  → Handler executes, heartbeating
  → Success: status=completed | Failure: attempts++, run_at = backoff, status=queued|failed
```

Enqueueing inside the same transaction as the state change is what makes the system
transactionally consistent without an outbox service: if the import batch commits, its
processing job committed with it; if it rolled back, so did the job.

---

## 4. The end-to-end product pipeline

```
 CSV upload (browser → R2 presigned PUT)
   │
   ▼  import.profile        detect encoding/delimiter/headers, sample rows
 Preview + column mapping (human, or auto-suggested from templates)
   │
   ▼  import.validate       dry run; per-row errors; nothing written to operational tables
 Import confirmation (human)
   │
   ▼  import.process        raw rows → normalize → upsert customers/locations/equipment/jobs
   │
   ▼  detection.generate    Stage 1: blocked candidate generation
   ▼  detection.score       Stage 2 + 4: deterministic signals → explainable score
   ▼  embeddings.backfill   Stage 3: embed new job text (async, non-blocking)
   ▼  detection.rescore     re-score with similarity signal once embeddings land
   ▼  [ai.classify]         Stage 5: feature-flagged off in V1
   │
   ▼  Human review          Stage 6: confirm / reject / categorise → layer-4 truth
   │
   ▼  analytics.refresh     root-cause + cost rollups
```

Note the **two-pass scoring**: candidates are scored immediately on deterministic signals so
the user sees results within seconds of an import finishing, then re-scored when embeddings
complete. A user never waits on the embedding provider to see their first findings. This also
means the similarity signal's absence must be a *first-class state* (`unavailable`), distinct
from "computed, and it was low" — see [07-detection-engine.md §4](07-detection-engine.md).

---

## 5. Module boundaries and dependency rules

```
app/modules/
  identity          users, credentials, sessions, verification, password reset
  organizations     orgs, memberships, roles, invitations, settings
  customers         customers, locations, equipment
  workforce         technicians
  jobs              jobs, notes, line items
  imports           batches, rows, mappings, templates, error reports
  detection         rule sets, signals, candidate generation, scoring
  reviews           human classification, categories, root causes
  analytics         aggregates, cost calculation
  costs             cost models
  billing           plans, entitlements, subscriptions
  audit             audit events
  tasks             background job queue + worker
```

**Allowed dependencies**

- Any module may depend on `core/`, `db/`, `shared/`, and `providers/` protocols.
- A module may call another module's **service**. It may never import another module's
  **repository** or ORM model.
- `detection` may read `jobs` through `jobs`' service/read-model, not its repository.
- `audit` and `tasks` are leaf infrastructure: everything may call them, they call nothing
  except `core`.
- No cycles. Enforced with `import-linter` in CI ([19-testing-strategy.md §7](19-testing-strategy.md)).

The one intentional exception: `detection` runs bulk SQL that joins `jobs` directly for
candidate generation. Reading a million rows through a service API would be absurd. This is
allowed via a **read-model** — a narrow, explicitly-exported SQLAlchemy selectable published
by `jobs` (`jobs/read_models.py`) that `detection` may use. Writes still go through services.

---

## 6. Technology choices, confirmed and justified

| Layer | Choice | Note |
| --- | --- | --- |
| Frontend | Next.js (App Router) + TypeScript | Marketing pages need static generation and metadata control; the app needs server-side auth checks. Same framework for both avoids a second stack. |
| Styling | Tailwind CSS + a small component set (shadcn-style, vendored) | Vendored, not a dependency-heavy UI kit. Keeps the design under our control. |
| Backend | FastAPI + Pydantic v2 | Pydantic v2 gives us request validation *and* AI structured-output validation from the same models. |
| ORM | SQLAlchemy 2.x async + Alembic | Async matters because the workload is I/O-bound (Neon over the network, provider calls). |
| DB | Neon Postgres + `pgvector` | Scale-to-zero pricing matches an idle side project. |
| Driver | `asyncpg` via `postgresql+asyncpg://` | |
| Storage | Cloudflare R2 via S3-compatible API (`aioboto3`) | Zero egress fees. |
| Email | Resend behind `EmailProvider` | |
| Deploy | Vercel (frontend), Render (API) | |
| AI | OpenAI behind `AIProvider` | |

### Neon-specific constraints implementers must respect

1. **Connection pooling.** Neon's pooled endpoint is PgBouncer in transaction mode. Prepared
   statements must be disabled on the asyncpg driver (`statement_cache_size=0` /
   `prepared_statement_cache_size=0`), or you will hit "prepared statement already exists"
   under load. Use the **pooled** endpoint for the API and the **direct** endpoint for Alembic
   migrations.
2. **`SET LOCAL` is safe in transaction mode** (it is scoped to the transaction PgBouncer is
   already holding), `SET` is not. Our RLS context-setting uses `SET LOCAL` exclusively.
3. **Scale-to-zero cold starts** add latency to the first request after idle. Acceptable for a
   side project; the background worker's poll loop will in practice keep the branch warm.
4. Keep the SQLAlchemy pool small (`pool_size=5, max_overflow=5`) — Neon's connection limits
   are lower than a self-hosted Postgres, and the worker shares the budget.

---

## 7. Cost model at launch

| Item | Plan | Monthly |
| --- | --- | --- |
| Vercel | Hobby | $0 |
| Render | Starter web service (avoids sleep-on-idle) | ~$7 |
| Neon | Free tier initially | $0 |
| Cloudflare R2 | Free tier (10 GB, no egress fees) | $0 |
| Resend | Free tier (3k emails/mo) | $0 |
| Sentry | Developer tier | $0 |
| OpenAI embeddings | ~$0.02 per 1M tokens (`text-embedding-3-small`); 100k jobs ≈ 15M tokens | ~$0.30 one-off |
| **Total** | | **~$7/month** |

The single largest avoidable cost would be a dedicated Render Background Worker (+$7/mo).
V1 therefore runs the worker **in-process** in the API service, guarded by `WORKER_ENABLED`.
The trade-off is honest and must be respected: a long CSV parse competes with request handling
in the same container. Mitigations in [09-background-jobs.md §7](09-background-jobs.md)
(bounded worker concurrency, chunked processing with `await` yield points, no CPU-bound work
without `run_in_executor`). The flag exists so that splitting the worker into its own Render
service is a config change, not a refactor.

---

## 8. What would make us change this architecture

| Signal | Response |
| --- | --- |
| Import processing regularly delays API p95 beyond 500 ms | Split the worker into a dedicated Render Background Worker (`WORKER_ENABLED=false` on the API) |
| Sustained > 5 queued jobs/sec, or need for fan-out/chaining | Move to Redis + Dramatiq; keep handler signatures identical |
| A single org exceeds ~1M jobs | Partition `jobs` and `job_embeddings` by `organization_id` hash; see [04-data-model.md §15](04-data-model.md) |
| Vector similarity search (not pairwise) becomes a core feature | Add HNSW index; evaluate `hnsw.iterative_scan` for the org-filter recall problem |
| Multi-region latency complaints | Neon read replica + Render region pinning, not a rewrite |
