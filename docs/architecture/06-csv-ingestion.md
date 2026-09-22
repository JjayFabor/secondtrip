# 06 — CSV Ingestion Architecture

The ingestion pipeline is the product's front door. If it mangles a customer's data or fails
opaquely on row 40,000 of 60,000, nothing downstream matters.

Two governing principles:

1. **Nothing is silently discarded.** Every row of every file lands in `import_rows` with a
   status and a structured issue list. A user can always answer "what happened to row 8,412?"
2. **Nothing is guessed.** A missing date, an unresolvable customer, an unparseable amount
   produces an *error on that row*, not an invented value. Fabricated data poisons detection
   invisibly, which is far worse than a visible rejection.

---

## 1. The flow

```
 1. POST /imports                     → import_batch (awaiting_file) + presigned R2 PUT URL
 2. Browser PUTs the file directly to R2                    (API never sees the bytes)
 3. POST /imports/{id}/uploaded       → verify object exists, size, sha256; enqueue profiling
 4. [job] import.profile              → encoding, delimiter, header, columns, sample rows
 5. GET  /imports/{id}/preview        → columns + samples + SUGGESTED mapping
 6. PUT  /imports/{id}/mapping        → user confirms/edits mapping; optionally save template
 7. POST /imports/{id}/validate       → [job] dry run over ALL rows; writes import_rows only
 8. GET  /imports/{id}/issues         → error report (paged) + downloadable CSV
 9. POST /imports/{id}/commit         → [job] import.process; writes operational data
10. [job] detection.run               → chained automatically on success
```

Steps 7 and 9 are separate on purpose. A user should be able to see "3,102 of 60,000 rows have
problems" **before** anything touches their operational data, and go fix their export. A
single-shot "upload and pray" import is how you lose a customer's trust in the first session.

---

## 2. Why the browser uploads straight to R2

A 50 MB CSV posted through the API would occupy a Render request worker for the duration of
the transfer, and Vercel's route handlers cap request bodies at 4.5 MB. A presigned `PUT`
removes the API from the data path entirely.

```python
key = f"orgs/{org_id}/imports/{import_id}/source.csv"   # no user input anywhere in the key
url = storage.signed_upload_url(
    key=key,
    content_type="text/csv",
    max_bytes=entitlements.limit(org, "import_file_bytes"),
    expires_in=900,
)
```

Upload controls (see [10-storage.md §4](10-storage.md)):

- `Content-Type` is pinned in the signature.
- The browser rejects a file above the returned plan limit before transfer. Because R2 does not
  support presigned POST policies, the API authoritatively verifies `HEAD` and streamed bytes
  after PUT, immediately deleting and rejecting an oversized object.
- The key is built exclusively from server-generated UUIDs. The user's filename is stored in
  `import_batches.original_filename` for display and **never** appears in a key — that is the
  path-traversal and key-collision mitigation.
- The URL expires in 15 minutes.

On `POST /imports/{id}/uploaded` the backend independently `HEAD`s the object to confirm
existence and true size, and streams it once to compute `file_sha256`. **Client-reported size
is never trusted.**

---

## 3. Profiling (`import.profile`)

Reads only the first ~1 MB.

| Step | Approach | Failure behaviour |
| --- | --- | --- |
| Encoding | `charset-normalizer` best guess; strip UTF-8/UTF-16 BOM | Unclear → default `utf-8` with `errors="replace"`, flag `ENCODING_UNCERTAIN` on the batch, let the user override in the preview |
| Delimiter | `csv.Sniffer` over the first 64 KB; fall back to counting `,` `;` `\t` `|` across the first 20 lines and picking the most consistent | Ambiguous → default `,` and flag it as user-overridable |
| Header | `Sniffer.has_header`, plus a heuristic: does row 1 parse as dates/numbers? | Assume header present; user can toggle |
| Columns | Name, ordinal, 5 sample values, inferred type | Duplicate header names get suffixed `name`, `name_2` |
| Row count | Cheap line count over the streamed object | Approximate is fine for the progress bar |

Everything detected is **a default the user can override**, never a silent decision. All of it
is persisted on `import_batches` so the mapping UI is a pure read.

