# 04 — Data Model

This is the authoritative schema specification. Alembic migrations must match it; where they
diverge, this document is updated in the same PR.

---

## 1. Global conventions

| Concern | Rule |
| --- | --- |
| Primary keys | `uuid` holding **UUIDv7**, generated in Python. Column default `gen_random_uuid()` as a safety net only. Rationale in [00 ADR-010](00-overview-and-decisions.md) |
| Tenant column | `organization_id uuid NOT NULL REFERENCES organizations(id)` on every tenant table |
| Timestamps | `timestamptz` **always**, stored UTC. Never `timestamp`. `created_at`/`updated_at` on every mutable table, defaulting to `now()` |
| Local dates | Where business meaning is a calendar day, add an explicit `date` column computed in the org's timezone (see §3) |
| Money | `numeric(14,2)` + a `currency_code char(3)` companion. **Never `float`/`double`/`real`** |
| Quantities | `numeric(12,3)` |
| Scores | `numeric(6,2)` raw, `numeric(5,2)` normalized (0–100) |
| Probabilities | `numeric(4,3)` (0.000–1.000) |
| Text | `text` — never `varchar(n)` unless a real external limit exists. Length validated in Pydantic |
| Email | `citext` (case-insensitive), always stored lowercased anyway |
| Enums | **Postgres native enums only for closed, code-owned sets** (job status, background job status, roles). Anything a customer can extend is a table, not an enum |
| JSONB | Used for genuinely schemaless data (raw import rows, rule params, AI output, audit diffs). Never for data we filter or join on regularly |
| Soft delete | Selective — see §10 |
| Naming | `snake_case`, plural table names, `<table>_<cols>_idx` / `_key` / `_fkey` |

### Why a `date` column alongside `timestamptz`

"Two visits 8 days apart" is a statement about calendar days in the shop's local timezone. A
job completed at 23:30 on 1 March and one at 00:30 on 2 March are a day apart to the business
and 1 hour apart in UTC arithmetic. Storing `service_date date` (computed as
`(started_at AT TIME ZONE organizations.timezone)::date` at write time) makes day-based rules
correct and makes daily analytics groupings index-friendly. `started_at timestamptz` remains
the precise instant.

---

## 2. The four data layers

Restating [00 §2](00-overview-and-decisions.md) as a table assignment, because every
implementer needs this mapping:

| Layer | Tables |
| --- | --- |
| **1 — Source/raw** (immutable evidence) | `import_batches` (file metadata + R2 key), `import_rows.raw_data` |
| **2 — Normalized operational** (rebuildable from layer 1) | `customers`, `locations`, `equipment`, `technicians`, `jobs`, `job_notes`, `job_line_items`, `service_categories` |
| **3 — Derived analytical** (safe to wipe and recompute) | `detection_runs`, `rework_candidates`*, `candidate_signals`, `candidate_score_history`, analytics rollups |
| **4 — Human-confirmed truth** (never machine-written) | `rework_reviews`, `rework_categories`, `root_causes`, `rework_cost_snapshots` |

\* `rework_candidates` is a hybrid: the **row identity** (the job pair) is stable and must
survive recomputation because layer-4 reviews point at it; the **scoring columns** on it are
layer 3 and are freely overwritten. This is why detection **upserts** candidates and never
does `DELETE` + `INSERT`. See §6.

---

## 3. Identity & tenancy

### `users`

Not tenant-owned. A person with one login who may belong to several organizations.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `email` | citext NOT NULL UNIQUE | lowercased at write |
| `full_name` | text NOT NULL | |
| `status` | enum `user_status` NOT NULL | `pending_verification`, `active`, `suspended`, `deactivated` |
| `email_verified_at` | timestamptz NULL | |
| `last_login_at` | timestamptz NULL | |
| `timezone` | text NULL | IANA; display preference, falls back to org |
| `created_at` / `updated_at` | timestamptz NOT NULL | |
| `deleted_at` | timestamptz NULL | soft delete + anonymisation, see [12](12-privacy-and-data-lifecycle.md) |

- `UNIQUE (email)` — partial on `deleted_at IS NULL` so a deleted user's address can be reused.
- Index `(status)` for admin queries.

### `user_credentials`

Split from `users` so that a password hash is never accidentally loaded into a response model
or logged with a user object. One row per user.

| Column | Type | Notes |
| --- | --- | --- |
| `user_id` | uuid PK, FK → users `ON DELETE CASCADE` | |
| `password_hash` | text NOT NULL | Argon2id PHC string |
| `password_updated_at` | timestamptz NOT NULL | |
| `failed_attempt_count` | int NOT NULL DEFAULT 0 | |
| `locked_until` | timestamptz NULL | |

### `user_sessions`

Specified in [03-authentication.md §2](03-authentication.md).

### Token tables

`email_verification_tokens`, `password_reset_tokens`, `email_change_tokens` — identical shape:

| Column | Type |
| --- | --- |
| `id` | uuid PK |
| `user_id` | uuid FK → users `ON DELETE CASCADE` |
| `token_hash` | bytea NOT NULL UNIQUE |
| `expires_at` | timestamptz NOT NULL |
| `consumed_at` | timestamptz NULL |
| `created_at` | timestamptz NOT NULL |
| `new_email` | citext NULL *(email_change only)* |

Index `(user_id, consumed_at)`. Purged 30 days after expiry.

### `organizations`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `name` | text NOT NULL | |
| `slug` | citext NOT NULL UNIQUE | URL-safe; reserved-word blocklist |
| `timezone` | text NOT NULL DEFAULT `'UTC'` | IANA. Drives `service_date` and day-window math |
| `currency_code` | char(3) NOT NULL DEFAULT `'USD'` | ISO 4217 |
| `industry_key` | text NULL | `hvac`, `plumbing`, … Selects seed data only; **no code branches on this** |
| `status` | enum `organization_status` NOT NULL | `active`, `suspended`, `pending_deletion` |
| `onboarding_completed_at` | timestamptz NULL | |
| `created_by_user_id` | uuid FK → users `ON DELETE SET NULL` | |
| `created_at` / `updated_at` | timestamptz NOT NULL | |
| `deleted_at` | timestamptz NULL | |
| `purge_after` | timestamptz NULL | set on deletion request; grace period |

