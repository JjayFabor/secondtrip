# 09 — Background Processing

A PostgreSQL-backed job queue. No Redis, no Celery, no broker. The design target is a system
that is correct under crashes and redeploys, costs nothing at idle, and can be swapped for a
real broker later without touching a single handler.

---

## 1. Job types

| `job_type` | Trigger | Idempotency key | Priority |
| --- | --- | --- | --- |
| `import.profile` | File uploaded | `import:{batch_id}:profile` | 10 |
| `import.validate` | Mapping confirmed | `import:{batch_id}:validate` | 10 |
| `import.process` | Commit | `import:{batch_id}:process` | 10 |
| `import.error_report` | Validate/process finished with issues | `import:{batch_id}:report` | 50 |
| `detection.run` | Import completed, rules changed, manual | `detection:{run_id}` | 20 |
| `embeddings.backfill` | New/changed job text | `embed:{org_id}:{chunk_id}` | 80 |
| `detection.rescore` | Embeddings landed | `rescore:{run_id}` | 30 |
| `ai.classify_candidate` | Gate passed (V1: disabled) | `ai:{candidate_id}:{prompt_version}` | 60 |
| `analytics.refresh` | Review recorded, import completed | `analytics:{org_id}:{period}` | 70 |
| `export.generate` | User request | `export:{export_id}` | 40 |
| `org.purge` | Deletion grace period elapsed | `purge:{org_id}` | 90 |
| `system.sweep_stale_jobs` | Cron, every minute | — | 5 |
| `system.purge_expired_tokens` | Cron, daily | — | 95 |
| `system.prune_import_rows` | Cron, daily | — | 95 |
| `system.prune_candidate_signals` | Cron, daily | — | 95 |

Lower priority number = runs first. Import work outranks embeddings deliberately: a user is
watching an import progress bar, and nobody is watching a backfill.

---

## 2. Claiming work

```sql
WITH claimed AS (
    SELECT id
    FROM   background_jobs
    WHERE  status = 'queued'
      AND  run_at <= now()
      AND  NOT cancel_requested
    ORDER  BY priority, run_at, id
    LIMIT  :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE background_jobs j
SET    status       = 'processing',
       locked_at    = now(),
       locked_by    = :worker_id,
       heartbeat_at = now(),
       attempts     = j.attempts + 1,
       updated_at   = now()
FROM   claimed c
WHERE  j.id = c.id
RETURNING j.*;
```

`FOR UPDATE SKIP LOCKED` is the whole mechanism: concurrent workers skip rows another worker
has locked instead of blocking on them. Two workers polling simultaneously claim disjoint
sets, with no coordination and no broker.

Supported by the partial index `(status, run_at, priority) WHERE status = 'queued'` — partial
so the index contains only pending work. Without `WHERE`, the index grows with completed
history forever and the claim query degrades as the table ages.

`attempts` is incremented **at claim time, not at failure time**. If a worker is SIGKILLed
mid-job, the attempt still counted, so a job that reliably crashes the process cannot retry
infinitely.

### The poll loop

```python
async def run_worker(worker_id: str, stop: asyncio.Event) -> None:
    backoff = POLL_MIN          # 0.5 s
    while not stop.is_set():
        jobs = await claim(worker_id, batch_size=WORKER_BATCH_SIZE)
        if not jobs:
            await wait_or_stop(stop, backoff)
            backoff = min(backoff * 2, POLL_MAX)   # 5 s ceiling
            continue
        backoff = POLL_MIN
        await asyncio.gather(*(execute_guarded(j) for j in jobs))
```

Adaptive backoff keeps an idle deployment from issuing two queries a second forever, which on
Neon's usage-based pricing is a genuine (if small) cost, and prevents the branch from being
kept artificially warm at 3am. `LISTEN/NOTIFY` on enqueue is a worthwhile latency optimisation
later; polling is correct and simpler now.

---

## 3. Execution, heartbeats, and staleness

