# 02 — Multi-Tenancy, Tenant Isolation & RBAC

---

## 1. The tenant boundary

**The tenant is the `organization`.** Every business record in the system belongs to exactly
one organization, via a non-nullable `organization_id` column. There is no "global" business
data and no record shared across organizations.

Records that are deliberately **not** tenant-owned:

| Table | Why |
| --- | --- |
| `users` | A person is a person. They may belong to several organizations. |
| `user_credentials`, `user_sessions` | Belong to the user, not to an org. |
| `plans`, `plan_entitlements` | Product catalogue, identical for everyone. |
| `detection_signal_definitions` | Catalogue of signal types the code implements. |
| `system_root_causes`, `system_rework_categories` | Seed/global defaults an org may adopt or override. |

Everything else — customers, locations, equipment, technicians, jobs, imports, candidates,
reviews, categories, rules, cost models, audit events, and background jobs — carries
`organization_id NOT NULL`.

### The membership join is the only bridge

```
users ──< organization_memberships >── organizations
```

A user's access to organization X exists **only** if a non-revoked `organization_memberships`
row links them. This is checked on every request that touches tenant data. There is no
inheritance, no "parent org," no admin-sees-all path in application code. (Internal support
tooling, if ever built, gets a separate audited mechanism — not a magic role.)

---

## 2. Three layers of enforcement

Isolation is enforced independently at three levels, because the realistic failure mode is
not "we forgot to implement isolation," it is "one query out of four hundred forgot its
filter."

### Layer 1 — Postgres Row-Level Security (the backstop)

Every tenant-owned table gets:

```sql
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY jobs_tenant_isolation ON jobs
  USING      (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
```

Four details that make or break this:

1. **`FORCE ROW LEVEL SECURITY` is mandatory.** Without it, the table's *owner* bypasses its
   own policies. Since Alembic creates tables as the owner, forgetting `FORCE` means the app
   silently has no RLS if it ever connects as that role.
2. **The application connects as a dedicated non-owner role.** Migrations run as the owner
   (`DATABASE_URL_MIGRATIONS`, direct endpoint); the app runs as `secondtrip_app`
   (`DATABASE_URL`, pooled endpoint) with `SELECT/INSERT/UPDATE/DELETE` grants and no
   `BYPASSRLS` attribute. Two roles, two URLs — this is a deployment requirement, documented
   in [17-configuration.md](17-configuration.md).
3. **The third argument to `current_setting` must be `true`** (`missing_ok`). Otherwise a
   query issued before the GUC is set raises instead of returning zero rows — and a
   hard error in a health check is a worse failure mode than an empty result.
4. **`NULLIF(..., '')` is required, not decorative.** `missing_ok` only covers a GUC that was
   *never* touched in the session — `current_setting` then returns true SQL `NULL`, and
   `NULL::uuid` is a no-op cast. But `set_config('app.current_org_id', NULL, true)` — the SQL
   way to clear a GUC — does not produce NULL, it produces an **empty string**, and
   `''::uuid` raises `invalid input syntax for type uuid` rather than comparing false.
   Verified against a live Postgres session, not assumed. Without `NULLIF`, "never set" fails
   safe (zero rows) while "explicitly cleared" throws a 500 — two code paths that are supposed
   to have the identical safe behavior, diverging. `NULLIF` collapses both to true NULL before
   the cast, so the "missing context never errors" guarantee actually holds in both cases.

**Setting the context.** At the start of every transaction that touches tenant data:

```sql
SET LOCAL app.current_org_id = '<uuid>';
```

`SET LOCAL` is transaction-scoped, which is exactly right for PgBouncer transaction pooling:
the setting cannot leak to the next tenant that borrows the connection. Plain `SET` would be
a cross-tenant leak waiting to happen. **Never use plain `SET` for tenant context.**

Implemented as a SQLAlchemy async session factory that takes a `TenantContext` and emits the
`SET LOCAL` as the first statement after `begin()`.

**What RLS does not cover:** aggregate queries run by the analytics module still need correct
`GROUP BY` scoping to be *meaningful*, and RLS cannot protect you from a bug that writes org
A's data *into* org B's context. `WITH CHECK` covers the write case; correctness of the
context itself is layer 2's job.

### Layer 2 — Repository-level scoping (the primary mechanism)

Tenant-scoped repositories cannot be constructed without a `TenantContext`:

```python
@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: UUID
    actor_user_id: UUID | None      # None for system/worker-initiated work
    role: OrganizationRole | None
    request_id: str | None


class TenantRepository:
    """Base class. Every query it issues is org-filtered by construction."""

    def __init__(self, session: AsyncSession, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    def _scoped(self, stmt: Select) -> Select:
        return stmt.where(self.model.organization_id == self._tenant.organization_id)
```

Rules for implementers:

- Domain services receive repositories, never a bare `AsyncSession`.
- `get_by_id` on a tenant repository is **always** `WHERE id = :id AND organization_id = :org`.
  Never `session.get(Job, id)`. This single rule eliminates the entire IDOR class.
- A missing row and a wrong-tenant row both produce `404 Not Found`. Returning `403` for the
  latter confirms the record exists to an attacker probing IDs — an information leak.
- Raw SQL (candidate generation, analytics) is permitted but must be reviewed for an explicit
  `organization_id` predicate, and is covered by a dedicated test
  ([19-testing-strategy.md §2](19-testing-strategy.md)).

### Layer 3 — API dependency chain

```python
async def require_org_context(
    org_id: UUID = Path(...),
    user: AuthenticatedUser = Depends(require_session),
    ...
) -> TenantContext:
    membership = await memberships.active_for(user.id, org_id)
    if membership is None:
        raise NotFound()          # not Forbidden — do not confirm the org exists
    return TenantContext(organization_id=org_id, actor_user_id=user.id, role=membership.role)
```

Because the organization is in the **URL path** (`/api/v1/orgs/{org_id}/jobs`), it is
impossible to write a tenant endpoint that forgets to declare its scope — the route will not
compile without the parameter, and the dependency that consumes it performs the membership
check. A header-based tenant (`X-Organization-Id`) makes the scope optional-looking and
easier to forget, which is why it is rejected.

---

## 3. RBAC model

### Roles

| Role | Intended user | Rank |
| --- | --- | --- |
| `owner` | Business owner; billing responsibility | 40 |
| `admin` | Operations manager who configures the system | 30 |
| `manager` | Service manager who reviews and classifies rework | 20 |
| `member` | Analyst / read-mostly | 10 |

Roles are **ranked and inclusive**: a permission granted to `manager` is granted to `admin`
and `owner`. This avoids the combinatorial mess of independent role grants at a scale where
custom roles are not a requirement.

Exactly one `owner` is guaranteed per organization. The last owner cannot be demoted or
removed; ownership must be transferred first. Enforced in the service layer **and** by a
deferred constraint check in a trigger — losing the sole owner locks an org out of its own
billing.

### Permission matrix

| Capability | owner | admin | manager | member |
| --- | :---: | :---: | :---: | :---: |
| View dashboard, jobs, candidates, analytics | ✅ | ✅ | ✅ | ✅ |
| Export data | ✅ | ✅ | ✅ | ✅ |
| Upload / map / commit an import | ✅ | ✅ | ✅ | ❌ |
| Delete an import (and its derived data) | ✅ | ✅ | ❌ | ❌ |
| Review a candidate (confirm/reject/classify) | ✅ | ✅ | ✅ | ❌ |
| Reopen / change a previous classification | ✅ | ✅ | ✅ | ❌ |
| Manage rework categories & root causes | ✅ | ✅ | ❌ | ❌ |
| Edit detection rules / thresholds | ✅ | ✅ | ❌ | ❌ |
| Edit cost model | ✅ | ✅ | ❌ | ❌ |
| Invite members / change roles | ✅ | ✅ | ❌ | ❌ |
| Assign the `owner` role | ✅ | ❌ | ❌ | ❌ |
| Organization settings (name, timezone, currency) | ✅ | ✅ | ❌ | ❌ |
| Billing & subscription | ✅ | ❌ | ❌ | ❌ |
| View audit log | ✅ | ✅ | ❌ | ❌ |
| Delete the organization | ✅ | ❌ | ❌ | ❌ |

Encoded as a `Permission` enum mapped to a minimum rank:

```python
PERMISSION_MIN_RANK: Final[dict[Permission, int]] = {
    Permission.JOBS_READ:            Rank.MEMBER,
    Permission.IMPORTS_WRITE:        Rank.MANAGER,
    Permission.REVIEWS_WRITE:        Rank.MANAGER,
    Permission.DETECTION_CONFIGURE:  Rank.ADMIN,
    Permission.MEMBERS_MANAGE:       Rank.ADMIN,
    Permission.BILLING_MANAGE:       Rank.OWNER,
    ...
}
```

Checked by a dependency `require_permission(Permission.X)` that reads the role from
`TenantContext`. **Authorization is never checked in the frontend for enforcement** — the
frontend hides controls for usability; the backend decides.

---

## 4. Cross-tenant attack surface

Each row is a concrete risk with its concrete mitigation. This table is the checklist for the
security review in [19-testing-strategy.md](19-testing-strategy.md).

