# 19 — Testing Strategy

No tests are written in Phase 0. This document defines what will be tested, and — equally
important — what will not.

**The governing principle:** test the things that are hard to get right and catastrophic to get
wrong. Coverage percentage is not a goal; a suite full of tests asserting that a Pydantic model
has the fields you just declared inflates a number and catches nothing.

---

## 1. Shape of the suite

```
tests/
├── unit/           ~65%   pure functions, no I/O, milliseconds
├── integration/    ~30%   real Postgres, real transactions
├── security/        ~5%   tenant isolation, authorization — small but non-negotiable
└── contract/               OpenAPI ↔ generated types
```

Inverted pyramid warnings do not apply cleanly here: the riskiest logic in this system
(normalization, scoring, cost) is pure, so unit tests genuinely carry the load. Everything
touching tenancy runs against a real database, because the isolation guarantees are partly
enforced *by* the database.

**No mocked database.** Tests run against a real Postgres with pgvector, RLS policies applied,
and the same non-owner app role as production. A mocked repository cannot prove RLS works, and
RLS is one of the three isolation layers.

**No mocked providers at the integration level** — use `FakeAIProvider`, `InMemoryStorage`,
`MemoryEmailProvider`. These are real implementations of the protocol, so they exercise the
same call sites rather than a `MagicMock` that accepts anything.

---

## 2. Tenant isolation & authorization — **highest priority**

The tests that justify the whole architecture. A failure here is a data breach.

### Cross-tenant matrix

A parameterized suite over **every tenant-scoped endpoint**:

```python
@pytest.mark.parametrize("method,path_template", ALL_TENANT_ROUTES)
async def test_cannot_access_other_org_resource(method, path_template, org_a, org_b, client):
    resource = await seed_resource_in(org_b)
    resp = await client.request(method, path_template.format(org_id=org_a.id, id=resource.id),
                                cookies=session_for(user_in(org_a)))
    assert resp.status_code == 404          # never 403 — that would confirm existence
```

`ALL_TENANT_ROUTES` is derived from `app.routes`, so **a new endpoint is automatically
covered**. This is the single most valuable test in the suite: it does not rely on anyone
remembering to add a case.

### Companion tests

| Test | Asserts |
| --- | --- |
| Route audit | Every `/orgs/{org_id}/*` route declares `require_org_context`; fails on omission |
| RLS coverage | Enumerate `information_schema.tables`; every table with an `organization_id` column has RLS **enabled and forced** and at least one policy |
| RLS actually blocks | With `app.current_org_id` set to org A, a raw `SELECT * FROM jobs` returns zero of org B's rows |
| App role privileges | The app role has no `BYPASSRLS`, does not own tenant tables, and has no `UPDATE`/`DELETE` on `audit_events` |
| Repository scoping | A `TenantRepository` cannot be constructed without a `TenantContext` (type-level + runtime) |
| Raw SQL audit | Every `text()` literal in the codebase containing `FROM jobs`/`FROM rework_candidates` etc. also contains `organization_id` |
| Permission matrix | For each role × each permission-gated endpoint, assert allow/deny against [02 §3](02-multi-tenancy.md) |
| Membership revocation | A revoked member is denied on the **very next request**, not at session expiry |
| Storage keys | Generated object keys never contain user-supplied strings (property test over hostile filenames) |
| Worker tenancy | A job handler given org A's row cannot read org B's data |

---

## 3. CSV normalization & ingestion

Pure functions — cheap to test exhaustively, and wrong answers here silently corrupt every
downstream result.

### Date parsing

| Case | Expected |
| --- | --- |
| `2026-03-12`, `03/12/2026`, `12/03/2026`, `12-Mar-2026`, `March 12, 2026` | Parsed per the mapping/format |
| Ambiguous `03/04/2026` with a batch containing `25/12/2025` | `DD/MM` inferred for the whole file |
| Ambiguous with no disambiguating value | `AMBIGUOUS_DATE_FORMAT` error, **not a guess** |
| Naive datetime, org timezone `America/Chicago` | Correct UTC + correct local `service_date` |
| `23:30` on 1 Mar in `America/Chicago` | `service_date = 2026-03-01`, not 2 Mar |
| Excel serial `45678` | Parsed or explicitly rejected — decided and tested, not accidental |
| `1899-12-30`, `0000-00-00`, `2099-01-01` | `DATE_OUT_OF_RANGE` |

The timezone cases are the ones that silently break detection: a job that lands on the wrong
calendar day shifts `days_between` and can move a candidate across a band boundary.

### Money parsing

`"$1,234.56"` · `"1.234,56"` · `"(500.00)"` → −500 · `"1234"` · `""` → **NULL, not 0** ·
`"N/A"` → NULL · `"1,23,456.78"` (Indian grouping) · `"12.345"` (ambiguous: 12345 or 12.345?)
· values exceeding `numeric(14,2)`.