### `organization_memberships`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL FK → organizations `ON DELETE CASCADE` | |
| `user_id` | uuid NOT NULL FK → users `ON DELETE CASCADE` | |
| `role` | enum `organization_role` NOT NULL | `owner`, `admin`, `manager`, `member` |
| `invited_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | |
| `joined_at` | timestamptz NOT NULL | |
| `revoked_at` | timestamptz NULL | |

- `UNIQUE (organization_id, user_id) WHERE revoked_at IS NULL` — a user has at most one active
  membership per org, while historical revoked rows are retained for audit.
- Index `(user_id) WHERE revoked_at IS NULL` — powers "my organizations", a per-request query.
- Index `(organization_id, role) WHERE revoked_at IS NULL` — powers the owner-count guard.
- A trigger (or a deferred check in the service) guarantees ≥ 1 active `owner` per active org.

### `organization_invitations`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL FK → organizations `ON DELETE CASCADE` | |
| `email` | citext NOT NULL | |
| `role` | enum `organization_role` NOT NULL | the role **the token grants** |
| `token_hash` | bytea NOT NULL UNIQUE | |
| `invited_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | |
| `expires_at` | timestamptz NOT NULL | |
| `accepted_at` / `accepted_by_user_id` | timestamptz / uuid NULL | |
| `revoked_at` | timestamptz NULL | |
| `created_at` | timestamptz NOT NULL | |

`UNIQUE (organization_id, email) WHERE accepted_at IS NULL AND revoked_at IS NULL` — one live
invitation per address per org.

---

## 4. Customers, locations, equipment

These three tables are where **entity resolution** lives, and they are the main source of
import subtlety: a CSV rarely carries stable IDs, so we must derive them.

### `customers`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `source_system_id` | uuid NULL FK → source_systems | |
| `external_id` | text NULL | their ID, when the CSV has one |
| `natural_key_hash` | bytea NOT NULL | see §4.4 |
| `display_name` | text NOT NULL | |
| `normalized_name` | text NOT NULL | casefold, punctuation stripped, legal suffixes removed |
| `customer_type` | text NULL | `residential` / `commercial` — free text, org-defined |
| `email` | citext NULL | |
| `phone_raw` | text NULL | |
| `phone_e164` | text NULL | normalized; the strongest matching key |
| `account_number` | text NULL | |
| `first_seen_job_at` / `last_seen_job_at` | timestamptz NULL | maintained by the import, for cheap sorting |
| `job_count` | int NOT NULL DEFAULT 0 | denormalized counter, rebuildable |
| `created_at` / `updated_at` / `deleted_at` | | |

Keys and indexes:
- `UNIQUE (organization_id, id)` — enables composite FKs (§9).
- `UNIQUE (organization_id, source_system_id, external_id) WHERE external_id IS NOT NULL AND deleted_at IS NULL`
- `UNIQUE (organization_id, natural_key_hash) WHERE deleted_at IS NULL`
- `(organization_id, normalized_name)` — search
- `(organization_id, phone_e164) WHERE phone_e164 IS NOT NULL` — matching
- GIN trigram on `normalized_name` for fuzzy search (`pg_trgm`)

### `locations`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `customer_id` | uuid NULL FK → customers | a location may exist before its customer is known |
| `external_id` | text NULL | |
| `address_hash` | bytea NOT NULL | sha256 of the normalized address tuple |
| `label` | text NULL | "Main office", "Unit 4" |
| `address_line1` / `address_line2` | text NULL | |
| `city` / `region` / `postal_code` | text NULL | |
| `country_code` | char(2) NULL | |
| `latitude` / `longitude` | numeric(9,6) NULL | populated only if the source provides it — **no geocoding in V1** |
| `created_at` / `updated_at` / `deleted_at` | | |

- `UNIQUE (organization_id, id)`
- `UNIQUE (organization_id, customer_id, address_hash) WHERE deleted_at IS NULL`
- `(organization_id, postal_code)`

### `equipment`

The hardest entity to resolve, and the highest-value signal when it resolves correctly — "same
unit, twice in nine days" is the single most persuasive rework indicator.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `customer_id` | uuid NULL FK → customers | |
| `location_id` | uuid NULL FK → locations | |
| `external_id` | text NULL | |
| `natural_key_hash` | bytea NOT NULL | |
| `asset_tag` | text NULL | |
| `serial_number` | text NULL | strongest identity when present |
| `manufacturer` | text NULL | |
| `model` | text NULL | |
| `equipment_type` | text NULL | vertical-neutral: "condenser", "water heater", "panel" |
| `installed_on` | date NULL | |
| `warranty_expires_on` | date NULL | feeds the `warranty_window` signal |
| `created_at` / `updated_at` / `deleted_at` | | |

- `UNIQUE (organization_id, id)`
- `UNIQUE (organization_id, natural_key_hash) WHERE deleted_at IS NULL`
- `(organization_id, location_id)`, `(organization_id, serial_number) WHERE serial_number IS NOT NULL`

### 4.4 Natural key derivation (the identity rules)

Deterministic, documented, and **implemented once** in `imports/normalization/identity.py`.
Each entity tries rules in order and uses the first that yields a value:

**Customer**
1. `sha256(org_id | source_system_id | external_id)` when an external ID is present
2. `sha256(org_id | phone_e164)` when a phone is present
3. `sha256(org_id | normalized_name | postal_code)`
4. `sha256(org_id | normalized_name)` — last resort, logged as a low-confidence match

**Location**
1. external ID
2. `sha256(org_id | customer_key | normalized_address_line1 | postal_code)`

**Equipment**
1. external ID
2. `sha256(org_id | upper(serial_number))` when a serial is present
3. `sha256(org_id | location_key | manufacturer | model | equipment_type)`
4. No key derivable → **equipment is left NULL on the job**, not invented

Rule 4 matters. Fabricating an equipment row per job would make `same_equipment` fire on every
pair and destroy the signal's value. **An absent identifier must produce an absent link, never
a synthetic one.** The same principle applies to customers: if nothing above resolves, the row
is an error, not a guess — see [06-csv-ingestion.md §6](06-csv-ingestion.md).

---

## 5. Workforce & operational data

### `technicians`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `external_id` | text NULL | |
| `natural_key_hash` | bytea NOT NULL | external id → employee_code → normalized name |
| `full_name` | text NOT NULL | |
| `normalized_name` | text NOT NULL | |
| `employee_code` | text NULL | |
| `email` | citext NULL | |
| `hourly_cost_amount` | numeric(14,2) NULL | per-tech override of the cost model default |
| `currency_code` | char(3) NULL | |
| `is_active` | boolean NOT NULL DEFAULT true | |
| `user_id` | uuid NULL FK → users `ON DELETE SET NULL` | optional link if the tech also logs in |
| `created_at` / `updated_at` / `deleted_at` | | |

`UNIQUE (organization_id, id)`, `UNIQUE (organization_id, natural_key_hash) WHERE deleted_at IS NULL`.

**Privacy note:** technician-level rework rates are the most politically sensitive output this
product creates. The data model supports it; the product should present it carefully, and
[12-privacy-and-data-lifecycle.md §7](12-privacy-and-data-lifecycle.md) records the position.

### `service_categories`