**Excel-exported CSVs** are the common real-world case and deserve explicit handling:
UTF-16LE with BOM and `\t` delimiters, `\r\n` line endings, and thousands separators in
numbers. The profiler must recognise all three. If a user uploads an actual `.xlsx`, detect the
`PK\x03\x04` magic bytes and return a clear "this is an Excel workbook, please export as CSV"
error rather than a parse failure.

---

## 4. Column mapping

### Target field catalogue

| Target field | Required | Type | Notes |
| --- | --- | --- | --- |
| `external_job_id` | ⚠️ strongly recommended | text | Without it, dedup falls back to a natural-key hash |
| `service_date` | ✅ **required** | date/datetime | No usable date ⇒ row error. Anchors all time windows |
| `customer_name` | ✅ required¹ | text | |
| `customer_external_id` | ○ | text | |
| `customer_phone` | ○ | text | Best identity key after an external ID |
| `customer_email` | ○ | text | |
| `address_line1`, `city`, `region`, `postal_code` | ○ | text | Together form the location key |
| `location_external_id` | ○ | text | |
| `equipment_serial` | ○ | text | Strongest equipment identity |
| `equipment_manufacturer`, `equipment_model`, `equipment_type` | ○ | text | |
| `equipment_external_id` | ○ | text | |
| `technician_name` | ○ | text | |
| `technician_external_id`, `technician_code` | ○ | text | |
| `service_category`, `job_type` | ○ | text | Mapped to `service_categories` |
| `job_status` | ○ | text | Mapped via a value-mapping table to `job_status` |
| `summary`, `description` | ○ | text | |
| `symptoms`, `diagnosis`, `resolution` | ○ | text | **Highest value for detection quality** |
| `technician_notes` | ○ | text | Becomes a `job_notes` row |
| `invoice_number` | ○ | text | |
| `revenue_amount`, `parts_amount`, `labor_amount` | ○ | money | |
| `duration_minutes` | ○ | int | Falls back to the cost model default |
| `is_warranty` | ○ | boolean | Accepts `Y/N`, `true/false`, `1/0`, `Warranty` |
| `warranty_reference` | ○ | text | |
| `scheduled_at`, `started_at`, `completed_at` | ○ | datetime | |

¹ `customer_name` is required unless `customer_external_id` is mapped.

**Minimum viable import:** `service_date` + (`customer_name` | `customer_external_id`). That
alone produces candidates on the `same_customer` + `days_between` signals. Everything else
increases precision, and the UI should say so explicitly — a mapping screen that shows
"mapping `equipment_serial` would improve detection accuracy significantly" converts far
better than one that just lists optional fields.

### Mapping document

```json
{
  "version": 1,
  "fields": {
    "service_date":  {"source_column": "Completed Date", "transform": {"type": "date", "format": "%m/%d/%Y", "timezone": "America/Chicago"}},
    "customer_name": {"source_column": "Client Name"},
    "revenue_amount":{"source_column": "Invoice Total", "transform": {"type": "money", "decimal_separator": ".", "thousands_separator": ","}},
    "is_warranty":   {"source_column": "Warranty?", "transform": {"type": "boolean", "true_values": ["Y", "YES", "WARRANTY"]}},
    "job_status":    {"source_column": "Status", "transform": {"type": "value_map", "map": {"Complete": "completed", "Closed": "completed", "Cancelled": "cancelled"}}}
  },
  "retain_unmapped": ["Lead Source", "Zone"],
  "skip_rows_where": [{"column": "Status", "operator": "equals", "value": "Estimate"}]
}
```

- `retain_unmapped` columns are preserved in `jobs.extra_fields`, so a customer's own fields
  are not lost and can be mapped properly later without a re-upload.
- `skip_rows_where` handles the common "my export includes estimates and we only want
  completed jobs" case. Skipped rows are recorded as `skipped_filtered`, not dropped.

### Auto-suggestion

Three strategies, in order:

1. **Template match** — `sha256(sorted(lowercased header names))` matched against
   `import_column_mappings.signature`. An exact match pre-fills everything.
2. **Synonym dictionary** — a static `dict[target_field, set[str]]` in
   `imports/mapping/synonyms.py`:
   ```python
   "customer_name": {"customer", "customer name", "client", "client name", "account name",
                     "bill to", "customer_full_name", "cust name"},
   ```
   Matched on a normalized header (lowercase, strip non-alphanumerics).