A property test asserts no parse path ever produces a `float`.

### Entity resolution

Same customer via external ID, via phone, via name+postcode; **different** customers with the
same name and different postcodes; equipment resolved by serial across two differently-named
customers; equipment **not** invented when no identifier exists (asserts `equipment_id IS
NULL`); enrichment semantics (a later blank does not erase an earlier value).

### Idempotency

| Test | Asserts |
| --- | --- |
| Import the same file twice | Second run creates 0 jobs, updates N; no duplicate customers/locations/equipment |
| Import overlapping files | Union of jobs, no duplicates |
| Same file, different mapping | Jobs updated, not duplicated |
| Interrupt at row 3,000 of 10,000 and resume | Exactly 10,000 jobs, no duplicates, no gaps |
| Byte-identical re-upload | Blocked by `file_sha256` |

The interrupt-and-resume test is the one that finds real bugs — it exercises checkpointing,
upserts, and transaction boundaries together.

### Adversarial CSV corpus

Committed fixtures in `tests/fixtures/csv/adversarial/`, each asserting a **clean error rather
than a crash or a hang**: 100 MB single field · 1M columns · null bytes · invalid UTF-8 ·
UTF-16LE with BOM · mixed line endings · unterminated quotes · formula-injection payloads in
every text column · a 50 MB file of one repeated row · an `.xlsx` renamed to `.csv` · an empty
file · a header-only file · duplicate header names · BIDI override characters.

---

## 4. Detection engine

### Scoring (pure — test exhaustively)

| Test | Asserts |
| --- | --- |
| Known signal set → known score | Golden cases from [07 §5](07-detection-engine.md) |
| `NOT_EVALUABLE` excluded from **numerator and denominator** | An org with no equipment data still reaches 100 |
| Veto suppresses regardless of score | `is_suppressed`, reason recorded, raw score still stored |
| Gate hides but still scores | Stored, `surfaced=false` |
| Multiplier order independence | Result identical regardless of signal evaluation order |
| Score clamped to 0–100 | Weights summing above the max cannot exceed 100 |
| All weights zero | No division by zero; score 0 |
| `Decimal` throughout | No float anywhere in the path (property test) |
| Band boundaries | 74.99 → medium, 75.00 → high |

### Candidate generation (integration)

| Test | Asserts |
| --- | --- |
| Canonical ordering | Only one of (A,B)/(B,A) exists, ever |
| Same-day jobs | Total order via `(service_date, order_ts, id)`; no reciprocal pair |
| NULL `started_at` | Pair still generated (the `COALESCE` case) |
| Window boundary | Exactly `window_days` apart is included; +1 day is not |
| Fan-out guard | 100 jobs in a window produce ≤ `max_followups_per_job` per anchor |
| Cancelled jobs | Never anchor or complete a pair |
| Cross-tenant | Two orgs with identical customer names never pair across |
| Equipment-only block | A pair is found when the customer differs but equipment matches |
| **Re-run preserves reviews** | Confirm a candidate, re-run detection, review still present and attached |
| **Re-run with new rules** | Score changes, `candidate.id` unchanged, review intact |
| Narrowed window | Previously-valid candidate is suppressed, **not deleted** |

The two "re-run preserves reviews" tests protect the single most valuable data in the product.
They should be among the first tests written.

### Semantic similarity

Deterministic `FakeAIProvider` embeddings (hash-derived) so cosine values are reproducible.
Assert: signal contributes above threshold; `NOT_EVALUABLE` when either embedding is missing;
`similarity_state` transitions correctly; provider failure leaves `unavailable` and does not
depress the score; vectors from different `model_key`s are never compared.

### AI structured output

Valid response parses · missing field rejected · extra field rejected (`extra="forbid"`) ·
out-of-range confidence rejected · invented classification value rejected · malformed JSON
retried once then recorded as `invalid_output` · **a prompt-injection payload in a job note
cannot alter workflow state, score, or review** · dedup on `input_hash` prevents a second
provider call.

---

## 5. Cost calculation

Pure, and it produces the number customers make decisions with.

| Test | Asserts |
| --- | --- |
| Known inputs → known total | Golden cases |
| Technician override beats model default | |
| Missing duration → model default | |
| `include_parts_cost=false` | Parts excluded |
| Custom factors, per-visit and per-hour | Both applied correctly |
| Rounding | One `ROUND_HALF_UP` at the end, not per component |
| Snapshot immutability | Change the cost model; historical snapshots unchanged; current view recomputes |
| Currency consistency | Mixed currencies raise rather than silently summing |

---

