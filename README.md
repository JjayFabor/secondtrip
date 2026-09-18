# SecondTrip

Multi-tenant SaaS that finds the **second trips** hiding in a service business's job history —
callbacks, rework, warranty visits, incomplete repairs, misdiagnoses, and recurring problems —
explains why each was flagged, and turns manager judgements into confirmed truth and
business-impact analytics.

Not a field-service management system. An intelligence layer on top of the one you already
have.

**Status:** Phase 0 complete — architecture and technical specification. No implementation yet.

---

## The idea

A shop owner knows some of their jobs are repeat visits. They do not know how many, which
technicians, which equipment, which root causes, or what it costs them. The answer is in their
job history, but it is unreadable at scale because nobody labels a job "this was a callback."

SecondTrip reads the history and makes it legible:

```
Potential callback · Score 92 / 100 · High confidence

  ✓ Same equipment            Carrier 24ACC6, serial ...4821          +30
  ✓ 8 days apart              12 Mar → 20 Mar                         +20
  ✓ Description similarity    0.89 — "no cooling upstairs"            +20
  ✓ Follow-up invoiced $0     Invoice #4471                           +25
  ✓ Same customer             Mercer Property Group                   +20
  ✓ Same technician           D. Okafor                                +5
  ✗ Warranty flag             Not marked as warranty                    —
  — Repeat part code          No parts recorded on the first visit    n/a
                                                       Raw 120 / 130 → 92
```

A manager then confirms, rejects, or reclassifies it. **That judgement — not the score — is
what the product accumulates.**

---

## How it works

```
CSV upload → validate → normalize → import
           → candidate generation (blocked, not N²)
           → deterministic signals
           → semantic similarity (pgvector)
           → explainable composite score
           → [optional AI classification]
           → human review
           → root-cause & cost analytics
```

The detection engine works with the AI provider switched off. AI enhances detection; it does
not own the workflow.

---

## Stack

Next.js · TypeScript · FastAPI · Pydantic v2 · SQLAlchemy async · Alembic · PostgreSQL
(Neon) + pgvector · Cloudflare R2 · Resend · Vercel + Render

Modular monolith. Postgres is also the job queue and the vector store. Roughly $7/month at
launch.

---

## Documentation

| | |
| --- | --- |
| [`PLAN.md`](PLAN.md) | Durable task state, decisions, current status |
| [`CLAUDE.md`](CLAUDE.md) | Binding rules for coding agents |
| [`docs/architecture/`](docs/architecture/) | Full technical specification (23 documents) |

Start with
[`docs/architecture/00-overview-and-decisions.md`](docs/architecture/00-overview-and-decisions.md)
— it carries the architectural decision record and an index of everything else.

### The idea that shapes the whole design

Four kinds of data, never conflated:

| Layer | Example | Rebuildable? |
| --- | --- | --- |
| Source / raw | the uploaded CSV | No — it is evidence |
| Normalized operational | jobs, customers, equipment | Yes, from raw |
| Derived analytical | candidates, signals, scores, embeddings | **Yes — safe to wipe and recompute** |
| Human-confirmed truth | reviews, categories, root causes | **No — never machine-written** |

The detection pipeline may freely rebuild layer 3. It may never touch layer 4.