3. **Fuzzy fallback** — `difflib.SequenceMatcher` ≥ 0.82 against synonyms, plus a type check
   against the sampled values (a column suggested as `service_date` must have samples that
   parse as dates).

Suggestions are **always presented for confirmation**, never auto-applied. Each carries a
confidence indicator so a user knows which to check.

---

## 5. Normalization rules

Implemented once in `imports/normalization/`, pure functions, heavily unit-tested. These
functions are the single highest-value test target in the codebase
([19-testing-strategy.md §3](19-testing-strategy.md)).

### Dates

Order of attempts:
1. Explicit format from the mapping (best — offered in the UI once a column is chosen).
2. ISO 8601.
3. An ordered list of common formats, **disambiguated by a batch-level scan**: sample 200
   non-empty values; if any has a first component > 12, the file is `DD/MM`; if any has a
   second component > 12, it is `MM/DD`; if neither, ask the user.
4. Failure → `INVALID_DATE` row error.

**`03/04/2026` is genuinely ambiguous** and guessing is how you silently shift a customer's
entire dataset by months. The batch-level scan resolves most files; the remainder go to the
user. Never guess per-row.

Naive datetimes are interpreted in the **organization's timezone**, then stored as UTC.
`service_date` is the org-local calendar date.

### Money

```
strip currency symbols and whitespace
detect parentheses negatives:  (1,234.56) → -1234.56
apply the mapping's separators; if absent, infer:
    last separator followed by exactly 2 digits and appearing once → decimal separator
    "1.234,56" → European;  "1,234.56" → US
parse with Decimal(str)      ← never float()
reject > 2 decimal places with WARNING (round half-up) rather than an error
empty / "-" / "N/A" → NULL, not 0
```

**`NULL` and `0` must not be conflated.** `zero_value_followup` is a detection signal; a
missing invoice figure is not evidence of a free callback.

### Booleans

`{"y","yes","true","t","1","x","warranty"}` → true; `{"n","no","false","f","0",""}` → false;
anything else → warning + false, with the raw value preserved in the issue.

### Text

Trim, collapse internal whitespace, normalize Unicode to NFC, strip control characters except
`\n`/`\t`, cap at 32 KB per field (`FIELD_TOO_LONG` warning, truncated with a marker).
**No HTML stripping and no sanitisation at ingest** — the raw text is stored as data, and
escaping happens at the point of rendering. Sanitising on the way in destroys legitimate
content (`<` in "temp < 60F") and creates a false sense of safety.

### Names & phones

- `normalized_name`: casefold, strip punctuation, collapse whitespace, remove trailing legal
  suffixes (`LLC`, `Inc`, `Ltd`).
- `phone_e164`: `phonenumbers` library with the org's country as the default region; failure
  leaves `phone_e164` NULL and keeps `phone_raw`.

---

## 6. Entity resolution during import

Per row, in order — each step is an upsert keyed on the natural key from
[04-data-model.md §4.4](04-data-model.md):

```
1. customer   ← required; unresolvable ⇒ ROW ERROR (never invented)
2. location   ← optional; needs at least address_line1 + postal_code, or an external ID
3. equipment  ← optional; needs a serial, an external ID, or (location + make + model)
4. technician ← optional
5. service_category ← lookup or create by normalized label
6. job        ← upsert
7. job_notes, job_line_items ← replace-by-hash
```

Upserts use `INSERT ... ON CONFLICT (organization_id, natural_key_hash) WHERE deleted_at IS
NULL DO UPDATE` and are **enriching, not overwriting**: a later row that supplies a phone
number for a customer fills the blank, but a later row with a *blank* phone does not erase an
existing one. `COALESCE(EXCLUDED.col, table.col)` is the pattern; the exception is
explicitly-mapped fields on `jobs`, where a re-import is meant to be authoritative.

**Equipment must never be invented** (rule 4 of §4.4). If a job has no equipment identifier,
`jobs.equipment_id` stays NULL and the `same_equipment` signal reports "not evaluable" for
pairs involving it — which is materially different from "evaluated, did not match."

