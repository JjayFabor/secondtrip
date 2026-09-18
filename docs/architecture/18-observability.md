# 18 — Observability

Budget: **$0/month at launch.** The goal is not a dashboard suite; it is the ability to answer
"what happened to this customer's import?" from a request ID, without paying an APM vendor.

---

## 1. Stack

| Concern | V1 | Upgrade path |
| --- | --- | --- |
| Logs | structlog → JSON → stdout → Render log stream | Better Stack / Axiom free tier (log drain) |
| Errors | Sentry free tier (backend + frontend) | Paid tier for volume |
| Metrics | Derived from the database via an internal ops endpoint | Grafana Cloud free tier + `prometheus-fastapi-instrumentator` |
| Tracing | Sentry performance at 5% sampling | OpenTelemetry → Grafana Tempo |
| Uptime | Better Uptime / UptimeRobot free ping on `/health` | Multi-region checks |
| Product analytics | Plausible (optional) | — |

Database-derived metrics are not a compromise here: queue depth, import throughput, detection
counts and AI spend all already live in Postgres as first-class rows. Shipping them to a
metrics backend to read them back would be the more complicated option, not the simpler one.

---

## 2. Structured logging

```python
log.info("import.completed",
         import_batch_id=str(batch.id),
         organization_id=str(tenant.organization_id),
         total_rows=batch.total_rows,
         created_jobs=batch.created_jobs,
         error_rows=batch.error_rows,
         duration_ms=elapsed_ms)
```

```json
{"event":"import.completed","level":"info","timestamp":"2026-09-16T10:31:02.441Z",
 "request_id":"01JQ8X...","organization_id":"0192...","import_batch_id":"0193...",
 "total_rows":58231,"created_jobs":57904,"error_rows":327,"duration_ms":41208,
 "service":"secondtrip-api","env":"production","version":"a3f9c21"}
```

Event names are dotted and stable (`import.completed`, `detection.run.completed`,
`ai.request.failed`) so they can be grepped and later turned into metrics without editing call
sites.

### Context binding

`structlog.contextvars` binds once per request and per job; every subsequent log line inside
that scope carries it automatically:

| Field | Bound by |
| --- | --- |
| `request_id` | `RequestIdMiddleware` — from `X-Request-Id` or generated (UUIDv7) |
| `organization_id` | `require_org_context` |
| `user_id` | `require_session` |
| `job_id`, `job_type`, `attempt` | Worker `execute_guarded` |
| `correlation_id` | Carried from the enqueuing request into the job |

`correlation_id` is the one that pays for itself: a user reports "my import from Tuesday
failed," and a single `request_id` search returns the HTTP request, the enqueue, every worker
attempt, and the provider calls — across two processes.

`X-Request-Id` is echoed on every response and surfaced in the UI's error state, so a user can
paste it into a support message.

---

## 3. What is logged

| Event | Level | Key fields |
| --- | --- | --- |
| `http.request` | info | method, path template, status, duration_ms |
| `http.request.slow` | warning | above 1000 ms |
| `auth.login.succeeded` / `.failed` | info / warning | user_id or email **hash**, ip_hash, reason |
| `auth.session.revoked` | info | reason, count |
| `import.*` | info | batch id, counts, duration |
| `import.row.rejected` | debug | row number, **error code only — never the row content** |
| `detection.run.*` | info | run id, pairs, candidates, duration |
| `job.*` | per [09 §8](09-background-jobs.md) | |
| `ai.request.*` | info / warning | model, operation, tokens, cost, latency, status |
| `ai.budget.exceeded` | warning | org, period, spend |
| `entitlement.denied` | info | key, limit, current |
| `storage.*` | info | operation, key **prefix only** |
| `tenant.access_denied` | **warning** | user_id, attempted org — a possible attack signal |
| `security.rate_limited` | warning | bucket, ip_hash |

Note `import.row.rejected` logs the error code and row number, never the cell values. The row
content is already stored in `import_rows` where it is tenant-scoped, access-controlled, and
subject to retention — putting it in a log stream would defeat all three.

`tenant.access_denied` is deliberately `warning`. In normal operation it should be near zero;
a cluster of them is either a bug or someone probing, and both deserve attention.

---

## 4. Metrics