Org-scoped taxonomy — *not* an enum, because "Heat Pump — Diagnostic" means nothing to a pest
control company.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `key` | text NOT NULL | stable slug |
| `label` | text NOT NULL | |
| `parent_id` | uuid NULL FK → service_categories `ON DELETE SET NULL` | one level of nesting expected |
| `is_system_default` | boolean NOT NULL DEFAULT false | seeded from the industry pack |
| `is_active` | boolean NOT NULL DEFAULT true | |
| `sort_order` | int NOT NULL DEFAULT 0 | |

`UNIQUE (organization_id, key)`.

### `source_systems`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `kind` | enum `source_system_kind` | `csv_upload`, `api`, `servicetitan`, `jobber`, `housecall_pro` |
| `name` | text NOT NULL | "2024 export", "ServiceTitan prod" |
| `is_default` | boolean NOT NULL DEFAULT false | |
| `created_at` | timestamptz NOT NULL | |

`UNIQUE (organization_id, name)`. External IDs are only unique **within** a source system —
two different FSM exports may both use `JOB-1001` for different jobs.

### `jobs` — the core operational table

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `source_system_id` | uuid NOT NULL FK → source_systems | |
| `external_id` | text NULL | customer's job ID |
| `natural_key_hash` | bytea NOT NULL | dedup key when `external_id` is absent |
| `first_import_batch_id` | uuid NULL FK → import_batches `ON DELETE SET NULL` | |
| `last_import_batch_id` | uuid NULL FK → import_batches `ON DELETE SET NULL` | |
| `customer_id` | uuid NULL FK → customers | |
| `location_id` | uuid NULL FK → locations | |
| `equipment_id` | uuid NULL FK → equipment | |
| `technician_id` | uuid NULL FK → technicians | |
| `service_category_id` | uuid NULL FK → service_categories | |
| `job_number` | text NULL | human-facing reference |
| `raw_service_category` | text NULL | the unmapped source value, kept for re-mapping |
| `raw_job_type` | text NULL | |
| `status` | enum `job_status` NOT NULL DEFAULT `'unknown'` | `completed`, `cancelled`, `scheduled`, `in_progress`, `unknown` |
| `scheduled_at` | timestamptz NULL | |
| `started_at` | timestamptz NULL | |
| `completed_at` | timestamptz NULL | |
| `service_date` | date NOT NULL | org-local calendar date; the ordering/window key |
| `duration_minutes` | int NULL | |
| `summary` | text NULL | short description |
| `description` | text NULL | |
| `symptoms_text` | text NULL | reported problem |
| `diagnosis_text` | text NULL | what the tech found |
| `resolution_text` | text NULL | what the tech did |
| `invoice_number` | text NULL | |
| `revenue_amount` | numeric(14,2) NULL | invoiced total |
| `parts_amount` | numeric(14,2) NULL | |
| `labor_amount` | numeric(14,2) NULL | |
| `currency_code` | char(3) NOT NULL | denormalized from org; explicit for future multi-currency |
| `is_warranty` | boolean NOT NULL DEFAULT false | source-flagged warranty work |
| `is_no_charge` | boolean NOT NULL DEFAULT false | derived: `revenue_amount = 0` |
| `warranty_reference` | text NULL | claim number |
| `extra_fields` | jsonb NOT NULL DEFAULT `'{}'` | unmapped columns the org chose to retain |
| `search_document` | tsvector GENERATED ALWAYS AS (...) STORED | over summary/description/symptoms/diagnosis/resolution |
| `created_at` / `updated_at` / `deleted_at` | | |

**`service_date` is NOT NULL** and is the anchor for candidate generation. When a source
provides no usable date at all, the row is an import **error**, not a job with a guessed date —
a job without a date cannot participate in time-window detection and would silently degrade
every result.

Indexes:

| Index | Purpose |
| --- | --- |
| `UNIQUE (organization_id, id)` | composite FK target |
| `UNIQUE (organization_id, source_system_id, external_id) WHERE external_id IS NOT NULL AND deleted_at IS NULL` | idempotent re-import |
| `UNIQUE (organization_id, natural_key_hash) WHERE deleted_at IS NULL` | dedup without external IDs |
| `(organization_id, customer_id, service_date)` | **the candidate-generation index** — primary blocking key |
| `(organization_id, equipment_id, service_date) WHERE equipment_id IS NOT NULL` | equipment-blocked generation |
| `(organization_id, location_id, service_date) WHERE location_id IS NOT NULL` | location-blocked generation |
| `(organization_id, service_date DESC, id DESC)` | job list default sort + cursor pagination |
| `(organization_id, technician_id, service_date)` | technician analytics |
| `(organization_id, last_import_batch_id)` | import rollback/delete |
| `GIN (search_document)` | full-text search |

### `job_notes`

Separate from `jobs` because notes are 1-to-many and should not duplicate the job row.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `job_id` | uuid NOT NULL FK → jobs `ON DELETE CASCADE` | |
| `note_type` | text NOT NULL DEFAULT `'technician'` | `technician`, `dispatch`, `customer`, `internal` |
| `author_name` | text NULL | |
| `body` | text NOT NULL | |
| `occurred_at` | timestamptz NULL | |
| `content_hash` | bytea NOT NULL | dedup on re-import |
| `created_at` | timestamptz NOT NULL | |

`UNIQUE (organization_id, job_id, content_hash)` — re-importing the same file does not
duplicate notes. Index `(organization_id, job_id)`.

### `job_line_items`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `job_id` | uuid NOT NULL FK → jobs `ON DELETE CASCADE` | |
| `kind` | enum `line_item_kind` | `part`, `labor`, `fee`, `discount`, `other` |
| `code` | text NULL | part number / SKU — a strong repeat-failure signal |
| `description` | text NULL | |
| `quantity` | numeric(12,3) NOT NULL DEFAULT 1 | |
| `unit_amount` | numeric(14,2) NULL | |
| `total_amount` | numeric(14,2) NULL | |
| `currency_code` | char(3) NOT NULL | |
| `line_number` | int NULL | |

Index `(organization_id, job_id)`, `(organization_id, code) WHERE code IS NOT NULL` — the
latter powers "which part keeps failing", a headline analytics feature.

---

## 6. Detection (layer 3, with a stable identity spine)

### `detection_signal_definitions` — **global, not tenant-scoped**

The catalogue of signals the *code* implements. Rows are created by migration, in lockstep
with the signal registry in `detection/signals/`.

| Column | Type |
| --- | --- |
| `key` | text PK — e.g. `same_equipment` |
| `label` | text NOT NULL |
| `description` | text NOT NULL — shown in the settings UI |
| `value_type` | enum: `boolean`, `numeric`, `ratio`, `categorical` |
| `default_weight` | numeric(8,2) NOT NULL |
| `default_params` | jsonb NOT NULL DEFAULT `'{}'` |
| `supported_kinds` | text[] NOT NULL — which rule kinds are legal for this signal |
| `is_active` | boolean NOT NULL DEFAULT true |

### `detection_rule_sets` — immutable versions