| # | Risk | Vector | Mitigation |
| --- | --- | --- | --- |
| 1 | **IDOR on any resource** | `GET /orgs/{my_org}/jobs/{other_orgs_job_id}` | Repository `get_by_id` always filters by org; RLS backstop; 404 not 403 |
| 2 | **Org-swap in the path** | User passes an org they are not a member of | `require_org_context` membership check; 404 |
| 3 | **Nested resource confusion** | `/orgs/A/candidates/{id}` where the candidate's job belongs to B | Candidates carry their own `organization_id`; never inferred by joining through another table |
| 4 | **Background job loses tenant context** | Worker reuses ambient/last-seen context | `TenantContext` is reconstructed *from the job row's* `organization_id` on every execution. Handlers receive a context argument and have no access to a global one |
| 5 | **Object storage traversal** | User-supplied filename in the R2 key | Keys are built only from server-generated UUIDs: `orgs/{org_id}/imports/{import_id}/source.csv`. Original filename stored as a DB column, never used in a key. See [10-storage.md](10-storage.md) |
| 6 | **Signed URL leakage / reuse** | A presigned GET shared or logged | Short TTL (≤ 300 s), generated per-request after an authorization check, never logged, never embedded in an email |
| 7 | **Cache poisoning (future)** | Shared cache key without org | Any cache key MUST be prefixed `org:{organization_id}:`. A cache helper that refuses un-prefixed keys is the enforcement point. Not applicable in V1 (no cache) |
| 8 | **Export file containing foreign rows** | Export query missing filter | Exports run through the same tenant repositories; export object key is org-namespaced |
| 9 | **Audit log disclosure** | Reading another org's audit trail | `audit_events.organization_id` + RLS; only admin+ may read |
| 12 | **Enumeration via error messages** | "Job not found in org X" vs "Job belongs to org Y" | Uniform 404 body; error responses never echo a resource's owning org |
| 13 | **Aggregate leakage** | An analytics query that groups without an org filter | Analytics repositories are tenant-scoped like all others; raw-SQL analytics covered by the raw-SQL audit test |
| 14 | **Invitation token replay** | Accepting an invite mints a membership for the wrong org | Token is a hash lookup returning the invitation row; the org comes from that row, never from the request body |
| 15 | **Session fixation across orgs** | Session carries a "current org" that outlives membership | The session carries **no** org. Org comes from the URL and is re-validated per request; membership revocation is effective immediately |

Risk 15 deserves emphasis: **do not put the active organization in the session.** It is
tempting (saves a query) and it creates a stale-authorization bug where a removed user keeps
access until their session expires.

---

## 5. Tenant context in background jobs

```python
async def execute(job: BackgroundJobRow) -> None:
    tenant = TenantContext(
        organization_id=job.organization_id,   # ← the only source
        actor_user_id=job.enqueued_by_user_id, # for audit attribution
        role=None,                             # system actor: permission checks bypassed
        request_id=job.correlation_id,
    )
    handler = REGISTRY[job.job_type]
    async with session_for(tenant) as session:   # emits SET LOCAL app.current_org_id
        await handler(session, tenant, job.payload_model())
```

- `organization_id` is `NOT NULL` for all tenant work; system-wide maintenance jobs use a
  separate `system_jobs` type set that is explicitly not tenant-scoped and may not touch
  tenant tables through the normal repositories.
- Handlers take `tenant` as an explicit parameter. There is no `contextvar` holding tenant
  identity for data access — a contextvar is exactly how tenant context leaks between
  concurrently-running coroutines on one worker.
- `role=None` means "system actor." Services must treat a `None` role as *bypassing
  permission checks but still being fully org-scoped*. Permission checks belong at the API
  boundary; the worker has already had its authorization decided at enqueue time.

---

## 6. Data-access requirements (binding rules)

1. Every tenant table has `organization_id uuid NOT NULL REFERENCES organizations(id)`.
2. Every tenant table has RLS enabled **and forced**, with a policy referencing
   `app.current_org_id`.
3. Every index on a tenant table that supports a lookup has `organization_id` as its
   **leading column**. This serves both correctness (the planner uses the index for the
   tenant predicate) and performance (a per-tenant range scan rather than a global one).
4. Unique constraints on tenant data are scoped to the tenant:
   `UNIQUE (organization_id, external_id)`, never `UNIQUE (external_id)`.
5. Foreign keys between tenant tables must not permit cross-tenant references. Postgres
   cannot express "same org" in a simple FK; where the risk is material (`rework_candidates`
   → two `jobs`), use a **composite FK against a composite unique key**:

   ```sql
   -- on jobs
   UNIQUE (organization_id, id)
   -- on rework_candidates
   FOREIGN KEY (organization_id, prior_job_id)    REFERENCES jobs (organization_id, id),
   FOREIGN KEY (organization_id, followup_job_id) REFERENCES jobs (organization_id, id)
   ```

   This makes a cross-tenant candidate *structurally impossible*, not merely unlikely. Apply
   this pattern to the high-value relationships listed in
   [04-data-model.md §9](04-data-model.md); it is overkill everywhere else.
6. No query in a tenant repository may use `session.get()`, `session.merge()`, or a bare
   `select(Model).where(Model.id == ...)`.