---

## 7. Idempotency

Four independent layers, because re-importing is normal user behaviour, not an edge case:

| Level | Mechanism | Effect |
| --- | --- | --- |
| **File** | `UNIQUE (organization_id, file_sha256)` | Re-uploading identical bytes is refused with "you already imported this on <date>", overridable with an explicit confirmation |
| **Row (in-file)** | `import_rows.row_hash` | Exact duplicate rows within one file → `skipped_duplicate` |
| **Job** | `UNIQUE (organization_id, source_system_id, external_id)` or `UNIQUE (organization_id, natural_key_hash)` | Re-import **updates** the existing job. `created_jobs` vs `updated_jobs` counters distinguish the two |
| **Request** | `Idempotency-Key` header on `POST /commit` | A retried commit returns the original result rather than enqueuing a second processing job |

The `natural_key_hash` for a job, when no external ID exists:

```
sha256(org_id | customer_key | service_date | normalized(summary or description)[:200] | invoice_number)
```

Chosen because these five together are stable across re-exports of the same source data while
being distinct between two genuinely different visits on the same day. It is imperfect — two
identical maintenance visits on one day at one site would collide — so the row is flagged
`POSSIBLE_DUPLICATE` (warning, still imported as an update) rather than silently merged, and
the UI surfaces it.

**Processing is resumable.** `import_batches.processed_rows` is checkpointed after each chunk
of 500 rows within the same transaction that writes those rows. A crashed or redeployed worker
restarts the job and skips to `processed_rows + 1`. Combined with row-level upserts, replaying
a chunk is harmless.

---

## 8. Error handling & reporting

### Severity model

| Severity | Meaning | Effect on the row |
| --- | --- | --- |
| `error` | The row cannot become a valid job | Not imported; `status = 'error'` |
| `warning` | Imported, but something was assumed or lost | Imported; `status = 'warning'` |
| `info` | Noted, no impact | Imported normally |

### Error code catalogue

Stable machine codes so the frontend can render specific guidance and remediation links.

| Code | Severity | Trigger |
| --- | --- | --- |
| `MISSING_REQUIRED_FIELD` | error | A required target field is empty |
| `INVALID_DATE` | error | Date unparseable after all strategies |
| `AMBIGUOUS_DATE_FORMAT` | error | Batch-level scan could not disambiguate |
| `DATE_OUT_OF_RANGE` | error | Before 1990 or more than 1 year in the future |
| `UNRESOLVABLE_CUSTOMER` | error | No external ID, phone, or name |
| `INVALID_NUMBER` | error | Money/int column unparseable |
| `NEGATIVE_AMOUNT` | warning | Negative revenue — kept (credits are real) but flagged |
| `TOO_MANY_COLUMNS` / `TOO_FEW_COLUMNS` | error | Field count ≠ header count |
| `FIELD_TOO_LONG` | warning | > 32 KB, truncated |
| `UNKNOWN_ENUM_VALUE` | warning | Unmapped `job_status`; falls back to `unknown` |
| `DUPLICATE_ROW_IN_FILE` | info | Identical `row_hash` already seen |
| `POSSIBLE_DUPLICATE` | warning | Natural key collided with an existing job |
| `ENCODING_REPLACEMENT` | warning | Undecodable bytes replaced |
| `EQUIPMENT_NOT_RESOLVED` | info | No equipment identifier; detection precision reduced |
| `ROW_SKIPPED_BY_FILTER` | info | Matched `skip_rows_where` |

### The error report CSV — and formula injection

Downloadable from `GET /imports/{id}/issues/export`, generated into R2, served by signed URL:

```csv
row_number,status,error_code,field,message,raw_value
8412,error,INVALID_DATE,service_date,"Could not parse date","31/13/2026"
```

**Every cell is escaped against CSV formula injection before writing.** A value beginning with
`=`, `+`, `-`, `@`, tab, or CR is prefixed with a single quote. This matters acutely here
because the `raw_value` column echoes attacker-controlled content from the uploaded file
straight back into a file the user will open in Excel. The escaping helper lives in
`shared/csv_safety.py` and **must** be used by every export path in the system
([11-security-threat-model.md §5](11-security-threat-model.md)).

---