Collapsed from a parent/version pair: each row **is** a version. One active per org.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `version_number` | int NOT NULL | monotonic per org |
| `name` | text NULL | optional label for the change |
| `is_active` | boolean NOT NULL DEFAULT false | |
| `window_days` | int NOT NULL DEFAULT 30 | the outer candidate-generation window |
| `min_score_to_surface` | numeric(5,2) NOT NULL DEFAULT 40 | below this, stored but hidden by default |
| `max_followups_per_job` | int NOT NULL DEFAULT 25 | fan-out guard, §6 of [07](07-detection-engine.md) |
| `notes` | text NULL | |
| `created_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (organization_id, version_number)`
- `UNIQUE (organization_id) WHERE is_active` — exactly one active set per org, enforced by the
  database rather than by hope.
- **Rows are never updated** (except flipping `is_active`). Editing settings inserts a new
  version. This is what makes a score reproducible.

### `detection_rules`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `rule_set_id` | uuid NOT NULL FK → detection_rule_sets `ON DELETE CASCADE` | |
| `signal_key` | text NOT NULL FK → detection_signal_definitions(key) | |
| `kind` | enum `rule_kind` NOT NULL | `additive`, `multiplier`, `gate`, `veto` |
| `weight` | numeric(8,2) NOT NULL DEFAULT 0 | |
| `params` | jsonb NOT NULL DEFAULT `'{}'` | e.g. `{"bands": [[0,7,1.0],[8,14,0.6]]}` |
| `is_enabled` | boolean NOT NULL DEFAULT true | |
| `sort_order` | int NOT NULL DEFAULT 0 | display order in the evidence panel |

`UNIQUE (rule_set_id, signal_key)`.

The four rule kinds, which together give an extensible scoring model without a DSL:

| Kind | Effect |
| --- | --- |
| `additive` | contributes `weight × signal_strength` to the raw score |
| `multiplier` | scales the running score (e.g. ×1.2 when the follow-up is within warranty) |
| `gate` | if unmatched, the candidate is not surfaced (score is still stored) |
| `veto` | if matched, the candidate is **suppressed** with a recorded reason |

`veto` exists because "scheduled maintenance visit" or "planned multi-day install, part 2 of 3"
are not rework and should not merely score a bit lower — they should be removed. A weight-only
model cannot express that cleanly.

### `detection_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `rule_set_id` | uuid NOT NULL FK → detection_rule_sets | the version used |
| `trigger` | enum `detection_trigger` | `import_completed`, `rules_changed`, `manual`, `scheduled` |
| `scope` | jsonb NOT NULL DEFAULT `'{}'` | e.g. `{"import_batch_id": "...", "from": "2026-01-01"}` |
| `status` | enum `run_status` | `queued`, `running`, `completed`, `failed`, `cancelled` |
| `pairs_evaluated` | bigint NOT NULL DEFAULT 0 | |
| `candidates_created` | int NOT NULL DEFAULT 0 | |
| `candidates_updated` | int NOT NULL DEFAULT 0 | |
| `candidates_suppressed` | int NOT NULL DEFAULT 0 | |
| `background_job_id` | uuid NULL FK → background_jobs `ON DELETE SET NULL` | |
| `started_at` / `completed_at` | timestamptz NULL | |
| `error_message` | text NULL | |
| `created_at` / `updated_at` | timestamptz NOT NULL | mutable run lifecycle timestamps |

Index `(organization_id, started_at DESC)`.

### `rework_candidates` — the stable pair identity

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | **stable across re-runs** |
| `organization_id` | uuid NOT NULL | |
| `prior_job_id` | uuid NOT NULL | the earlier visit |
| `followup_job_id` | uuid NOT NULL | the later visit |
| `customer_id` / `location_id` / `equipment_id` | uuid NULL | denormalized for filtering & grouping |
| `technician_prior_id` / `technician_followup_id` | uuid NULL | denormalized for technician analytics |
| `days_between` | int NOT NULL | calendar days, org timezone |
| `current_score` | numeric(6,2) NULL | raw |
| `current_normalized_score` | numeric(5,2) NULL | 0–100 |
| `score_band` | enum `score_band` NULL | `low`, `medium`, `high` |
| `is_suppressed` | boolean NOT NULL DEFAULT false | hidden from the active review queue |
| `suppression_reason` | enum `candidate_suppression_reason` NULL | `signal_veto`, `out_of_window` |
| `suppressed_by_signal_key` | text NULL | required only for `signal_veto` |
| `workflow_status` | enum `candidate_workflow_status` NOT NULL DEFAULT `'open'` | `open`, `in_review`, `reviewed`, `dismissed` |
| `current_rule_set_id` | uuid NULL FK → detection_rule_sets `ON DELETE SET NULL` | |
| `current_detection_run_id` | uuid NULL FK → detection_runs `ON DELETE SET NULL` | |
| `first_detected_at` | timestamptz NOT NULL | |
| `last_evaluated_at` | timestamptz NOT NULL | |
| `created_at` / `updated_at` | | |

Constraints:

- `UNIQUE (organization_id, prior_job_id, followup_job_id)` ← **the upsert target**
- `CHECK (prior_job_id <> followup_job_id)`
- suppression state is internally consistent: unsuppressed rows have no reason/key; a
  `signal_veto` has a signal key; `out_of_window` has no signal key
- `UNIQUE (organization_id, id)`
- Composite FKs guaranteeing both jobs belong to the same org as the candidate:
  ```sql
  FOREIGN KEY (organization_id, prior_job_id)    REFERENCES jobs (organization_id, id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, followup_job_id) REFERENCES jobs (organization_id, id) ON DELETE CASCADE
  ```

**Canonical ordering.** The pair is always stored with the earlier job as `prior_job_id`,
ordered by `(service_date, started_at, id)`. Without this, `(A,B)` and `(B,A)` can both exist
and the unique constraint is useless. The ordering helper lives in
`detection/pairing.py` and is the only place that constructs a pair.

Indexes:

| Index | Purpose |
| --- | --- |
| `(organization_id, current_normalized_score DESC, id DESC) WHERE NOT is_suppressed AND workflow_status = 'open'` | the review queue — the app's busiest query |
| `(organization_id, workflow_status, last_evaluated_at DESC)` | filters |
| `(organization_id, followup_job_id)` / `(organization_id, prior_job_id)` | job detail page: "this job's linked visits" |
| `(organization_id, equipment_id) WHERE equipment_id IS NOT NULL` | recurring-equipment analytics |
| `(organization_id, current_detection_run_id)` | run inspection |

`workflow_status` (a queue state) is deliberately **separate** from the review's `decision`
(a judgement). Conflating them means you cannot express "reviewed and confirmed" vs
"dismissed without judgement" vs "reopened."

### `candidate_signals` — the explainability record