```python
async def execute_guarded(job: BackgroundJobRow) -> None:
    tenant = TenantContext(organization_id=job.organization_id,
                           actor_user_id=job.enqueued_by_user_id,
                           role=None, request_id=job.correlation_id)
    heartbeat = asyncio.create_task(beat(job.id, interval=15))
    try:
        handler = REGISTRY[job.job_type]
        payload = handler.payload_model.model_validate(job.payload)
        async with asyncio.timeout(handler.timeout_seconds):
            await handler(tenant, payload, JobControl(job.id))
        await mark_completed(job.id)
    except JobCancelled:
        await mark_cancelled(job.id)
    except Exception as exc:                    # noqa: BLE001 — the boundary owns this
        await mark_failed_or_retry(job.id, exc)
    finally:
        heartbeat.cancel()
```

- **Heartbeat** every 15 s updates `heartbeat_at`. `system.sweep_stale_jobs` resets any row
  with `status = 'processing' AND heartbeat_at < now() - interval '2 minutes'` back to
  `queued`, which is how a SIGKILLed worker's in-flight jobs recover. Heartbeat, not
  `locked_at`, because a legitimately long job (a 1M-row import) would otherwise be stolen
  mid-flight and run twice.
- **Per-handler timeout**, declared in the registry. A hung provider call must not hold a
  slot forever.
- **Payload validated with Pydantic** on every execution. Payloads are written by a previous
  deploy's code and read by the current one; a schema mismatch must be a clean validation
  failure, not a `KeyError` three frames deep.
- The broad `except` is correct **here and only here** — this is the boundary whose job is to
  turn any failure into a recorded state transition.

---

## 4. Retries & backoff

```python
delay = min(BASE_DELAY * 2 ** (attempts - 1), MAX_DELAY)   # 10s base, 1h cap
jitter = random.uniform(0, delay * 0.25)                   # full-ish jitter
run_at = now() + timedelta(seconds=delay + jitter)
```

10 s → 20 s → 40 s → 80 s → 160 s, capped at 1 h, ±25% jitter. Jitter matters because a
provider outage fails every queued embedding job at nearly the same instant; without it they
all retry in lockstep and hammer the recovering provider.

**Non-retryable failures fail immediately**, without consuming attempts: payload validation
errors, missing referenced entities, entitlement denials, 4xx provider errors. These are
raised as `PermanentJobError` and the handler registry distinguishes them. Retrying a
structurally invalid job five times is pure waste and delays real work.

On exhausting `max_attempts`: `status = 'failed'`, `last_error` populated (truncated to 4 KB,
**passed through log redaction** — see [18 §5](18-observability.md)), the owning domain object
is moved to a failure state (e.g. `import_batches.status = 'failed'`), an audit event is
emitted, and the user is notified where they would reasonably be waiting.

A failed job can be retried manually from the UI by an admin, which resets `attempts = 0`,
`status = 'queued'`.

---

## 5. Idempotency

Three mechanisms, because at-least-once delivery is the only guarantee this design offers:

1. **Enqueue-time deduplication** —
   `UNIQUE (job_type, idempotency_key) WHERE idempotency_key IS NOT NULL AND status <> 'failed'`.
   A double-clicked "Process import" enqueues once. The failed-status exclusion permits a
   legitimate retry after permanent failure.
2. **Handler-level idempotency** — every handler must be safe to run twice. Enforced by
   convention and by test ([19 §6](19-testing-strategy.md)):
   - `import.process` — checkpointed `processed_rows` + row-level upserts
   - `detection.run` — candidate upserts on the pair unique key
   - `embeddings.backfill` — upsert on `(job_id, content_scope, model_key)`
   - `ai.classify_candidate` — dedup on `input_hash` before dispatch
   - `analytics.refresh` — full recompute of a period, not an increment
3. **Transactional enqueue** — the `INSERT INTO background_jobs` happens in the *same
   transaction* as the state change that justifies it. If the import batch commits, its job
   committed too; if the transaction rolls back, no orphan job exists. This is what removes
   the need for an outbox pattern.

Rule 3 has a corollary worth stating explicitly: **never enqueue a job for a row you have not
yet committed.** A worker on another process can claim the job microseconds after commit, and
if the row it references is still uncommitted, it fails confusingly.

---

## 6. Cancellation

Cooperative, because a `SIGKILL`-style cancel would leave partial writes uncheckpointed.