An internal `GET /internal/metrics` endpoint (protected by `INTERNAL_METRICS_TOKEN`, never
public) returns the operational picture as JSON:

**Queue health** — depth by type and status, oldest queued job age, processing count, failures
in 24h, stale recoveries in 24h.

**Imports** — batches by status in 24h, median rows/second, median duration, error-row rate,
failed batches.

**Detection** — runs in 24h, pairs evaluated, candidates created, suppression rate, median run
duration, candidates awaiting review, median time-to-review.

**AI** — requests and cost by model in 24h and month-to-date, p50/p95 latency, error rate,
invalid-output rate, orgs over budget.

**Business** — active orgs, orgs with ≥1 import, jobs imported in 24h, reviews recorded in 24h,
confirmation rate by band ([07 §8](07-detection-engine.md)).

Each is a single SQL aggregate. The endpoint is the seed of a future `/metrics` in Prometheus
format — the queries stay, only the serialization changes.

### Alerts worth having

| Condition | Why |
| --- | --- |
| Oldest queued job > 15 min | The worker is dead or wedged — the highest-signal alert in the system |
| Stale recoveries > 5/hour | Worker crashing or being OOM-killed |
| Import failure rate > 10% in 24h | Parser regression or a systematically bad export format |
| AI error rate > 20% in 1h | Provider incident; verify degradation is working |
| Any org over AI budget | Cost control |
| `tenant.access_denied` spike | Possible probing |
| `/health` down 2 min | Standard uptime alert |

Delivered by email via the existing `EmailProvider` in V1 — no PagerDuty, no on-call rotation
for a side project. A daily digest of the metrics above is more valuable than most real-time
alerting at this stage.

---

## 5. Redaction

A structlog processor runs on every event, before any output:

```python
SENSITIVE_KEYS = frozenset({
    "password", "password_hash", "token", "token_hash", "secret", "api_key",
    "authorization", "cookie", "session", "signed_url", "email",
    "customer_name", "address", "phone", "note", "body", "description",
    "symptoms_text", "diagnosis_text", "resolution_text", "raw_data",
})
```

Matching keys are replaced with `"***"`. Values containing `X-Amz-Signature` are scrubbed
regardless of key name, which catches a signed URL logged under an innocuous name.

**The processor is a safety net, not the policy.** The policy is that these fields are never
passed to a logger in the first place; the processor exists because the policy will eventually
be violated by a debugging line someone forgets to remove. A test asserts the processor
redacts every key in the set.

Sentry: `send_default_pii=False`, plus a `before_send` hook that drops request bodies and
cookies and applies the same key filter to `extra` and breadcrumbs. Verified with a deliberate
PII payload in the pre-launch checklist ([11 §16](11-security-threat-model.md)).

---

## 6. Health checks

| Endpoint | Checks | Used by |
| --- | --- | --- |
| `GET /health` | Process alive. **No database call** | Render liveness, uptime monitor |
| `GET /ready` | `SELECT 1`, storage `head` on a sentinel key, worker heartbeat freshness | Render readiness, deploy gate |

`/health` must not touch the database. A health check that fails during a brief Neon
reconnection causes the platform to restart a perfectly healthy process, turning a two-second
blip into a cold start — and, if the restart loop continues, an outage created entirely by the
monitoring.

---

## 7. Frontend

- Sentry browser SDK: errors, unhandled rejections, 5% performance sampling.
- Web Vitals reported for marketing pages, where they affect search ranking
  ([20 §6](20-frontend-and-seo.md)).
- `request_id` from failed API responses is attached to the Sentry event **and displayed in
  the error UI**, which is what makes a user's bug report actionable.
- Plausible (optional, cookieless) for marketing funnel measurement. No third-party tracker
  loads on `/app` routes — customer data pages should not talk to analytics vendors at all.

---

## 8. Upgrade triggers

| Signal | Action |
| --- | --- |
| Render's log retention too short to investigate | Add a log drain to Axiom/Better Stack free tier |
| Guessing at latency distributions | `prometheus-fastapi-instrumentator` + Grafana Cloud free tier |
| Multi-step failures hard to follow across processes | OpenTelemetry tracing end to end |
| Sentry quota exhausted | Tune sampling before paying; most volume is usually one noisy error |
| More than one person on call | Real alerting and an on-call rotation |
