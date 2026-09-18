# 12 — Privacy & Data Lifecycle

SecondTrip holds personal data about people who have no relationship with SecondTrip: our
customers' customers, and their technicians. That shapes the whole posture.

---

## 1. Data inventory

| Category | Fields | Subject | Sensitivity |
| --- | --- | --- | --- |
| Account | email, name, password hash, sessions, IP hash | Our user | Medium |
| Customer identity | name, email, phone, account number | Our customer's customer | **High** |
| Location | street address, postcode, coordinates | Our customer's customer | **High** |
| Equipment | serial, make, model, install date | Property data | Low |
| Technician | name, employee code, email, hourly cost | Our customer's employee | **High** — employment-consequential |
| Job records | dates, amounts, descriptions, free-text notes | Mixed | **High** — notes can contain anything |
| Derived | candidates, signals, scores, embeddings, AI analyses | Derived from the above | High (embeddings encode the text) |
| Human decisions | reviews, categories, root causes, reviewer identity | Our user | Medium |
| Operational | audit events, background jobs, logs | Our user | Medium |

Two entries deserve emphasis:

- **Free-text notes are unbounded.** A technician may have written a medical detail, a gate
  code, or an opinion about the occupant. We cannot schema-constrain them, so they are treated
  as high-sensitivity throughout: never logged, never in audit payloads, redacted before AI
  calls.
- **Embeddings are personal data.** A 768-dimensional vector derived from text containing a
  name is not anonymous. It is therefore deleted wherever its source text is deleted, never
  retained as "just derived data."

### Controller / processor position

For customer and technician records, **the organization is the data controller and SecondTrip
is the processor.** We act on their instructions, we do not determine the purpose, and we
delete on their instruction. This has three concrete consequences in the design:

1. Deletion requests from a *data subject* (an end customer) are handled by the organization,
   not by us; we provide the tooling to execute them.
2. Cross-organization pooling of personal data is forbidden — including for model improvement
   ([08 §6](08-ai-and-embeddings.md)).
3. A Data Processing Agreement and a subprocessor list (Neon, Render, Vercel, Cloudflare,
   OpenAI, Resend) are launch requirements, not paperwork for later. Any privacy-conscious
   B2B buyer will ask for both.

---

## 2. Organization deletion

Requested by an `owner`. Two-phase, with a grace period.

```
POST /orgs/{id}/deletion-request
  → status = 'pending_deletion', purge_after = now() + 30 days
  → all members lose access IMMEDIATELY (membership check fails on pending_deletion)
  → confirmation email to every owner, with a cancellation link
  → audit event

  [30 days] — cancellable by an owner at any point

[job] org.purge
  → DELETE FROM organizations WHERE id = :id       (cascades everything tenant-owned)
  → storage.delete_prefix(f"orgs/{org_id}/")
  → delete billing customer at the provider (when billing exists)
  → retain ONLY: a deletion record {org_id, deleted_at, requested_by_hash} for 12 months
  → audit event written to the retained record, not to the deleted org
```

The 30-day grace period exists because deletion here is irreversible and catastrophic to the
customer: there is no backup restore that recovers one tenant out of a shared database without
restoring everything. Immediate access revocation gives the *effect* of deletion right away,
which is what a customer actually wants when they press the button.

**Cascade coverage is a tested invariant.** A test creates an org with at least one row in
every tenant table, deletes it, and asserts zero rows remain anywhere. A table added later
without `ON DELETE CASCADE` fails that test — which is the only reliable defence against a
migration that quietly leaves orphans.

---

## 3. User deletion

A user is not tenant data, and they may have authored `rework_reviews` — layer-4 truth with
`ON DELETE RESTRICT`. Hard-deleting them would either destroy those decisions or violate the
constraint.

**Anonymise, do not delete:**

```
users.email        → "deleted-{uuid7}@deleted.invalid"
users.full_name    → "Deleted user"
users.status       → 'deactivated'
users.deleted_at   → now()
DELETE user_credentials, user_sessions, all tokens
memberships        → revoked_at = now()
audit_events       → actor_user_id retained; actor_label already denormalized
rework_reviews     → reviewed_by_user_id retained, now pointing at the anonymised row
```

The result: "confirmed by Deleted user on 12 March" — the decision and its accountability
chain survive, the person does not. If a user is an org's sole owner, deletion is blocked until
ownership is transferred.

Documented in the privacy policy, because "we anonymise rather than erase your identifier from
historical business records" is a position that must be disclosed, not assumed.

---

## 4. Retention