**This table is why the product is trustworthy.** One row per signal evaluated per run.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `candidate_id` | uuid NOT NULL FK → rework_candidates `ON DELETE CASCADE` | |
| `detection_run_id` | uuid NOT NULL FK → detection_runs `ON DELETE CASCADE` | |
| `signal_key` | text NOT NULL | |
| `rule_kind` | enum `rule_kind` NOT NULL | |
| `outcome` | enum `signal_outcome` NOT NULL | `matched`, `not_matched`, `not_evaluable` |
| `strength` | numeric(5,4) NOT NULL DEFAULT 1 | 0–1; lets a band/ratio contribute partially |
| `raw_value` | jsonb NULL | `{"days": 8}`, `{"cosine": 0.89}`, `{"serial": "match"}` |
| `weight_applied` | numeric(8,2) NOT NULL | the weight from the rule set version |
| `contribution` | numeric(8,2) NOT NULL | what it actually added to the score |
| `explanation` | text NOT NULL | pre-rendered human sentence: "Same equipment (serial ...4821)" |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (candidate_id, detection_run_id, signal_key)`
- Index `(organization_id, detection_run_id)` for bulk cleanup.

**Non-matching and non-evaluable signals are stored too.** "Different technician — no
contribution" is informative to a reviewer, while "No equipment recorded — not evaluable"
explains why a configured weight was excluded from the denominator. A boolean `matched` column
would collapse those distinct states and is therefore deliberately not used. The UI renders
matched signals prominently and the other outcomes on demand.

**Retention:** keep signals for the **current** run of each candidate plus the two most recent
prior runs; a cleanup job deletes older ones. Unbounded retention would make this the largest
table in the database for no benefit.

### `candidate_score_history`

Small, cheap, and the only way to answer "did my rule change help?"

| Column | Type |
| --- | --- |
| `id` | uuid PK |
| `organization_id` | uuid NOT NULL |
| `candidate_id` | uuid NOT NULL FK → rework_candidates `ON DELETE CASCADE` |
| `detection_run_id` | uuid NOT NULL FK → detection_runs `ON DELETE CASCADE` |
| `rule_set_id` | uuid NOT NULL |
| `raw_score` / `normalized_score` | numeric |
| `score_band` | enum |
| `is_suppressed` | boolean |
| `created_at` | timestamptz |

`UNIQUE (candidate_id, detection_run_id)`.

---

## 7. Human review (layer 4 — never machine-written)

### `rework_categories`

Configurable per organization, seeded with the brief's list.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `key` | text NOT NULL | |
| `label` | text NOT NULL | |
| `description` | text NULL | |
| `outcome` | enum `category_outcome` NOT NULL | `rework`, `not_rework`, `uncertain` |
| `counts_toward_cost` | boolean NOT NULL DEFAULT true | |
| `is_system_default` | boolean NOT NULL DEFAULT false | |
| `is_active` | boolean NOT NULL DEFAULT true | |
| `color` | text NULL | |
| `sort_order` | int NOT NULL DEFAULT 0 | |

`UNIQUE (organization_id, key)`.

The `outcome` column is what makes this configurable **and** analysable: analytics never
hard-codes category keys, it groups by `outcome` and `counts_toward_cost`. A customer can
invent "Comfort complaint — no fault found" and the cost engine still behaves correctly
because they also chose an outcome for it.

Seeded defaults:

| key | outcome | counts_toward_cost |
| --- | --- | --- |
| `confirmed_callback` | rework | ✅ |
| `warranty` | rework | ✅ |
| `workmanship` | rework | ✅ |
| `misdiagnosis` | rework | ✅ |
| `failed_part` | rework | ✅ |
| `incomplete_repair` | rework | ✅ |
| `scheduled_followup` | not_rework | ❌ |
| `customer_caused` | not_rework | ❌ |
| `unrelated` | not_rework | ❌ |
| `unsure` | uncertain | ❌ |

### `root_causes`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `key` / `label` | text NOT NULL | |
| `parent_id` | uuid NULL FK → root_causes `ON DELETE RESTRICT` | one nesting level; deactivate instead of deleting |
| `is_system_default` / `is_active` | boolean | |
| `sort_order` | int | |

`UNIQUE (organization_id, key)`. Seeded vertical-neutral: `workmanship`, `diagnosis`,
`part_quality`, `parts_availability`, `access_or_scheduling`, `customer_behaviour`,
`system_design`, `documentation`, `other`.

### `rework_reviews` — append-only human decisions

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `candidate_id` | uuid NOT NULL FK → rework_candidates `ON DELETE CASCADE` | |
| `decision` | enum `review_decision` NOT NULL | `confirmed`, `rejected`, `uncertain` |
| `category_id` | uuid NULL FK → rework_categories `ON DELETE RESTRICT` | |
| `root_cause_id` | uuid NULL FK → root_causes `ON DELETE RESTRICT` | |
| `note` | text NULL | |
| `reviewed_by_user_id` | uuid NOT NULL FK → users `ON DELETE RESTRICT` | |
| `score_at_review` | numeric(5,2) NULL | what the machine said at decision time |
| `rule_set_id_at_review` | uuid NULL | |
| `decided_at` | timestamptz NOT NULL | |
| `superseded_by_review_id` | uuid NULL FK → rework_reviews `ON DELETE SET NULL` | reclassification chain |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (candidate_id) WHERE superseded_by_review_id IS NULL` — exactly one *current* review
  per candidate, enforced in the database.
- Index `(organization_id, decided_at DESC)`, `(organization_id, category_id)`,
  `(organization_id, reviewed_by_user_id)`.
- **`ON DELETE RESTRICT` on `reviewed_by_user_id`, `category_id`, `root_cause_id`** — you may
  not delete a user or a category that human truth depends on. Deactivate instead
  (`is_active = false`). This is the database refusing to let the product destroy its own
  evidence.

Rows are **never updated** except to set `superseded_by_review_id`. Changing a classification
inserts a new row and links the old one. Reclassification history is a product feature (§21 of
the brief) and an audit requirement.

The application database role has `INSERT` and column-level
`UPDATE (superseded_by_review_id)` only; it has no review `DELETE` or general `UPDATE`
privilege. Append-only behavior is therefore a database rule, not only a service convention.

`score_at_review` freezes what the deterministic detector reported when the human decided.
That column is the basis for measuring detection quality later.

### `rework_cost_snapshots`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `candidate_id` | uuid NOT NULL FK → rework_candidates `ON DELETE CASCADE` | |
| `review_id` | uuid NULL FK → rework_reviews `ON DELETE SET NULL` | |
| `cost_model_id` | uuid NOT NULL FK → organization_cost_models | the version used |
| `labor_cost` / `dispatch_cost` / `overhead_cost` / `opportunity_cost` / `parts_cost` | numeric(14,2) | |
| `total_cost` | numeric(14,2) NOT NULL | |
| `currency_code` | char(3) NOT NULL | |
| `inputs` | jsonb NOT NULL | the exact inputs used (duration, hourly rate, …) |
| `computed_at` | timestamptz NOT NULL | |