## 9. Limits, cancellation, and failure

### Limits (entitlement-driven, with hard ceilings)

| Limit | Free | Pro | Business | Hard ceiling |
| --- | --- | --- | --- | --- |
| File size | 5 MB | 50 MB | 200 MB | 500 MB |
| Rows per file | 10k | 250k | 1M | 2M |
| Imports per month | 3 | 50 | unlimited | — |
| Concurrent processing imports | 1 | 2 | 3 | 5 |
| Columns | 200 | 200 | 200 | 200 |
| Bytes per field | 32 KB | 32 KB | 32 KB | 64 KB |

Rows and file size are checked **while streaming**, aborting the moment a limit is crossed —
never after buffering the whole file. `csv.field_size_limit` is set explicitly; the default
allows a single field to consume a great deal of memory.

Full validation streams the object into an anonymous, disk-backed temporary file while these
limits are enforced. The worker can then scan up to 200 date values and restart parsing from
the beginning without retaining the source in memory or downloading it twice. Rows are parsed
and persisted in bounded chunks; the temporary file is discarded when the handler exits.

The 500-row checkpoint is also the performance unit: identity keys are deduplicated in memory,
advisory locks are acquired in a stable batch, and owning module services perform bounded bulk
upserts. `make perf-import` exercises this exact path with the generated `hvac-v2` fixture. Its
timing starts before independent object verification and includes profile, mapping, full
validation, commit, queue polling, and processing; direct browser upload time is excluded.

Compressed uploads are **not accepted in V1**. Accepting gzip means either trusting a
decompressed-size header or implementing a decompression-bomb guard, and the feature is worth
neither.

### Cancellation

`POST /imports/{id}/cancel` sets `cancel_requested_at`. The worker checks the flag at every
500-row checkpoint and, if set, stops, sets `status = 'cancelled'`, and leaves already-imported
rows in place — with the count clearly reported. A partially-imported batch is a legitimate,
inspectable state; the user can delete the batch to roll it back
([04 §13](04-data-model.md)).

### Failure

- **Row failure** → record the issue, continue. Never aborts the batch.
- **Chunk failure** (DB error) → the chunk's transaction rolls back; the job retries with
  backoff from the last checkpoint ([09-background-jobs.md](09-background-jobs.md)).
- **Batch failure** (file gone, undecodable, exhausted retries) → `status = 'failed'`,
  `failure_reason` set, user notified by email.
- **Poison rows**: if the same chunk fails 3 times, fall back to processing it row-by-row so a
  single malformed row is isolated as a row error instead of blocking 499 healthy rows.

---

## 10. Module layout

```
backend/app/modules/imports/
├── router.py                  # HTTP surface
├── schemas.py                 # Pydantic request/response models
├── models.py                  # import_batches, import_rows, import_column_mappings
├── repository.py
├── service.py                 # orchestration, status transitions, entitlement checks
├── profiling/
│   ├── encoding.py            # charset detection, BOM handling
│   ├── dialect.py             # delimiter/header sniffing
│   └── profiler.py
├── mapping/
│   ├── catalogue.py           # target field definitions + requirements
│   ├── synonyms.py            # the synonym dictionary
│   ├── suggester.py           # template → synonym → fuzzy
│   └── document.py            # ColumnMapping pydantic model + validation
├── normalization/
│   ├── dates.py
│   ├── money.py
│   ├── text.py
│   ├── booleans.py
│   ├── phones.py
│   └── identity.py            # natural key derivation  ← shared with future integrations
├── resolution/
│   ├── customers.py
│   ├── locations.py
│   ├── equipment.py
│   └── technicians.py
├── processing/
│   ├── reader.py              # streaming row reader with limits
│   ├── validator.py           # dry run
│   ├── processor.py           # chunked commit + checkpointing
│   └── errors.py              # the code catalogue
└── reporting/
    └── error_report.py        # CSV generation with formula escaping
```

`normalization/` and `resolution/` contain **no HTTP and no CSV concepts**. They operate on a
`SourceRecord` dataclass. This is the boundary that lets a future ServiceTitan integration
reuse the entire normalization and entity-resolution stack by writing only a new adapter that
produces `SourceRecord`s — which is the whole point of designing the boundary now.
