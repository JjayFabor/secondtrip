# CLAUDE.md — SecondTrip

Instructions for coding agents working in this repository.

**Before any feature or fix:** read this file and [`PLAN.md`](PLAN.md). For anything touching a
subsystem, read its specification in [`docs/architecture/`](docs/architecture/) first — the
spec is the source of truth, and where code and spec disagree, one of them is a bug that must
be resolved explicitly, not worked around.

---

## What this product is

A multi-tenant SaaS that finds callbacks and rework in a service business's job history,
explains why each was flagged, and captures manager judgements as confirmed truth.

First vertical is HVAC. **Nothing HVAC-specific may appear in code, schema, or enums.** Vertical
specificity lives in seed data and org configuration.

---

## Non-negotiable rules

Violating any of these is a defect, regardless of whether tests pass.

### Tenancy

1. Every tenant table has `organization_id uuid NOT NULL` and RLS **enabled and forced**.
2. Never `session.get(Model, id)` or `select(Model).where(Model.id == id)` on tenant data.
   Always through a `TenantRepository`, always org-filtered.
3. A missing row and a wrong-tenant row both return **404**. Never 403 — that confirms
   existence.
4. Never put the active organization in the session. It comes from the URL path and is
   re-validated per request.
5. Background job handlers rebuild `TenantContext` **from the job row**, never from ambient
   state or a contextvar.
6. Object storage keys contain only server-generated UUIDs. Never a user-supplied filename.
7. Any cache key (if caching is ever added) must be prefixed `org:{organization_id}:`.

### The four data layers

8. The detection pipeline may freely rebuild layer 3 (candidates, signals, scores, embeddings,
   AI analyses). It may **never** write to layer 4 (`rework_reviews` and its categories/root
   causes).
9. `rework_candidates` are **upserted** on `(organization_id, prior_job_id, followup_job_id)`.
   Never `DELETE` + `INSERT` — that cascades away every human review.
10. AI output never becomes a review. `rework_reviews.reviewed_by_user_id` is `NOT NULL`.
11. Reviews are append-only. A changed classification inserts a new row and sets
    `superseded_by_review_id` on the old one.

### Data handling

12. Money is `Decimal` end to end, `numeric(14,2)` in Postgres, serialized as a **string** in
    JSON. `float` in a money path is a defect.
13. All timestamps `timestamptz` in UTC. Day-based business logic uses the org-local
    `service_date`, never a UTC delta.
14. Never invent data during import. No customer, no date, no equipment → a **row error**, not
    a guess. A fabricated equipment row destroys the `same_equipment` signal for everyone.
15. Every export cell passes through `shared/csv_safety.py`. No exceptions.
16. Unique constraints on soft-deleted tables are partial: `WHERE deleted_at IS NULL`.

### Providers

17. Vendor SDKs are confined: `openai` only under `providers/ai/openai/`, `boto3`/`aioboto3`
    only under `providers/storage/r2/`, `resend` only under `providers/email/`. Enforced by
    `import-linter`.
18. No vendor type crosses a provider protocol boundary.
19. Every provider call path has a defined behaviour when the provider is down. The product
    must remain fully functional with `AI_ENABLED=false`.
20. Authorization asks `EntitlementService`. Never `if org.plan == ...`, never a billing
    provider call.

### Structure

21. `os.environ` is read only in `app/core/settings.py`.
22. A module may import another module's `service.py` and `schemas.py` — never its
    `repository.py` or `models.py`. The one exception is `jobs/read_models.py`.
23. Routers contain no business logic: validate, call a service, serialize.
24. Never hold a database transaction open across a provider call. Commit, call, record.
25. Enqueue background jobs **in the same transaction** as the state change that justifies
    them.
26. Never hard-code the domain. Use `APP_URL` / `FRONTEND_URL` / `COOKIE_DOMAIN`.

### Security

27. Raw SQL uses named bind parameters only. No f-strings, no `%` formatting, no interpolated
    identifiers.
28. Dynamic sort/filter columns come from a whitelist map. An unknown key is a 422.
29. `dangerouslySetInnerHTML` is banned.
30. Never log job notes, descriptions, customer names, addresses, phones, tokens, or signed
    URLs. The redaction processor is a safety net, not the policy.
31. Imported text reaching an AI provider is **data, never instruction** — user turn only,
    delimited, closed output schema.

---

### Design

32. One design system for both surfaces. Tokens live in `frontend/src/styles/tokens.css`,
    consumed only through the Tailwind theme. No component reads a raw hex, px radius, or
    shadow value directly. See `docs/architecture/22-design-system.md`.
33. Score band (machine confidence) and review outcome (human decision) use separate,
    non-overlapping color mappings. A high score is never styled as bad; a rejected candidate
    is never styled as an error.
34. `--accent` (apricot) is a background fill only — never text, never a stand-alone focus
    ring or border. Focus rings use `--focus-ring` (teal).
35. No shadow on an ordinary content card. Shadow only for dropdowns, popovers, and dialogs.
36. No new shared frontend package. Marketing and dashboard consume the same
    `components/ui/`, `components/brand/`, `components/charts/` — one Next.js app, not a
    `packages/ui`.
37. Before shipping any new screen, check it against the anti-pattern checklist in
    `22-design-system.md §2` (no gradients, no glassmorphism, no decorative shadows, no
    fabricated metrics/logos/testimonials).

---

## Working agreement

- **Design before code.** For any non-trivial change, present the approach with trade-offs
  before implementing.
- **Debugging is systematic.** The moment a bug, test failure, or unexpected behaviour appears,
  invoke the `systematic-debugging` skill before proposing a fix. Confirm the root cause with
  evidence; fix the cause, not the symptom; verify by running the actual failure path.
- **Never claim done on static checks alone.** Run the code. State explicitly what was verified
  live versus only type-checked.
- **Update `PLAN.md`** as work progresses, so a fresh session can resume from it alone.
- **Update the spec in the same PR** when an implementation decision diverges from
  `docs/architecture/`.

---

## Commands

```bash
make dev          # postgres+pgvector, migrate, seed, api + web
make test         # backend pytest + frontend vitest
make lint         # ruff, mypy --strict, import-linter, eslint, tsc
make migrate m="message"
make contracts    # regenerate packages/contracts from OpenAPI
make seed-demo    # HVAC dataset with planted callbacks, maintenance pairs, unrelated pairs
make detect ORG=  # CLI: top candidates with full evidence
```

---

## Tests that must never be weakened

Never skip, `xfail`, or delete these. If one fails, the code is wrong, not the test.

- Cross-tenant access matrix (parameterized over every route)
- Route audit: every `/orgs/{org_id}/*` route declares `require_org_context`
- RLS coverage: every table with `organization_id` has RLS enabled **and forced**
- App role has no `BYPASSRLS`, does not own tenant tables, cannot `UPDATE`/`DELETE`
  `audit_events`
- Re-running detection preserves candidate IDs and human reviews
- Import idempotency, including interrupt-and-resume
- Every export path escapes CSV formula prefixes
- Password reset revokes all sessions
- Revoked membership denied on the next request

---

## Git

- Do **not** add `Co-Authored-By: Claude` or "Generated with Claude Code" footers to commits or
  PRs.
- Branch before committing; do not commit to the default branch.
- Commit or push only when asked.