`UNIQUE (candidate_id, cost_model_id)`. Snapshotting is essential: a report titled "Q1 rework
cost: $42,300" must not silently change to $51,000 because someone raised the hourly rate in
July. The current-cost view recomputes on demand; the snapshot is the historical record.

---

## 8. Cost model

### `organization_cost_models` — immutable versions, one active

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `version_number` | int NOT NULL | |
| `is_active` | boolean NOT NULL DEFAULT false | |
| `effective_from` | date NOT NULL | |
| `technician_hourly_cost` | numeric(14,2) NOT NULL | |
| `vehicle_dispatch_cost` | numeric(14,2) NOT NULL DEFAULT 0 | per visit |
| `overhead_per_visit` | numeric(14,2) NOT NULL DEFAULT 0 | |
| `opportunity_cost_per_hour` | numeric(14,2) NOT NULL DEFAULT 0 | revenue forgone |
| `default_visit_duration_minutes` | int NOT NULL DEFAULT 90 | used when a job has no duration |
| `include_parts_cost` | boolean NOT NULL DEFAULT true | |
| `custom_factors` | jsonb NOT NULL DEFAULT `'{}'` | `[{key,label,amount,per}]` — future factors without a migration |
| `currency_code` | char(3) NOT NULL | |
| `created_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (organization_id, version_number)`, `UNIQUE (organization_id) WHERE is_active`

Cost formula (implemented in `costs/calculator.py`, pure and unit-tested):

```
hours          = COALESCE(followup.duration_minutes, default_visit_duration_minutes) / 60
labor          = hours × COALESCE(technician.hourly_cost_amount, technician_hourly_cost)
dispatch       = vehicle_dispatch_cost
overhead       = overhead_per_visit
opportunity    = hours × opportunity_cost_per_hour
parts          = include_parts_cost ? SUM(followup line items where kind = 'part') : 0
custom         = Σ custom_factors (per-visit or per-hour)
total          = labor + dispatch + overhead + opportunity + parts + custom
```

All arithmetic in `Decimal`, rounded once at the end with `ROUND_HALF_UP` to 2 dp.

---

## 9. Deferred AI data-model research (not V1 tables)

> The structures below are retained only as non-binding research. They are not present in the
> V1 schema and must not be implemented unless the trigger in
> [21 §Deferred](21-implementation-sequencing.md) is met.

### `job_embeddings`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `job_id` | uuid NOT NULL FK → jobs `ON DELETE CASCADE` | |
| `content_scope` | enum `embedding_scope` NOT NULL | `problem` (symptoms+description) / `full` (+ diagnosis, resolution, notes) |
| `model_key` | text NOT NULL | e.g. `openai:text-embedding-3-small@768` |
| `dimensions` | int NOT NULL | |
| `embedding` | `vector(768)` NOT NULL | |
| `content_hash` | bytea NOT NULL | sha256 of the exact embedded text |
| `token_count` | int NULL | |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (job_id, content_scope, model_key)`
- `(organization_id, job_id)`
- **No ANN index in V1** — see [08-ai-and-embeddings.md §5](08-ai-and-embeddings.md). Pairwise
  cosine between two known rows needs no index, and an unused HNSW index costs build time and
  ~1 GB of memory pressure for nothing.

### `ai_analyses`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `candidate_id` | uuid NULL FK → rework_candidates `ON DELETE CASCADE` | |
| `job_id` | uuid NULL FK → jobs `ON DELETE CASCADE` | |
| `analysis_type` | enum | `candidate_classification`, `job_summary`, `root_cause_hypothesis` |
| `provider` / `model_key` | text NOT NULL | |
| `prompt_key` / `prompt_version` | text / int NOT NULL | prompts live in code; see §11 |
| `input_hash` | bytea NOT NULL | dedup: identical input + prompt version ⇒ reuse |
| `status` | enum `ai_status` NOT NULL | `succeeded`, `invalid_output`, `provider_error`, `refused`, `timeout` |
| `classification` | text NULL | validated against the schema's enum |
| `confidence` | numeric(4,3) NULL | |
| `reasoning_summary` | text NULL | |
| `possible_root_cause_key` | text NULL | mapped to `root_causes.key`, nullable if unmapped |
| `output` | jsonb NULL | full validated structured output |
| `error_message` | text NULL | |
| `prompt_tokens` / `completion_tokens` | int NULL | |
| `estimated_cost_amount` | numeric(12,6) NULL | six dp — per-call costs are fractions of a cent |
| `latency_ms` | int NULL | |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (candidate_id, prompt_key, prompt_version, input_hash)` — never pay twice for the
  same question.
- `(organization_id, created_at DESC)`, `(organization_id, status)`

`classification` is a plain `text` column, **not** an enum: the model's label vocabulary is
prompt-versioned and must be able to change without a migration. It is validated in Pydantic
against the schema for that prompt version, and it is **never** written into
`rework_reviews` — AI output and human truth stay in different tables.

### `ai_usage_daily`

Rollup for quota enforcement and cost dashboards without scanning `ai_analyses`.

| Column | Type |
| --- | --- |
| `organization_id` | uuid NOT NULL |
| `usage_date` | date NOT NULL |
| `provider` / `model_key` / `operation` | text NOT NULL |
| `request_count` | int NOT NULL DEFAULT 0 |
| `prompt_tokens` / `completion_tokens` | bigint NOT NULL DEFAULT 0 |
| `estimated_cost_amount` | numeric(12,6) NOT NULL DEFAULT 0 |

PK `(organization_id, usage_date, provider, model_key, operation)`. Upserted with
`ON CONFLICT ... DO UPDATE SET request_count = ai_usage_daily.request_count + 1, ...`.

---

## 10. Imports

