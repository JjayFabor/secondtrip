# 05 — Entity Relationship Diagrams

Four diagrams instead of one, because a single ERD across ~44 tables is unreadable and
therefore useless. Column lists are abridged to keys and identity-bearing fields; the complete
column specification is [04-data-model.md](04-data-model.md).

Legend: `PK` primary key, `FK` foreign key, `UK` participates in a unique constraint.

---

## 1. Identity & tenancy

```mermaid
erDiagram
    USERS ||--o| USER_CREDENTIALS : "authenticates with"
    USERS ||--o{ USER_SESSIONS : "holds"
    USERS ||--o{ EMAIL_VERIFICATION_TOKENS : "issued"
    USERS ||--o{ PASSWORD_RESET_TOKENS : "issued"
    USERS ||--o{ ORGANIZATION_MEMBERSHIPS : "member via"
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERSHIPS : "grants"
    ORGANIZATIONS ||--o{ ORGANIZATION_INVITATIONS : "sends"
    USERS ||--o{ ORGANIZATION_INVITATIONS : "invited by"

    USERS {
        uuid id PK
        citext email UK
        text full_name
        enum status
        timestamptz email_verified_at
        timestamptz deleted_at
    }
    USER_CREDENTIALS {
        uuid user_id PK "FK to users"
        text password_hash "argon2id"
        int failed_attempt_count
        timestamptz locked_until
    }
    USER_SESSIONS {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK "sha256 of raw token"
        timestamptz expires_at
        timestamptz revoked_at
    }
    EMAIL_VERIFICATION_TOKENS {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK
        timestamptz consumed_at
    }
    PASSWORD_RESET_TOKENS {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK
        timestamptz consumed_at
    }
    ORGANIZATIONS {
        uuid id PK
        text name
        citext slug UK
        text timezone "IANA"
        char currency_code
        text industry_key "seed data only"
        enum status
        timestamptz deleted_at
    }
    ORGANIZATION_MEMBERSHIPS {
        uuid id PK
        uuid organization_id FK "UK with user_id"
        uuid user_id FK
        enum role "owner admin manager member"
        timestamptz revoked_at
    }
    ORGANIZATION_INVITATIONS {
        uuid id PK
        uuid organization_id FK
        citext email
        enum role "granted by the token"
        bytea token_hash UK
        timestamptz expires_at
        timestamptz accepted_at
    }
```

The membership table is the **only** bridge between a person and tenant data. Note that
`ORGANIZATION_INVITATIONS` carries the role: accepting a token grants what the row says, never
what the request body says.

---