## 6. Background jobs

| Test | Asserts |
| --- | --- |
| Concurrent claim | Two workers claim disjoint sets (`SKIP LOCKED`) |
| Every handler is idempotent | Run twice, assert identical final state — parameterized over the registry |
| Retry backoff | `run_at` matches the formula within jitter bounds |
| Attempts exhausted | `failed`, owning object in a failure state, audit event emitted |
| Permanent errors | Fail immediately without consuming attempts |
| Stale recovery | Simulate a dead worker; the job returns to `queued` |
| Cancellation | Stops at the next checkpoint; completed work retained |
| Enqueue idempotency | Duplicate `idempotency_key` inserts once |
| Transactional enqueue | Rolled-back transaction leaves no job row |
| Tenant context | Rebuilt from the job row, never ambient |
| Payload validation | An old payload shape fails cleanly, not with a `KeyError` |

The parameterized "every handler is idempotent" test is worth the effort to build: it
automatically covers handlers added later.

---

## 7. Other areas

### Entitlements

Each key enforced at its checkpoint · override beats plan · expired override ignored · counters
increment in the work transaction and **not** on rollback · period boundaries in the org
timezone · `past_due` grace period · downgrade retains data but blocks import · denial message
includes limit and current.

### Authentication

Password reset revokes **all** sessions · invitation grants the role from the *row*, not the
request · invitation bound to the invited email · expired/consumed tokens rejected · session
revocation effective next request · login rate limit and lockout · registration with an
existing email does not disclose existence · timing does not disclose account existence
(statistical, generous tolerance to avoid flakiness) · last owner cannot be removed or demoted.

### Audit

Written in the same transaction (rollback → no event) · `changes` contains only allowlisted
fields · a payload containing job notes/customer names is rejected or stripped · `actor_label`
survives user anonymisation · app role cannot `UPDATE`/`DELETE` audit rows · destructive
actions record their consequence counts.

### Export safety

Every export endpoint escapes all six dangerous prefixes · `Content-Disposition: attachment` ·
signed URL TTL respected · export contains only the requesting org's rows.

### Architecture conformance (fast, run on every commit)

`import-linter` contracts pass · `openai` imported only under `providers/ai/openai/` ·
`boto3` only under `providers/storage/r2/` · no `os.environ` outside `core/settings.py` · no
`dangerouslySetInnerHTML` (ESLint) · no `float` in money paths (mypy + a grep test) ·
signal registry matches `detection_signal_definitions`.

### Contract

CI regenerates `packages/contracts` and fails on any diff ([15 §4](15-api-design.md)).

---

## 8. What will NOT be tested

Stated explicitly so nobody adds these later believing they were an oversight:

| Not tested | Why |
| --- | --- |
| Pydantic field declarations | Testing that a library works |
| Simple CRUD getters/setters | No logic |
| ORM relationship traversal | SQLAlchemy's job |
| React component rendering snapshots | Brittle, churns on every style change, catches nothing |
| Third-party SDK behaviour | Their tests; we test our **adapter's** mapping |
| Every permutation of every filter | One representative per filter type |
| Exact AI model output quality | Non-deterministic. We test **schema validation and failure handling**, not whether the model is right |
| Getter endpoints with no authorization nuance | Covered by the parameterized tenant matrix |
| Migration up/down round-trips for every revision | One "migrate from scratch, then from the previous release" check in CI is sufficient |

---

## 9. Test data

- **Factories** (`factory_boy` or plain builders) over fixtures — an explicit
  `JobFactory(service_date=..., equipment=...)` reads far better than a shared fixture whose
  relevant field is buried.
- **Golden datasets** for detection: a curated HVAC-shaped set with *known* callbacks, known
  maintenance pairs that must be vetoed, and known unrelated pairs. Scoring changes are
  evaluated against it, so a "tuning improvement" that quietly breaks something is visible.
- Each test creates its own organization; tests never share tenant state.
- Transaction-per-test with rollback, except where the test is specifically about commit
  behaviour.
- `freezegun` for time-dependent logic (windows, expiry, retention).

---

## 10. CI gates

| Gate | Blocking |
| --- | --- |
| ruff + format | ✅ |
| mypy --strict | ✅ |
| import-linter | ✅ |
| Unit tests | ✅ |
| Integration tests | ✅ |
| **Security tests** | ✅ — never skippable, never `xfail` |
| Contract drift | ✅ |
| gitleaks | ✅ |
| pip-audit / pnpm audit | ⚠️ warn (fail on critical) |
| Frontend lint/tsc/build | ✅ |

No coverage threshold gate. A percentage target drives tests written to satisfy the number
rather than the risk, and the risks in this system are concentrated in a handful of places that
the sections above name explicitly.