### `import_batches`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `source_system_id` | uuid NOT NULL FK → source_systems | |
| `created_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | |
| `status` | enum `import_status` NOT NULL | see below |
| `original_filename` | text NULL | display only — **never used to build a storage key** |
| `storage_key` | text NULL | server-generated R2 key |
| `file_size_bytes` | bigint NULL | |
| `file_sha256` | bytea NULL | duplicate-upload detection |
| `encoding` / `delimiter` / `has_header` | text / char(1) / boolean | detected at profiling |
| `detected_columns` | jsonb NULL | `[{index,name,sample_values,inferred_type}]` |
| `sample_rows` | jsonb NULL | first ~20 rows for the preview UI |
| `profile_issues` | jsonb NOT NULL DEFAULT `[]` | encoding/dialect and sampled-shape warnings shown in preview |
| `mapping` | jsonb NULL | the applied `ColumnMapping` snapshot (frozen at commit) |
| `template_id` | uuid NULL FK → import_column_mappings `ON DELETE SET NULL` | |
| `total_rows` / `processed_rows` | int | checkpointed for resume + progress UI |
| `created_jobs` / `updated_jobs` / `skipped_rows` / `warning_rows` / `error_rows` | int NOT NULL DEFAULT 0 | |
| `error_report_key` | text NULL | R2 key of the generated error CSV |
| `cancel_requested_at` | timestamptz NULL | cooperative cancellation |
| `failure_reason` | text NULL | |
| `started_at` / `completed_at` | timestamptz NULL | |
| `created_at` / `updated_at` / `deleted_at` | | |

`import_status`: `awaiting_file` → `uploaded` → `profiling` → `awaiting_mapping` →
`validating` → `validated` → `queued` → `processing` → (`completed` | `completed_with_errors` |
`failed` | `cancelled`).

- `UNIQUE (organization_id, file_sha256) WHERE file_sha256 IS NOT NULL AND deleted_at IS NULL`
  — re-uploading a byte-identical file is blocked with a clear message (overridable with an
  explicit flag, which creates a new `source_system` or is force-confirmed by the user).
- Index `(organization_id, created_at DESC)`, `(organization_id, status) WHERE status IN ('queued','processing')`.

### `import_rows`

Every single row of every file lands here. **Nothing is silently discarded.**

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `import_batch_id` | uuid NOT NULL FK → import_batches `ON DELETE CASCADE` | |
| `row_number` | int NOT NULL | 1-based, counting the header as row 1 |
| `raw_data` | jsonb NOT NULL | the row exactly as parsed — **layer 1, immutable** |
| `normalized_data` | jsonb NULL | validated source-neutral `SourceRecord`; avoids re-normalizing during commit |
| `row_hash` | bytea NOT NULL | sha256 of `raw_data`, for in-file duplicate detection |
| `status` | enum `import_row_status` NOT NULL | `pending`, `imported`, `updated`, `skipped_duplicate`, `skipped_filtered`, `warning`, `error` |
| `issues` | jsonb NOT NULL DEFAULT `'[]'` | `[{code, field, message, severity, raw_value}]` |
| `job_id` | uuid NULL FK → jobs `ON DELETE SET NULL` | what it produced |
| `created_at` | timestamptz NOT NULL | |

- `UNIQUE (import_batch_id, row_number)`
- Index `(import_batch_id, status)` — drives the error report and the "show me failed rows" UI.
- Index `(organization_id, import_batch_id)`.
- Index `(organization_id, job_id)` — supports linked-row lookup and bounded tenant cleanup.

**Retention (important — this is the table that grows fastest):** 250k rows × a JSONB payload
is easily 500 MB per large import. Policy: after **90 days**, a maintenance job nulls
`raw_data` for rows with `status IN ('imported','updated','skipped_duplicate')`, keeping error
and warning rows intact indefinitely (or until the batch is deleted). The original file remains
in R2 for the full retention window, so layer 1 is never actually lost —
[12-privacy-and-data-lifecycle.md §4](12-privacy-and-data-lifecycle.md).

### `import_column_mappings` — reusable templates

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NOT NULL | |
| `source_system_id` | uuid NULL FK → source_systems `ON DELETE SET NULL` | |
| `name` | text NOT NULL | |
| `mapping` | jsonb NOT NULL | `{target_field: {source_column, transform, default}}` |
| `options` | jsonb NOT NULL DEFAULT `'{}'` | date format, decimal separator, timezone assumption |
| `is_default` | boolean NOT NULL DEFAULT false | |
| `signature` | text NULL | hash of the sorted header list — enables auto-suggestion on next upload |
| `usage_count` | int NOT NULL DEFAULT 0 | |
| `last_used_at` | timestamptz NULL | |
| `created_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | |

`UNIQUE (organization_id, name)`, index `(organization_id, signature)`.

The `signature` column is the quiet quality-of-life feature: the second time a customer uploads
their monthly export, the header hash matches and the mapping step is pre-filled and
one-click.

---

## 11. System tables

### `background_jobs`

Full semantics in [09-background-jobs.md](09-background-jobs.md).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `organization_id` | uuid NULL FK → organizations `ON DELETE CASCADE` | NULL only for system maintenance jobs |
| `job_type` | text NOT NULL | registry key |
| `payload` | jsonb NOT NULL | validated by a per-type Pydantic model |
| `status` | enum `bg_job_status` NOT NULL | `queued`, `processing`, `completed`, `failed`, `cancelled` |
| `priority` | smallint NOT NULL DEFAULT 100 | lower runs first |
| `run_at` | timestamptz NOT NULL DEFAULT now() | scheduling + backoff |
| `attempts` | int NOT NULL DEFAULT 0 | |
| `max_attempts` | int NOT NULL DEFAULT 5 | |
| `locked_at` / `locked_by` | timestamptz / text NULL | worker identity |
| `heartbeat_at` | timestamptz NULL | stale-job recovery |
| `idempotency_key` | text NULL | |
| `cancel_requested` | boolean NOT NULL DEFAULT false | |
| `last_error` | text NULL | truncated, redacted |
| `enqueued_by_user_id` | uuid NULL FK → users `ON DELETE SET NULL` | audit attribution |
| `correlation_id` | text NULL | the originating `X-Request-Id` |
| `created_at` / `updated_at` / `completed_at` | | |

- `UNIQUE (job_type, idempotency_key) WHERE idempotency_key IS NOT NULL AND status <> 'failed'`
- **The claim index:** `(status, run_at, priority) WHERE status = 'queued'` — a partial index
  so the poll query touches only pending work, not the completed history.
- `(status, heartbeat_at) WHERE status = 'processing'` — stale recovery sweep.
- `(organization_id, job_type, created_at DESC)` — per-org job history UI.

### `audit_events`

Specified in [13-audit.md](13-audit.md).

| Column | Type |
| --- | --- |
| `id` | uuid PK |
| `organization_id` | uuid NOT NULL |
| `actor_type` | enum: `user`, `system`, `api_key` |
| `actor_user_id` | uuid NULL FK → users `ON DELETE SET NULL` |
| `actor_label` | text NULL — denormalized name, survives user deletion |
| `action` | text NOT NULL — `import.completed`, `candidate.confirmed`, … |
| `resource_type` / `resource_id` | text / uuid NULL |
| `summary` | text NOT NULL |
| `changes` | jsonb NULL — allowlisted before/after only |
| `request_id` | text NULL |
| `ip_hash` | bytea NULL |
| `occurred_at` | timestamptz NOT NULL |

Index `(organization_id, occurred_at DESC)`, `(organization_id, resource_type, resource_id)`,
`(organization_id, action, occurred_at DESC)`. **Append-only** — `UPDATE`/`DELETE` revoked
from the app role at the grant level, so the guarantee is enforced by Postgres, not convention.

