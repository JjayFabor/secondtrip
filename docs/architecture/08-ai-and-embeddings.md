# 08 — Deferred AI & Embeddings Research

> **Status: deferred and non-binding.** V1 has no AI provider, model calls, embeddings,
> vector storage, AI configuration, or AI entitlements. Detection is deterministic. Keep this
> document only as research that may be reconsidered after real customer review data proves a
> specific quality gap; do not implement it from the current sequencing plan.

**Governing rule:** AI enhances detection. AI does not own the workflow. Every code path that
touches a provider must have a defined behaviour when that provider returns an error, times
out, or is disabled entirely.

---

## 1. The provider protocol

```python
# app/providers/ai/base.py

class AIProvider(Protocol):
    async def embed(
        self, texts: Sequence[str], *, model: str, dimensions: int | None = None
    ) -> EmbeddingBatch: ...

    async def generate_structured[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], model: str,
        max_output_tokens: int = 1024, temperature: float = 0.0,
    ) -> StructuredResult[T]: ...

    async def summarize(
        self, *, text: str, instruction: str, model: str, max_output_tokens: int = 512,
    ) -> TextResult: ...
```

Return types are ours, never the vendor's:

```python
@dataclass(frozen=True, slots=True)
class ProviderUsage:
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: Decimal     # our own computation, from a local price table
    latency_ms: int

@dataclass(frozen=True, slots=True)
class StructuredResult[T]:
    value: T | None
    status: AIStatus            # succeeded | invalid_output | provider_error | refused | timeout
    usage: ProviderUsage
    error: str | None
```

**No OpenAI SDK type ever crosses this boundary.** No `ChatCompletion`, no `openai.APIError`,
no provider-specific enum. Domain services see `StructuredResult[CandidateClassification]`.
The compliance test for this is a lint rule: `openai` may be imported only under
`app/providers/ai/openai/`.

Note `generate_structured` returns a result object rather than raising on provider failure.
Failure is an expected outcome here, not an exception — modelling it in the return type means
a caller cannot forget to handle it.

### Implementations

| Class | Purpose |
| --- | --- |
| `OpenAIProvider` | The real one |
| `NullAIProvider` | Returns `status=provider_error` for generation, raises for `embed`. Wired when `AI_ENABLED=false`. Makes "AI disabled" a first-class, testable configuration rather than a special case |
| `FakeAIProvider` | Deterministic outputs for tests; embeddings derived from a hash of the text so similarity is reproducible |

---

## 2. Models and cost

| Operation | Model | Notes |
| --- | --- | --- |
| Embeddings | `text-embedding-3-small`, `dimensions=768` | Matryoshka truncation from 1536 |
| Classification | A small/cheap chat model with native JSON-schema structured output | Exact model in `AI_CLASSIFICATION_MODEL`; never hard-coded |

**Why 768 dimensions.** `vector(1536)` is 4 bytes/dim + 8 bytes overhead ≈ 6.1 KB per row;
100k jobs × 2 scopes ≈ 1.2 GB — well past Neon's free tier before any other data. At 768 dims
that halves to ~600 MB, and the accuracy loss on short problem descriptions is negligible
(these are 20–60 token strings, not documents). If storage becomes tight again, `halfvec(768)`
halves it once more at 2 bytes/dim with minimal recall impact.

The dimension is recorded in `job_embeddings.model_key`
(`openai:text-embedding-3-small@768`) so a future change produces a *new* key rather than
silently mixing incompatible vectors in one column. **Comparing vectors from two different
model keys is meaningless**, so every similarity query filters `a.model_key = b.model_key`.

**Cost table.** A `PRICE_TABLE: dict[str, ModelPrice]` in
`providers/ai/pricing.py` maps model → per-1M-token input/output prices, used to compute
`estimated_cost` locally. Prices move; the table carries an `as_of` date and a test asserts
every model named in settings has an entry. **Verify current published prices at
implementation time** — the figures in [01 §7](01-system-architecture.md) are order-of-magnitude
estimates for budgeting, not commitments.

---

## 3. Reliability

| Concern | Policy |
| --- | --- |
| Connect timeout | 5 s |
| Read timeout | 30 s (embeddings), 60 s (generation) |
| Retries | 3 attempts, exponential backoff 1s → 2s → 4s, full jitter |
| Retry on | 429, 500, 502, 503, 504, connection errors, timeouts |
| Never retry on | 400, 401, 403, 422, content-policy refusals — retrying a malformed request just burns budget |
| Batch size | 256 texts per embedding request, chunked to stay under the model's token cap |
| Circuit breaker | 5 consecutive failures → open for 60 s, then half-open with one probe |
| Concurrency | Semaphore capped at `AI_MAX_CONCURRENCY` (default 4), so a large backfill cannot saturate the worker |

