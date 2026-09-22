# Production launch runbook

Last audited: 2026-09-22

SecondTrip is not yet approved for a public production launch. The runtime architecture is
sound, but the external services, operational controls, privacy flows, and deployment evidence
below are not all in place. For this personal project, use one gated production stack with only
fictional data until the checks pass; a permanent duplicate staging stack is not required. Paid
launch remains blocked because billing is intentionally `noop` in V1.

This runbook implements the topology in
[`docs/architecture/01-system-architecture.md`](../architecture/01-system-architecture.md).

## 1. Services and resources to create

Create one production stack under the final domains, but keep it private/invite-only and load
only fictional demo data during validation. Use disposable Neon branches, Vercel previews, and
temporary R2 objects when isolation is needed; these are a validation process, not another
always-on application stack.

| Service | Resource to create | Required now | Purpose |
| --- | --- | :---: | --- |
| GitHub | repository + Actions + protected production environment | yes | Source, CI, deployment trigger, environment approvals |
| Domain/DNS | `secondtrip.<root>` + `api.secondtrip.<root>` | yes | Same-site custom domains required for session cookies |
| Vercel | Next.js project, root `frontend/` | yes | SSR frontend and marketing site |
| Render | paid web service, root `backend/` | yes | FastAPI and the in-process PostgreSQL worker |
| Neon | production project with suitable restore history | yes | PostgreSQL, RLS, job queue, analytics store |
| Cloudflare R2 | private production bucket + bucket-scoped token | yes | Source imports and generated reports |
| Resend | verified transactional subdomain + API key | yes | Verification, reset, invitation, and security email |
| Sentry | backend and frontend projects | before beta | Errors and low-rate traces; SDK work is still missing |
| Uptime/log service | `/health` and `/ready` checks + log drain | before beta | Detect failed API, database/storage readiness, and worker stalls |

Vercel Hobby is restricted to personal, non-commercial use. A commercial SecondTrip launch must
use an eligible paid Vercel plan or choose another commercial-compatible Next.js host. Render's
free service sleeps and is inappropriate for the in-process worker, so use always-on paid
compute. Verify current vendor pricing before purchase.

Cloudflare R2 stays private. Do not enable `r2.dev` or a public bucket domain. Browser uploads use
short-lived presigned S3 API URLs and therefore need an exact-origin bucket CORS policy.

## 2. Resources not needed for V1

- No OpenAI, model provider, embeddings, or vector database.
- No Redis, Kafka, Celery, or external scheduler. PostgreSQL is the queue.
- No payment provider until a paid plan is intentionally launched.
- No dedicated worker service until import processing measurably harms API latency. The first
  Render service runs with `WORKER_ENABLED=true`.
- No public R2 CDN or persistent Render disk.

Optional after the production gates are green: Plausible for marketing analytics, Better Stack
or Axiom for longer log retention, and a dedicated Render worker when the trigger in
[`09-background-jobs.md`](../architecture/09-background-jobs.md) is reached.

## 3. Domain and cookie layout

Authentication requires the frontend and API to share a parent domain:

```text
frontend  https://secondtrip.<root>
API       https://api.secondtrip.<root>
cookie    .secondtrip.<root>
```

Do not attempt production authentication with a `vercel.app` frontend and an `onrender.com`
API; those hosts are cross-site. The backend now
fails startup in production when `COOKIE_DOMAIN` is missing, does not parent both public hosts,
or `CORS_ALLOWED_ORIGINS` omits `FRONTEND_URL`.

## 4. Database creation

1. Create the Neon project in the same region as the Render service where possible.
2. Keep the Neon owner role only for bootstrap and Alembic.
3. Create `secondtrip_app` as a non-owner, non-`BYPASSRLS` role with a unique password.
4. Run `infra/neon/bootstrap.sql` once as the migration owner.
5. Set `DATABASE_URL` to the pooled endpoint using `secondtrip_app`.
6. Set `DATABASE_URL_MIGRATIONS` to the direct endpoint using the owner role.
7. Run `uv run alembic upgrade head`, then `uv run alembic check`.
8. Confirm app-role RLS security tests locally and, before customer data, against a disposable
   Neon branch made from the production project.
9. Configure the required history/backup window and complete a timed restore drill before
   production data is accepted.

Never expose the owner URL to the running application. Store both URLs only in Render's secret
environment; the frontend never receives database credentials.

## 5. R2 creation

For the production environment:

1. Create one private bucket.
2. Keep all public access and `r2.dev` disabled.
3. Create an object read/write token scoped only to that bucket.
4. Apply `infra/r2/cors.example.json` with the exact frontend origin.
5. Add the incomplete-multipart-upload lifecycle rule described in `infra/r2/README.md`.
6. Configure `STORAGE_PROVIDER=r2`, bucket, S3 endpoint, access key, secret, and
   `STORAGE_REGION=auto` on Render.
7. Before accepting customer data, complete a real upload, `HEAD`, download, error-report, and
   cleanup test using fictional data.