| Data | Default | Configurable | Rationale |
| --- | --- | --- | --- |
| Job records | 24 months | Per org, 6–84 months | Detection needs history; the customer decides how much |
| Import source files (R2) | 24 months | Follows job retention | Layer-1 evidence |
| `import_rows.raw_data` | **90 days** | No | Largest table; error/warning rows keep `raw_data` indefinitely |
| `import_rows` (error/warning) | Until batch deleted | No | The user's diagnostic record |
| Candidates, signals, scores | Follows jobs | No | Derived |
| `candidate_signals` prior runs | Current + 2 previous runs | No | Bounded explainability history |
| Embeddings | Follows jobs | No | Derived personal data |
| AI analyses | 12 months | No | Debugging and agreement metrics |
| Reviews | Follows jobs | No | The product's core asset |
| Audit events | 24 months | Longer on higher plans | Compliance |
| Sessions | 30 days past expiry | No | |
| Tokens | 30 days past expiry | No | |
| Background jobs | 30 days (completed), 90 days (failed) | No | |
| Application logs | 30 days | No | Platform default |
| Deleted-org tombstone | 12 months | No | Dispute resolution |

Enforced by nightly `system.*` prune jobs, each idempotent and each logging what it removed.
Retention is evaluated per organization against `organizations.retention_months`.

**Retention shortening is applied on the next nightly run, not retroactively at the moment of
the setting change** — and the UI says so, with a count of what will be deleted. A setting
change that silently destroys two years of data in the background is an incident, not a
feature.

---

## 5. Import deletion

Deleting an import is more dangerous than it looks, because a job can be created by one batch
and updated by another. The rules are in [04 §13](04-data-model.md). The privacy-relevant part:

- The user is shown, **before confirming**, exactly how many jobs will be deleted, how many
  will be retained, and **how many human reviews will be destroyed**.
- The R2 source object and error report are deleted via `storage.cleanup`.
- The audit event records the counts.

Destroying layer-4 data is always an explicit, informed, audited action — never a side effect.

---

## 6. Export & portability

| Export | Format | Scope |
| --- | --- | --- |
| Jobs | CSV | Filtered set or all |
| Rework candidates + evidence | CSV | Includes signal breakdown and score |
| Reviews | CSV | Decisions, categories, root causes, reviewer, timestamps |
| Analytics summary | CSV | Aggregates |
| **Full organization export** | ZIP of CSVs + `manifest.json` | Everything the org owns |

The full export is the portability answer and the anti-lock-in argument. Generated
asynchronously (`export.generate`), stored under `orgs/{org_id}/exports/{export_id}/`,
delivered by signed URL with a 30-day lifecycle expiry. Every cell passes through `csv_safe`
([11 §5](11-security-threat-model.md)).

---

## 7. Minimisation and technician data

**To AI providers:** redaction per [08 §7](08-ai-and-embeddings.md) — names, addresses,
phones, emails and serials are replaced before any call, including embedding calls.
Technicians become stable per-org pseudonyms so "same technician" stays computable without
transmitting a name.

**In logs:** never. **In audit payloads:** never (allowlist in [13 §4](13-audit.md)).
**In error messages:** IDs only.

**Technician-level analytics** deserve an explicit position, because the data model fully
supports "rank technicians by callback rate" and that output can affect someone's job:

- Technician attribution is shown only to `manager` and above.
- Comparative views require a **minimum job volume per technician** (default 25 in the period)
  before a rate is displayed. Below it, the UI shows the count and withholds the rate. A 50%
  callback rate on two jobs is noise, and presenting it as a performance metric is
  indefensible.
- Every technician view carries the confirmed/unconfirmed distinction prominently: unreviewed
  candidates are *suspicions*, not attributed callbacks.

This is a product-design commitment recorded in the architecture because it constrains what
the analytics endpoints may return, not merely what the UI chooses to show.

---

## 8. Subject rights support

| Right | Mechanism |
| --- | --- |
| Access (our user) | `GET /me/export` — account data, memberships, review history |
| Access (end customer) | The organization exports that customer's jobs; we provide the filter |
| Rectification | Correct at source and re-import, or edit the customer/equipment record directly |
| Erasure (our user) | §3 anonymisation |
| Erasure (end customer) | Organization deletes the customer → cascades jobs, candidates, embeddings, AI analyses. A `POST /customers/{id}/erase` action exists specifically for this, with a preview of affected records |
| Portability | §6 full export |
| Objection to AI processing | Org-level `ai_enabled = false`; deterministic detection continues |

`POST /customers/{id}/erase` is a deliberate addition: without it, an organization receiving an
erasure request from one of their customers would have to delete an entire import. That would
make us a poor processor.

---

## 9. Breach response

1. **Contain** — revoke sessions, rotate affected secrets, disable the vector.
2. **Assess** — which organizations, which data categories, what volume. The audit log and
   structured logs are the evidence base.
3. **Notify** — affected organization owners without undue delay (target < 72 h), with what
   was accessed and what they must do. They notify their own customers as controllers.
4. **Remediate and record** — a written post-mortem including the control that failed and the
   control added.

Prerequisites, all of which are architectural rather than procedural, and all of which already
exist in this design: request IDs correlating logs across the stack ([18](18-observability.md)),
an append-only audit trail ([13](13-audit.md)), per-org data scoping that makes "which tenants
were affected" answerable, and IP hashes that support investigation without retaining raw
addresses.