The circuit breaker matters more than it might appear: without it, a provider outage turns
every queued embedding job into a 3-retry × 30-second stall, and a backfill of 100k jobs
becomes a multi-day queue blockage that also starves every other job type.

### Behaviour when AI is unavailable

| Feature | Degradation |
| --- | --- |
| Embedding backfill | Job fails, retries with backoff; affected candidates stay `similarity_state = 'pending'` |
| Similarity signal | `NOT_EVALUABLE` — excluded from numerator *and* denominator ([07 §4](07-detection-engine.md)) |
| Candidate classification | Skipped; deterministic score stands; UI shows "AI analysis unavailable" |
| Import | **Entirely unaffected** |
| Candidate generation & scoring | **Entirely unaffected** |
| Review, analytics, exports | **Entirely unaffected** |

The last three rows are the point of the whole design. A provider outage costs precision on
one signal. It does not cost availability.

---

## 4. Usage, cost & observability

Every provider call writes an `ai_analyses` row (for generation) and upserts `ai_usage_daily`
(for all operations) in the **same transaction as the result it produced**. Metrics recorded:
provider, model, operation, token counts, estimated cost, latency, status.

Guard rails:

- **Per-org monthly budget** from the `ai_spend_cents` entitlement. `AIUsageService.guard()`
  is called *before* dispatch; exceeding it disables AI features for the period with a clear
  in-app message rather than a silent failure.
- **Global kill switch** `AI_ENABLED=false` swaps in `NullAIProvider` at composition root.
- A daily digest logs total spend per org; a threshold breach raises a Sentry message.

---

## 5. pgvector strategy

### V1: no ANN index, on purpose

The only vector operation in V1 is **pairwise cosine between two known rows**:

```sql
SELECT 1 - (a.embedding <=> b.embedding) FROM job_embeddings a, job_embeddings b
WHERE a.job_id = :prior AND b.job_id = :followup AND a.model_key = b.model_key ...
```

Both rows are found by a unique constraint. An HNSW index would not be used, would add minutes
to every bulk insert, and would consume significant maintenance memory. **Adding it now is a
pure cost.**

For efficiency, the rescore job fetches both vectors for a batch of candidates in one query
and computes cosine in SQL, not in Python — moving 768 floats × 2 × N rows over the wire to do
arithmetic we could have done in the database is the obvious mistake to avoid.

### When search does arrive: the org-filter recall problem

The moment a feature needs *"find the 10 most similar jobs"*, we add:

```sql
CREATE INDEX job_embeddings_hnsw_idx ON job_embeddings
USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
```

and immediately inherit a well-known pgvector trap. The query is:

```sql
SELECT job_id FROM job_embeddings
WHERE organization_id = :org AND model_key = :model
ORDER BY embedding <=> :query_vec
LIMIT 10;
```

HNSW traverses the graph across **all** organizations and *then* applies the
`organization_id` filter. For a small tenant in a large database, the 40 nearest global
neighbours may contain zero rows from that org — so the query returns **fewer than 10 results,
or none at all**, while the data plainly exists. This presents as "search is broken for small
customers," and it is a correctness problem, not a tuning problem.

Three mitigations, in order of preference:

1. **`SET LOCAL hnsw.iterative_scan = 'relaxed_order'`** (pgvector ≥ 0.8) — the index keeps
   scanning until enough rows survive the filter. The right first answer; verify the Neon
   Postgres image ships ≥ 0.8.
2. **Partial indexes per large tenant** — precise but unbounded in count; only for a handful
   of outsized organizations.
3. **Partition `job_embeddings` by `organization_id` hash** with a local index per partition,
   so the filter becomes partition pruning and the ANN search runs *within* one tenant. The
   correct end state at scale, and the reason `organization_id` is on the table at all rather
   than being joined through `jobs`.

**Regardless of index strategy, the `organization_id` predicate is mandatory and never
optional.** It is applied by the repository, and RLS enforces it independently — so the
failure mode of forgetting it is "no results," never "another tenant's results."

### Backfill

- Triggered when `jobs.embedding_content_hash` is NULL or differs from the stored
  `job_embeddings.content_hash`.