## 2. Operational data & ingestion

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ CUSTOMERS : owns
    ORGANIZATIONS ||--o{ TECHNICIANS : owns
    ORGANIZATIONS ||--o{ SERVICE_CATEGORIES : owns
    ORGANIZATIONS ||--o{ SOURCE_SYSTEMS : owns
    ORGANIZATIONS ||--o{ IMPORT_BATCHES : owns
    ORGANIZATIONS ||--o{ JOBS : owns

    CUSTOMERS ||--o{ LOCATIONS : "serviced at"
    CUSTOMERS ||--o{ EQUIPMENT : "owns asset"
    LOCATIONS ||--o{ EQUIPMENT : "installed at"

    CUSTOMERS ||--o{ JOBS : "requested"
    LOCATIONS ||--o{ JOBS : "performed at"
    EQUIPMENT ||--o{ JOBS : "serviced in"
    TECHNICIANS ||--o{ JOBS : "performed by"
    SERVICE_CATEGORIES ||--o{ JOBS : classifies
    SOURCE_SYSTEMS ||--o{ JOBS : "originated from"

    JOBS ||--o{ JOB_NOTES : "annotated by"
    JOBS ||--o{ JOB_LINE_ITEMS : "billed as"

    IMPORT_BATCHES ||--o{ IMPORT_ROWS : contains
    IMPORT_ROWS |o--o| JOBS : produced
    IMPORT_BATCHES |o--o| IMPORT_COLUMN_MAPPINGS : "used template"
    SOURCE_SYSTEMS ||--o{ IMPORT_BATCHES : "feeds"

    CUSTOMERS {
        uuid id PK
        uuid organization_id FK
        text external_id "UK with source_system"
        bytea natural_key_hash UK
        text display_name
        text normalized_name
        text phone_e164 "strongest match key"
        timestamptz deleted_at
    }
    LOCATIONS {
        uuid id PK
        uuid organization_id FK
        uuid customer_id FK
        bytea address_hash "UK with customer"
        text address_line1
        text postal_code
    }
    EQUIPMENT {
        uuid id PK
        uuid organization_id FK
        uuid customer_id FK
        uuid location_id FK
        bytea natural_key_hash UK
        text serial_number
        text manufacturer
        text model
        date warranty_expires_on
    }
    TECHNICIANS {
        uuid id PK
        uuid organization_id FK
        bytea natural_key_hash UK
        text full_name
        numeric hourly_cost_amount "overrides cost model"
        boolean is_active
    }
    SERVICE_CATEGORIES {
        uuid id PK
        uuid organization_id FK
        text key UK
        text label
        uuid parent_id FK
    }
    SOURCE_SYSTEMS {
        uuid id PK
        uuid organization_id FK
        enum kind "csv_upload api servicetitan"
        text name UK
    }
    JOBS {
        uuid id PK
        uuid organization_id FK "UK with id"
        uuid source_system_id FK
        text external_id "UK with source_system"
        bytea natural_key_hash UK
        uuid customer_id FK
        uuid location_id FK
        uuid equipment_id FK
        uuid technician_id FK
        uuid service_category_id FK
        date service_date "org-local NOT NULL"
        timestamptz started_at
        enum status
        text symptoms_text
        text diagnosis_text
        text resolution_text
        numeric revenue_amount
        boolean is_warranty
        boolean is_no_charge
        tsvector search_document
        timestamptz deleted_at
    }
    JOB_NOTES {
        uuid id PK
        uuid organization_id FK
        uuid job_id FK
        text note_type
        text body "untrusted content"
        bytea content_hash UK
    }
    JOB_LINE_ITEMS {
        uuid id PK
        uuid organization_id FK
        uuid job_id FK
        enum kind "part labor fee"
        text code "repeat-failure signal"
        numeric quantity
        numeric total_amount
    }
    IMPORT_BATCHES {
        uuid id PK
        uuid organization_id FK
        uuid source_system_id FK
        enum status
        text original_filename "display only"
        text storage_key "server-generated"
        bytea file_sha256 UK
        jsonb detected_columns
        jsonb mapping "frozen at commit"
        int total_rows
        int processed_rows
        text error_report_key
        timestamptz cancel_requested_at
    }
    IMPORT_ROWS {
        uuid id PK
        uuid organization_id FK
        uuid import_batch_id FK
        int row_number UK
        jsonb raw_data "layer 1 immutable"
        bytea row_hash
        enum status
        jsonb issues "never silently discarded"
        uuid job_id FK
    }
    IMPORT_COLUMN_MAPPINGS {
        uuid id PK
        uuid organization_id FK
        text name UK
        jsonb mapping
        text signature "header hash for auto-suggest"
        int usage_count
    }
```

---

## 3. Detection, review & cost

The spine of the product. Note the deliberate separation: everything left of
`REWORK_CANDIDATES` is machine-generated and disposable; `REWORK_REVIEWS` and its category /
root-cause references are human truth and are never machine-written.

```mermaid
erDiagram
    DETECTION_SIGNAL_DEFINITIONS ||--o{ DETECTION_RULES : "configured by"
    ORGANIZATIONS ||--o{ DETECTION_RULE_SETS : owns
    DETECTION_RULE_SETS ||--o{ DETECTION_RULES : contains
    DETECTION_RULE_SETS ||--o{ DETECTION_RUNS : "scored with"
    DETECTION_RUNS ||--o{ CANDIDATE_SIGNALS : produced
    DETECTION_RUNS ||--o{ CANDIDATE_SCORE_HISTORY : recorded

    JOBS ||--o{ REWORK_CANDIDATES : "prior job"
    JOBS ||--o{ REWORK_CANDIDATES : "followup job"
    REWORK_CANDIDATES ||--o{ CANDIDATE_SIGNALS : "explained by"
    REWORK_CANDIDATES ||--o{ CANDIDATE_SCORE_HISTORY : "scored over time"
    REWORK_CANDIDATES ||--o{ REWORK_REVIEWS : "judged by human"
    REWORK_CANDIDATES ||--o{ REWORK_COST_SNAPSHOTS : "costed as"

    REWORK_CATEGORIES ||--o{ REWORK_REVIEWS : classifies
    ROOT_CAUSES ||--o{ REWORK_REVIEWS : "attributed to"
    USERS ||--o{ REWORK_REVIEWS : decided
    REWORK_REVIEWS ||--o| REWORK_REVIEWS : "superseded by"
    ORGANIZATION_COST_MODELS ||--o{ REWORK_COST_SNAPSHOTS : "priced with"

    DETECTION_SIGNAL_DEFINITIONS {
        text key PK "global not tenant"
        text label
        enum value_type
        numeric default_weight
    }
    DETECTION_RULE_SETS {
        uuid id PK
        uuid organization_id FK
        int version_number UK "immutable version"
        boolean is_active "one per org"
        int window_days
        numeric min_score_to_surface
        int max_followups_per_job
    }
    DETECTION_RULES {
        uuid id PK
        uuid organization_id FK
        uuid rule_set_id FK
        text signal_key FK "UK with rule_set"
        enum kind "additive multiplier gate veto"
        numeric weight
        jsonb params
        boolean is_enabled
    }
    DETECTION_RUNS {
        uuid id PK
        uuid organization_id FK
        uuid rule_set_id FK
        enum trigger
        jsonb scope
        enum status
        bigint pairs_evaluated
        int candidates_created
    }
    REWORK_CANDIDATES {
        uuid id PK "stable across re-runs"
        uuid organization_id FK
        uuid prior_job_id FK "UK with followup"
        uuid followup_job_id FK
        uuid customer_id FK
        uuid equipment_id FK
        int days_between
        numeric current_normalized_score
        enum score_band
        boolean is_suppressed
        enum suppression_reason "signal_veto out_of_window"
        text suppressed_by_signal_key "veto only"
        enum workflow_status
        uuid current_rule_set_id FK
        uuid current_detection_run_id FK
    }
    CANDIDATE_SIGNALS {
        uuid id PK
        uuid organization_id FK
        uuid candidate_id FK
        uuid detection_run_id FK
        text signal_key "UK with candidate and run"
        enum outcome "matched not_matched not_evaluable"
        numeric strength
        jsonb raw_value
        numeric weight_applied
        numeric contribution
        text explanation "human sentence"
    }
    CANDIDATE_SCORE_HISTORY {
        uuid id PK
        uuid candidate_id FK
        uuid detection_run_id FK "UK with candidate"
        numeric normalized_score
        boolean is_suppressed
    }
    REWORK_CATEGORIES {
        uuid id PK
        uuid organization_id FK
        text key UK
        text label
        enum outcome "rework not_rework uncertain"
        boolean counts_toward_cost
        boolean is_active
    }
    ROOT_CAUSES {
        uuid id PK
        uuid organization_id FK
        text key UK
        text label
        uuid parent_id FK
    }
    REWORK_REVIEWS {
        uuid id PK
        uuid organization_id FK
        uuid candidate_id FK "UK where not superseded"
        enum decision "confirmed rejected uncertain"
        uuid category_id FK "RESTRICT"
        uuid root_cause_id FK "RESTRICT"
        uuid reviewed_by_user_id FK "RESTRICT"
        numeric score_at_review "what the machine claimed"
        text note
        timestamptz decided_at
        uuid superseded_by_review_id FK
    }
    ORGANIZATION_COST_MODELS {
        uuid id PK
        uuid organization_id FK
        int version_number UK
        boolean is_active "one per org"
        numeric technician_hourly_cost
        numeric vehicle_dispatch_cost
        numeric overhead_per_visit
        numeric opportunity_cost_per_hour
        int default_visit_duration_minutes
        jsonb custom_factors
    }
    REWORK_COST_SNAPSHOTS {
        uuid id PK
        uuid organization_id FK
        uuid candidate_id FK "UK with cost_model"
        uuid review_id FK
        uuid cost_model_id FK
        numeric total_cost
        jsonb inputs "exact values used"
    }
```

Two relationships to read carefully:

- `JOBS ||--o{ REWORK_CANDIDATES` appears **twice** — once as the prior visit, once as the
  follow-up. A single job is routinely both: the follow-up of one pair and the prior of the
  next.
- `REWORK_REVIEWS ||--o| REWORK_REVIEWS` is the reclassification chain. Rows are never updated;
  a changed decision inserts a new row and stamps `superseded_by_review_id` on the old one.

---

## 4. System & commercial

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ BACKGROUND_JOBS : "queues work for"
    ORGANIZATIONS ||--o{ AUDIT_EVENTS : records
    ORGANIZATIONS ||--o| ORGANIZATION_SUBSCRIPTIONS : subscribes
    ORGANIZATIONS ||--o{ ORGANIZATION_ENTITLEMENT_OVERRIDES : "granted"
    ORGANIZATIONS ||--o{ USAGE_COUNTERS : meters
    ORGANIZATIONS ||--o{ BILLING_EVENTS : "receives"
    PLANS ||--o{ PLAN_ENTITLEMENTS : grants
    PLANS ||--o{ ORGANIZATION_SUBSCRIPTIONS : "subscribed to"
    USERS ||--o{ AUDIT_EVENTS : "acted as"
    USERS ||--o{ BACKGROUND_JOBS : enqueued
    BACKGROUND_JOBS ||--o| DETECTION_RUNS : "executes"
    BACKGROUND_JOBS ||--o| IMPORT_BATCHES : "processes"

    BACKGROUND_JOBS {
        uuid id PK
        uuid organization_id FK "null only for system jobs"
        text job_type
        jsonb payload
        enum status "queued processing completed failed cancelled"
        smallint priority
        timestamptz run_at "backoff schedule"
        int attempts
        int max_attempts
        timestamptz locked_at
        text locked_by
        timestamptz heartbeat_at "stale recovery"
        text idempotency_key UK
        boolean cancel_requested
        text correlation_id
    }
    AUDIT_EVENTS {
        uuid id PK "append-only"
        uuid organization_id FK
        enum actor_type "user system api_key"
        uuid actor_user_id FK
        text actor_label "survives user deletion"
        text action
        text resource_type
        uuid resource_id
        text summary
        jsonb changes "allowlisted fields only"
        text request_id
        bytea ip_hash
        timestamptz occurred_at
    }
    PLANS {
        uuid id PK
        text key UK "free pro business"
        text name
        numeric monthly_price_amount
        boolean is_public
    }
    PLAN_ENTITLEMENTS {
        uuid id PK
        uuid plan_id FK
        text entitlement_key "UK with plan"
        bigint limit_value "null means unlimited"
        boolean is_boolean
        enum period "month total"
    }
    ORGANIZATION_SUBSCRIPTIONS {
        uuid id PK
        uuid organization_id FK UK
        uuid plan_id FK
        enum status "trialing active past_due canceled"
        text billing_provider
        text provider_customer_id
        text provider_subscription_id
        timestamptz current_period_end
        boolean cancel_at_period_end
    }
    ORGANIZATION_ENTITLEMENT_OVERRIDES {
        uuid id PK
        uuid organization_id FK
        text entitlement_key "UK with org"
        bigint limit_value
        text reason
        timestamptz expires_at
    }
    USAGE_COUNTERS {
        uuid id PK
        uuid organization_id FK
        text metric_key
        date period_start "UK with org and metric"
        date period_end
        bigint value
    }
    BILLING_EVENTS {
        uuid id PK
        uuid organization_id FK
        text provider
        text provider_event_id UK "webhook idempotency"
        text event_type
        jsonb payload
        boolean signature_verified
        timestamptz processed_at
    }
```

---

## 5. Cross-diagram summary

| Relationship | Cardinality | Enforced by |
| --- | --- | --- |
| user ↔ organization | many-to-many | `organization_memberships`, unique on `(org, user)` where active |
| organization → all business data | 1-to-many | `organization_id NOT NULL` + RLS |
| job pair → candidate | 1-to-1 per ordered pair | `UNIQUE (organization_id, prior_job_id, followup_job_id)` |
| candidate → current review | 1-to-at-most-1 | `UNIQUE (candidate_id) WHERE superseded_by_review_id IS NULL` |
| candidate → signals | 1-to-many per run | `UNIQUE (candidate_id, detection_run_id, signal_key)` |
| organization → active rule set | 1-to-1 | `UNIQUE (organization_id) WHERE is_active` |
| organization → active cost model | 1-to-1 | `UNIQUE (organization_id) WHERE is_active` |
| organization → subscription | 1-to-1 | `UNIQUE (organization_id)` |
| candidate's jobs ↔ candidate's org | same-tenant guarantee | composite FK on `(organization_id, job_id)` |