### `rate_limit_counters`

| Column | Type |
| --- | --- |
| `bucket_key` | text NOT NULL |
| `window_start` | timestamptz NOT NULL |
| `count` | int NOT NULL DEFAULT 0 |

PK `(bucket_key, window_start)`. Rows older than 1 day purged hourly. Not tenant-scoped (keys
are namespaced by purpose and may be per-IP, pre-authentication).

### `outbound_emails`

| Column | Type |
| --- | --- |
| `id` | uuid PK |
| `organization_id` | uuid NULL |
| `recipient_hash` | bytea NOT NULL — `sha256(email + APP_SECRET)`; **the address itself is not stored** |
| `template_key` | text NOT NULL |
| `provider` / `provider_message_id` | text |
| `status` | enum: `queued`, `sent`, `failed` |
| `error_message` | text NULL |
| `created_at` / `sent_at` | timestamptz |

Enough to debug "did the invite send?" without building a copy of everyone's inbox.

---

## 12. Commercial tables

Detailed in [14-billing-and-entitlements.md](14-billing-and-entitlements.md).

| Table | Key columns |
| --- | --- |
| `plans` | `key` UNIQUE (`free`/`pro`/`business`), `name`, `monthly_price_amount`, `annual_price_amount`, `currency_code`, `is_public`, `is_active`, `sort_order` |
| `plan_entitlements` | `plan_id`, `entitlement_key`, `limit_value bigint NULL` (NULL = unlimited), `is_boolean`, `period` (`month`/`total`). UNIQUE `(plan_id, entitlement_key)` |
| `organization_subscriptions` | `organization_id` UNIQUE, `plan_id`, `status`, `billing_provider`, `provider_customer_id`, `provider_subscription_id`, `current_period_start/end`, `cancel_at_period_end`, `trial_ends_at` |
| `organization_entitlement_overrides` | `organization_id`, `entitlement_key`, `limit_value`, `reason`, `expires_at`. UNIQUE `(organization_id, entitlement_key)` |
| `usage_counters` | `organization_id`, `metric_key`, `period_start date`, `period_end date`, `value bigint`. UNIQUE `(organization_id, metric_key, period_start)` |
| `billing_events` | `provider`, `provider_event_id` UNIQUE, `event_type`, `payload jsonb`, `signature_verified boolean`, `status`, `processed_at`, `organization_id` NULL |

`billing_events.provider_event_id UNIQUE` is the webhook idempotency guarantee — a provider
retrying a delivery cannot double-apply it.

---

## 13. Delete behaviour

| Parent → child | Behaviour | Why |
| --- | --- | --- |
| `organizations` → everything tenant-owned | `CASCADE` | Org deletion must actually delete |
| `users` → `user_credentials`, `user_sessions`, tokens | `CASCADE` | |
| `users` → `organization_memberships` | `CASCADE` | |
| `users` → `rework_reviews.reviewed_by_user_id` | **`RESTRICT`** | Human truth may not be orphaned; user deletion anonymises instead ([12 §3](12-privacy-and-data-lifecycle.md)) |
| `users` → `audit_events.actor_user_id` | `SET NULL` | `actor_label` preserves who it was |
| `users` → `*.created_by_user_id` | `SET NULL` | |
| `import_batches` → `import_rows` | `CASCADE` | |
| `import_batches` → `jobs.last_import_batch_id` | `SET NULL` | Deleting an import must not delete jobs another import also touched — see below |
| `jobs` → `job_notes`, `job_line_items` | `CASCADE` | |
| `jobs` → `rework_candidates` (composite FK) | `CASCADE` | A candidate without both jobs is meaningless |
| `rework_candidates` → `candidate_signals`, `score_history`, `rework_reviews`, `cost_snapshots` | `CASCADE` | |
| `rework_categories` / `root_causes` → `rework_reviews` | **`RESTRICT`** | Deactivate, never delete, a category in use |
| `detection_rule_sets` → `detection_rules` | `CASCADE` | |
| `detection_rule_sets` → `rework_candidates.current_rule_set_id` | `SET NULL` | |
| `detection_runs` → `candidate_signals` | `CASCADE` | |

**"Delete an import" is a domain operation, not a cascade.** A job may have been created by
import #1 and updated by import #3. Deleting #3 must not delete the job. The service therefore:

1. deletes jobs whose `first_import_batch_id` is this batch **and** which no other batch has
   touched;
2. leaves jobs that predate this batch, nulling `last_import_batch_id`;
3. cascades candidates/signals for deleted jobs;
4. **warns the user, before confirming, if any affected candidate carries a human review**,
   and records the count in the audit event.

Step 4 is the layer-4 protection surfacing in the UI: deleting operational data can destroy
human decisions, so the user must be told exactly how many before they proceed.

---

## 14. Soft delete strategy

Soft delete is applied **selectively**, not universally, because a blanket `deleted_at`
silently breaks every unique constraint and every join.

**Soft-deleted** (`deleted_at timestamptz NULL`): `organizations`, `users`, `customers`,
`locations`, `equipment`, `technicians`, `jobs`, `import_batches`.

Rationale: these are user-visible entities where an accidental delete is costly and
undo is valuable, and where downstream derived data references them.

**Hard-deleted**: everything else — candidates, signals, embeddings, AI analyses, background
jobs, sessions, tokens, rate-limit rows. They are either derived (rebuildable) or ephemeral.

Rules when soft delete applies:

1. Every unique index becomes partial: `... WHERE deleted_at IS NULL`. Otherwise a customer
   cannot re-create a record they deleted.
2. Tenant repositories filter `deleted_at IS NULL` by default; retrieving deleted rows requires
   an explicit `include_deleted=True`.
3. RLS policies do **not** filter `deleted_at` — that is an application concern, and mixing it
   into the security policy makes the policy harder to reason about.
4. A purge job hard-deletes soft-deleted rows after the retention window
   ([12 §4](12-privacy-and-data-lifecycle.md)).

---

## 15. Scale: what changes at 1M jobs per org

Designed for ≤100k jobs/org. The upgrade path, so it stays a migration rather than a rewrite:

| Pressure | Change |
| --- | --- |
| `jobs` table > ~5M rows total | `PARTITION BY HASH (organization_id)` — the composite unique keys already lead with `organization_id`, so partitioning is compatible without redesign |
| Candidate generation slow | It is already blocked by `(organization_id, customer_id, service_date)`. Next step: generate incrementally for the import's date range only (already the default scope), then narrow blocking to `equipment_id` when present |
| `candidate_signals` dominant table | Already bounded by the 3-run retention policy; tighten to 1 run, or move the explanation text to a generated view |
| `import_rows` bloat | Already mitigated by the 90-day `raw_data` nulling policy |

None of these require changing a primary key, a foreign key, or a domain service. That is the
property the design is buying.
