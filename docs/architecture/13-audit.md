# 13 — Auditability

The audit log answers three questions: *who changed this*, *when*, and *what did it look like
before*. It is not a debug log and it is not analytics.

---

## 1. Event model

```python
@dataclass(frozen=True, slots=True)
class AuditEvent:
    organization_id: UUID
    action: str                       # "candidate.confirmed" — dotted, past tense
    actor_type: ActorType             # user | system | api_key
    actor_user_id: UUID | None
    actor_label: str                  # denormalized: survives user anonymisation
    resource_type: str | None         # "rework_candidate"
    resource_id: UUID | None
    summary: str                      # human sentence, rendered at write time
    changes: dict[str, FieldChange] | None   # allowlisted before/after
    request_id: str | None
    ip_hash: bytes | None
    occurred_at: datetime
```

Three choices worth explaining:

- **`actor_label` is denormalized.** When a user is anonymised ([12 §3](12-privacy-and-data-lifecycle.md)),
  `actor_user_id` still resolves but the name is gone. The label preserves "Dana Okafor
  (dana@…)" as it was at the time, which is what an audit trail is for.
- **`summary` is rendered at write time**, not at read time. A summary generated from current
  data would say "Confirmed callback for *Acme Ltd*" even after the customer was renamed or
  deleted. The audit record must describe the world as it was.
- **`action` is past tense and dotted.** `candidate.confirmed`, not `confirm_candidate`. An
  audit log records what happened, and the naming should not read like an API call.

---

## 2. Storage

`audit_events`, columns in [04 §11](04-data-model.md). Key properties:

- **Append-only, enforced by Postgres:** the application role is granted `SELECT, INSERT` only.
  `UPDATE` and `DELETE` are revoked. A convention is a hope; a revoked grant is a guarantee.
- Retention: 24 months (longer on higher plans), pruned by a nightly job that runs as the
  owner role — the single exception to append-only, and it deletes only by age.
- Indexes: `(organization_id, occurred_at DESC)`,
  `(organization_id, resource_type, resource_id)`,
  `(organization_id, action, occurred_at DESC)`.
- RLS applies as with every tenant table.

### Write path

Audit writes participate in the **same transaction** as the change they describe. If the change
rolls back, so does its audit record — no phantom events. If the audit insert fails, the whole
operation fails, which is the correct priority for an auditable action.

```python
async with uow:
    review = await reviews.create(...)
    await audit.record(
        action="candidate.confirmed",
        resource_type="rework_candidate",
        resource_id=candidate.id,
        summary=f"Confirmed as {category.label}",
        changes={"decision": FieldChange(before=None, after="confirmed")},
    )
```

This rules out a queue-based or fire-and-forget audit pipeline. At our volume the synchronous
insert is negligible, and the consistency guarantee is worth far more than the microseconds.

---

## 3. Audited actions

| Action | Resource | Changes captured |
| --- | --- | --- |
| `organization.created` | organization | name, slug |
| `organization.settings_updated` | organization | name, timezone, currency, retention_months |
| `organization.deletion_requested` / `deletion_cancelled` / `purged` | organization | `purge_after` |
| `member.invited` | invitation | email (hashed), role |
| `member.invitation_revoked` / `invitation_accepted` | invitation | role |
| `member.role_changed` | membership | before/after role |
| `member.removed` | membership | role |
| `member.ownership_transferred` | membership | from/to user ids |
| `import.created` | import_batch | filename, size |
| `import.mapping_applied` | import_batch | mapped field count, template id |
| `import.committed` | import_batch | row count |
| `import.completed` | import_batch | created/updated/error/warning counts |
| `import.failed` / `import.cancelled` | import_batch | reason, processed count |
| `import.deleted` | import_batch | **jobs deleted, jobs retained, reviews destroyed** |
| `detection.rules_changed` | rule_set | before/after weights, window, thresholds |
| `detection.run_started` / `run_completed` | detection_run | trigger, scope, counts |
| `candidate.confirmed` | rework_candidate | decision, category, root_cause, score_at_review |
| `candidate.rejected` | rework_candidate | decision, category |
| `candidate.reclassified` | rework_candidate | before/after category, superseded review id |
| `candidate.unsuppressed` | rework_candidate | suppressing signal key |
| `category.created` / `updated` / `deactivated` | rework_category | key, label, outcome |
| `root_cause.created` / `updated` / `deactivated` | root_cause | key, label |
| `cost_model.changed` | cost_model | before/after every rate |
| `export.generated` | export | kind, row count, filters |
| `customer.erased` | customer | jobs affected, reviews destroyed |
| `data.retention_changed` | organization | before/after months, **estimated rows affected** |
| `billing.plan_changed` | subscription | before/after plan |
| `user.password_changed` / `sessions_revoked` | user | session count revoked |
| `ai.settings_changed` | organization | ai_enabled before/after |