- Batched 256 at a time, idempotent (the unique constraint makes a replayed batch a no-op
  upsert).
- Runs at low priority so it never delays import processing or candidate scoring.
- On a model change, the old `model_key` rows remain until a migration job re-embeds and the
  old key is dropped — there is never a window with no usable embeddings.

---

## 6. Embeddings beyond pairwise similarity

Designed for, deliberately **not built in V1**:

| Use case | Approach | Prerequisite |
| --- | --- | --- |
| **Job similarity search** ("find jobs like this") | kNN over `content_scope = 'problem'`, org-filtered | HNSW + §5 mitigations |
| **Recurring symptom discovery** | Periodic clustering (HDBSCAN over one org's vectors, offline) → cluster labels stored as a derived table | Enough volume to be meaningful; ~5k+ jobs |
| **Root-cause analysis** | Aggregate confirmed reviews by cluster; surface "this symptom cluster confirms as `misdiagnosis` 60% of the time" | Depends on review volume — a layer-4 dividend |
| **"Ask SecondTrip"** | Retrieval over org-scoped job text + structured filters, answered with `generate_structured` | Everything above, plus a careful prompt-injection posture since retrieved notes are untrusted |

### RAG boundaries, stated now to avoid a mistake later

1. **Retrieval is always org-scoped at the repository layer.** There is no "search all jobs"
   function. The retrieval API takes a `TenantContext` and cannot be called without one.
2. **Retrieved content is data, never instruction** — same delimiting and framing as
   [07 §6](07-detection-engine.md).
3. **Answers cite job IDs** that the caller re-authorizes before display. If retrieval somehow
   returned a foreign row, the display layer would refuse it — a second independent check.
4. **No cross-tenant learning.** Embeddings, clusters and fine-tuning data are never pooled
   across organizations. Aggregate insights across the customer base (e.g. default weight
   tuning, [07 §8](07-detection-engine.md)) use **counts and rates only**, never text or
   vectors.

Do not build a general RAG framework. When "Ask SecondTrip" is specified, it will be a narrow
retrieval function over one org's jobs with structured filters — closer to search-plus-summary
than to a document-QA system.

---

## 7. Privacy & data minimisation

Service records contain customer names, addresses, and phone numbers. None of that helps
classify a callback.

**Redaction before any provider call** (`providers/ai/redaction.py`):

| Data | Sent? | Treatment |
| --- | --- | --- |
| Customer name | ❌ | Replaced with `[CUSTOMER]` |
| Street address | ❌ | Replaced with `[ADDRESS]` |
| Phone / email | ❌ | Regex-scrubbed to `[PHONE]` / `[EMAIL]` |
| Technician name | ❌ | Replaced with a stable per-org pseudonym (`TECH_A`) so "same technician" remains expressible |
| Job description, symptoms, diagnosis, resolution | ✅ | The signal we actually need |
| Equipment make/model/type | ✅ | Diagnostically relevant |
| Serial number | ❌ | Replaced with `[SERIAL]` — identity, not diagnosis |
| Dates, amounts, durations | ✅ | Non-identifying |
| Job/customer UUIDs | ❌ | Never sent; correlation is held on our side |

Redaction is **best-effort on free text** — a technician may have typed a customer's name into
a note, and no regex catches every case. It is therefore paired with contractual and
configuration controls rather than presented as a guarantee:

- `AI_ZERO_RETENTION=true` asserts the provider account is configured for zero data retention;
  the setting is documented as an operational prerequisite, not enforced by code.
- An org-level `ai_enabled` setting lets a privacy-sensitive customer switch AI off entirely;
  detection continues on deterministic signals.
- The privacy policy states plainly which fields may be transmitted.

Redaction applies to **embeddings too**, not only to classification prompts. An embedding of
raw text containing a customer name is still a transmission of that name.

---

## 8. Module layout

```
backend/app/providers/ai/
├── base.py              # AIProvider protocol, StructuredResult, ProviderUsage, AIStatus
├── pricing.py           # model → price table, with as_of dates
├── redaction.py         # §7
├── retry.py             # backoff + circuit breaker
├── usage.py             # ai_analyses / ai_usage_daily recording + budget guard
├── null.py              # NullAIProvider
├── fake.py              # FakeAIProvider (tests)
└── openai/
    ├── client.py        # the ONLY module permitted to import `openai`
    └── mapping.py       # SDK types → our types, SDK errors → AIStatus
```