## 6. Resend creation

1. Verify a dedicated transactional sending subdomain instead of the root domain.
2. Publish the provider's SPF and DKIM records; add DMARC before public launch.
3. Create a production API key scoped as narrowly as the account supports.
4. Set `EMAIL_PROVIDER=resend`, `EMAIL_API_KEY`, and an address on the verified subdomain.
5. Exercise verification, password reset, invitation, password-change notification, and
   email-change notification with your own test addresses before inviting users. The adapter
   has not yet had a credentialed smoke test.

## 7. Deployable processes

The committed deployment package consists of:

- `render.yaml` — one paid Render API service with the in-process worker;
- `frontend/vercel.json` — deterministic Vercel install/build commands;
- `deploy/env/*.example` — secret-free environment-name templates;
- `scripts/smoke-deployment.sh` — read-only liveness, readiness, auth-gate, CORS, and
  private-cache checks;
- [`migrate-and-rollback.md`](migrate-and-rollback.md) — release and recovery procedure.

### Vercel frontend

- Root directory: `frontend`
- Install: `pnpm install --frozen-lockfile`
- Build: `pnpm build`
- Required environment:
  - `NEXT_PUBLIC_API_URL=https://api.secondtrip.<root>`
  - `API_INTERNAL_URL=https://api.secondtrip.<root>` unless private cross-cloud networking is
    added later
- Attach the frontend custom domain before testing authentication.

### Render API + worker

- Root directory: `backend`
- Build: install `uv`, then `uv sync --locked --no-dev`
- Pre-deploy: `uv run alembic upgrade head`
- Start: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/ready`; external uptime check: `/health`
- No persistent disk
- One instance initially, `WORKER_ENABLED=true`

Set every backend variable documented in [`17-configuration.md`](../architecture/17-configuration.md)
that is implemented by `backend/app/core/settings.py`. At minimum: production URLs and secret,
cookie/CORS values, both database URLs, R2 credentials, Resend credentials, JSON logging, and
worker bounds. Generate `APP_SECRET` with a cryptographically secure generator; never reuse the
example value.

## 8. Release order

1. Merge only after backend, frontend, and contract workflows pass in GitHub Actions.
2. Snapshot/restore point the production database.
3. Run the one-time role bootstrap when creating a database.
4. Run Alembic as the owner/direct connection before new application code receives traffic.
5. Deploy Render and require `/ready` success.
6. Deploy Vercel.
7. Run production-gate smoke tests with fictional data: registration, email verification, login,
   organization, invitation, import upload/profile/map/validate/commit/process, detection,
   review, and logout.
8. Verify private-cache headers, CSRF rejection, tenant isolation, R2 privacy, email delivery,
   logs without PII, and alerts.
9. Record the release SHA and rollback point.

## 9. Blocking production gates

### Security and operations

- [ ] GitHub Actions has run green on the actual remote repository; dependency audit is blocking,
      not `continue-on-error`.
- [x] Deployment manifests and commands are committed, locally validated, and reproduced in a
      runbook. Provider-dashboard values still require review when the resources are created.
- [ ] Production custom domains, secure shared cookie domain, and exact CORS origins work in all
      target browsers.
- [ ] Credentialed R2 and Resend smoke tests pass with fictional data.
- [ ] Sentry backend/frontend integrations exist with PII scrubbing verified.
- [ ] Uptime checks, durable logs, queue-stall alerting, and an incident contact exist.
- [ ] Neon restore and application recovery are rehearsed, timed, and documented.
- [ ] Frontend security headers/CSP are reviewed; the current app proxy does not supply the full
      production policy on every public route.
- [ ] The gated production deployment passes the end-to-end browser workflow with fictional data.

### Privacy and product integrity

- [ ] Organization/account deletion, export, retention, and purge workflows in
      [`12-privacy-and-data-lifecycle.md`](../architecture/12-privacy-and-data-lifecycle.md) exist
      and are tested.
- [ ] Privacy policy, terms, DPA, and subprocessor list are published; current footer links do not
      yet have pages.
- [ ] The Microsoft Excel formula-safety check is completed.
- [ ] Fifty candidates from real, permissioned customer data are manually reviewed for quality.
- [ ] Frontend component/integration and critical-path browser tests run in CI.
- [ ] Production support and data-incident procedures have an owner.

### Paid launch only

- [ ] Implement and test a real billing adapter, checkout, portal, signed webhooks, reconciliation,
      tax/pricing disclosures, and cancellation behavior. Until then, launch only a free/private
      beta and keep `BILLING_PROVIDER=noop`.

## 10. Current audit conclusion

The application can be deployed as a gated production instance after the services in section 1
are created. It must not yet be described as ready for real customer data. The shortest safe
path is: create the services and final domains, deploy the committed configuration, load only
fictional data, complete the R2 and Resend smoke tests, implement observability and privacy
operations, and run the restore and end-to-end drills before opening the private beta.