Three of these deliberately record **destructive consequences** rather than only the action:
`import.deleted`, `customer.erased`, and `data.retention_changed`. When a customer later asks
"where did our reviews go?", the audit log must answer it.

### Not audited

Reads (too voluminous, low value — except exports, which *are* audited because they remove
data from our control), page views, background job internals (they have their own structured
logs), and failed login attempts (rate-limit counters and security logs cover those without
building an account-enumeration oracle inside the tenant's own audit view).

---

## 4. What may appear in `changes`

A strict **per-resource-type allowlist** in `audit/allowlist.py`. A field absent from the
allowlist is dropped, not recorded — so adding a column to a model never silently starts
leaking its values into the audit log.

```python
AUDITABLE_FIELDS: Final[dict[str, frozenset[str]]] = {
    "organization":     frozenset({"name", "slug", "timezone", "currency_code",
                                   "retention_months", "status", "ai_enabled"}),
    "membership":       frozenset({"role", "revoked_at"}),
    "import_batch":     frozenset({"status", "original_filename", "file_size_bytes",
                                   "total_rows", "created_jobs", "updated_jobs",
                                   "error_rows", "reviews_destroyed"}),
    "detection_rule":   frozenset({"signal_key", "kind", "weight", "params", "is_enabled"}),
    "rework_candidate": frozenset({"decision", "category_key", "root_cause_key",
                                   "score_at_review", "workflow_status"}),
    "cost_model":       frozenset({"technician_hourly_cost", "vehicle_dispatch_cost",
                                   "overhead_per_visit", "opportunity_cost_per_hour",
                                   "default_visit_duration_minutes"}),
    ...
}
```

**Never in an audit payload**, under any circumstances:

| Excluded | Why |
| --- | --- |
| Password hashes, tokens, secrets | Obvious |
| Job notes, descriptions, symptoms, diagnoses | Unbounded free text; high sensitivity ([12 §1](12-privacy-and-data-lifecycle.md)) |
| Customer names, addresses, phones | PII; the resource ID is sufficient to locate the record |
| Technician names | Use IDs; `actor_label` covers the acting user only |
| Full row snapshots | A changed-fields diff is the requirement; a snapshot is a PII copy machine |
| Email addresses | Hashed in `member.invited`; the invitation row holds the address |

`FieldChange` values are truncated to 200 characters and, for `params`-style JSONB, recorded
as a structural diff rather than the full document.

---

## 5. Access

| Who | What |
| --- | --- |
| `owner`, `admin` | Full organization audit log |
| `manager`, `member` | No access |
| Cross-organization | Impossible — RLS plus org-scoped repository |

`GET /orgs/{id}/audit` supports filtering by `action`, `actor_user_id`, `resource_type`,
`resource_id`, and a date range, with cursor pagination. Exportable as CSV (through
`csv_safe`) for customers who need records outside the product.

---

## 6. System actors

Background work is audited with `actor_type = 'system'` and
`actor_label = f"system:{job_type}"`. When a job was enqueued by a person,
`enqueued_by_user_id` carries through, so `import.completed` is attributed to the user who
committed the import — which is what a reader expects — while still being marked as a system
execution.

Automatic events with no human origin (`detection.run_completed` from a scheduled trigger,
`organization.purged`) have `actor_user_id = NULL` and a label naming the responsible job.