```python
# inside a long handler, at each chunk boundary
await control.checkpoint(processed_rows=n)   # raises JobCancelled if cancel_requested
```

`POST /imports/{id}/cancel` sets both `import_batches.cancel_requested_at` and
`background_jobs.cancel_requested`. A queued (unclaimed) job is cancelled immediately at claim
time. An in-flight job stops at its next checkpoint, retaining completed work and reporting
exactly how much was imported. Partial state is a legitimate, inspectable outcome — not an
error.

---

## 7. Deployment: in-process in V1

`WORKER_ENABLED=true` starts the worker as an `asyncio` task inside the FastAPI lifespan,
sharing the API process. This saves a second Render service ($7/mo), which at this stage of
the project is a real consideration.

**The honest trade-off:** CSV parsing and scoring compete with request handling in the same
process and the same GIL. Mitigations, all of which are requirements rather than suggestions:

- `WORKER_CONCURRENCY` defaults to **2**.
- Handlers `await` at every chunk boundary so the event loop stays responsive.
- **Any CPU-bound step** (hashing a 200 MB file, large CSV parse loops) runs in
  `asyncio.to_thread` / `run_in_executor`. A tight synchronous loop over 250k rows blocks the
  event loop and stalls every concurrent HTTP request — this is the specific failure mode to
  watch for.
- The database pool is sized for both consumers ([01 §6](01-system-architecture.md)).
- Graceful shutdown: on SIGTERM, stop claiming, let in-flight jobs reach their next checkpoint
  (up to 25 s — Render's grace period is 30 s), then exit. Unfinished jobs return to `queued`
  via the stale sweep.

Setting `WORKER_ENABLED=false` on the API and deploying a second Render service with
`WORKER_ENABLED=true` and no HTTP port splits them. **That is a configuration change with no
code change**, which is the property this design exists to preserve.

### Scheduling

Cron jobs (`system.sweep_stale_jobs` and friends) are driven by a small internal scheduler in
the same worker: on each loop iteration, insert any due periodic job whose
`idempotency_key = f"{job_type}:{minute_bucket}"` does not yet exist. The unique constraint
makes concurrent workers safe, and there is no external cron dependency. Render Cron Jobs are
an alternative but cost another service.

---

## 8. Observability

Every job logs, with `job_id`, `job_type`, `organization_id`, `attempt`, `correlation_id`:

| Event | Level |
| --- | --- |
| `job.claimed` | debug |
| `job.completed` (+ `duration_ms`) | info |
| `job.retrying` (+ `next_run_at`, error class) | warning |
| `job.failed_permanently` | error → Sentry |
| `job.cancelled` | info |
| `job.stale_recovered` | warning |

Health signals worth alerting on: queue depth by type, oldest queued job's age, failure rate
per type, stale recoveries per hour. A rising `job.stale_recovered` count means the worker is
crashing or being OOM-killed, and it is the earliest warning available.

---

## 9. When to graduate to a real broker

Postgres queues are genuinely good up to a point. The honest limits:

| Signal | Threshold |
| --- | --- |
| Sustained throughput | > 5 jobs/sec for minutes at a time |
| Claim-query latency | p95 > 50 ms (index bloat from high churn) |
| Worker count | > 3 instances contending on the same partial index |
| Latency requirement | Sub-second job pickup needed (polling floor is ~0.5 s; `LISTEN/NOTIFY` buys one order of magnitude before a broker is required) |
| Topology | Genuine fan-out/fan-in, chords, or workflow chaining |
| Table churn | `background_jobs` autovacuum unable to keep up |

**Recommended graduation: Dramatiq + Redis**, not Celery — a smaller surface area, a saner
async story, and far less configuration for this workload. Migration path:

1. Handlers already take `(tenant, payload, control)` and are already idempotent — they move
   unchanged.
2. `JobQueue` becomes a protocol with `PostgresJobQueue` and `RedisJobQueue` implementations.
3. Run both in parallel during cutover: new jobs to Redis, drain Postgres.
4. Retain `background_jobs` as the **audit and status record** even after Redis owns dispatch —
   users want to see import history, and Redis is the wrong place for it.

Do not graduate for aesthetics. The trigger is one of the rows above, measured.
