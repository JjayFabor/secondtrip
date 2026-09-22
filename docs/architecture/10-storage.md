# 10 — Object Storage

---

## 1. The protocol

```python
# app/providers/storage/base.py

class StorageProvider(Protocol):
    async def upload(
        self, key: str, data: bytes | AsyncIterator[bytes], *,
        content_type: str, metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...

    async def download(self, key: str) -> AsyncIterator[bytes]: ...

    async def delete(self, key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int: ...

    async def head(self, key: str) -> ObjectMetadata | None: ...

    async def signed_download_url(self, key: str, *, expires_in: int = 300,
                                  download_filename: str | None = None) -> str: ...

    async def signed_upload_url(self, key: str, *, content_type: str, max_bytes: int,
                                expires_in: int = 900) -> PresignedUpload: ...
```

Two additions beyond the brief's four methods, each justified:

- **`delete_prefix`** — organization deletion must remove every object under
  `orgs/{org_id}/`. Without it, that becomes list-and-loop in domain code, which is exactly
  the provider detail the abstraction exists to hide.
- **`head`** — the API must independently verify size and existence after a direct-to-R2
  upload. Client-reported size is not evidence.

Implementations: `R2StorageProvider` (S3-compatible, `aioboto3`), `LocalStorageProvider`
(filesystem + a signed-URL route, for local development without R2 credentials), and
`InMemoryStorageProvider` for tests.

`StoredObject`, `ObjectMetadata`, and `PresignedUpload` are our dataclasses. No `boto3` type
crosses the boundary, and `boto3`/`aioboto3` may be imported only under
`app/providers/storage/r2/`.

---

## 2. Key structure

```
orgs/{organization_id}/imports/{import_batch_id}/source.csv
orgs/{organization_id}/imports/{import_batch_id}/errors.csv
orgs/{organization_id}/exports/{export_id}/{export_kind}.csv
orgs/{organization_id}/attachments/{job_id}/{attachment_id}        # future
```

**Every segment is a server-generated UUID or a fixed literal. No user-supplied string appears
in a key, ever.** This single rule eliminates:

- path traversal (`../../other-org/imports/...`)
- key collision between two files named `export.csv`
- injection of control characters or unicode lookalikes into keys
- information leakage through filenames (`Acme_Corp_Q3_layoffs.csv`)

The original filename is stored in `import_batches.original_filename` for display, and is
returned to the user at download time via the `download_filename` parameter of
`signed_download_url` (which sets `Content-Disposition`), **sanitised** at that point: strip
path separators, control characters and leading dots, cap at 200 characters, fall back to a
generated name if nothing survives.

The `orgs/{organization_id}/` prefix is what makes `delete_prefix` a complete tenant purge and
makes any future bucket policy or lifecycle rule tenant-aware by construction.

---

## 3. Bucket configuration

| Setting | Value |
| --- | --- |
| Public access | **Blocked.** No public bucket, no public dev bucket, no exceptions |
| Access | S3 API with scoped R2 API tokens only |
| Encryption | R2 server-side encryption (default) |
| Versioning | Off (cost); deletion is intended to be final |
| CORS | `PUT` allowed only from the exact app origins in `CORS_ALLOWED_ORIGINS`; `Content-Type` allowed; `ETag` exposed |
| Lifecycle | Abort incomplete multipart uploads after 1 day; expire `exports/` objects after 30 days |
| Buckets | One per environment: `secondtrip-dev`, `secondtrip-prod`. Never shared |

Separate buckets per environment, not a shared bucket with prefixes, because a misconfigured
staging credential must not be able to read production data.

---

## 4. Signed URLs

### Download

```python
async def download_import_file(tenant, import_id) -> str:
    batch = await imports.get(tenant, import_id)      # org-scoped: 404 if not theirs
    require_permission(tenant, Permission.IMPORTS_READ)
    return await storage.signed_download_url(
        batch.storage_key, expires_in=300,
        download_filename=safe_filename(batch.original_filename),
    )
```

- **Authorization happens before signing**, in our code. The signed URL is the *result* of a
  successful authorization check, never a substitute for one.
- 5 minute TTL. Long enough to click, short enough that a URL in a browser history or a
  pasted Slack message is stale.
- Signed URLs are **never logged** (the log redactor scrubs any value containing
  `X-Amz-Signature`) and never sent by email. Emails link to an app page that mints a fresh
  URL after re-authenticating.

### Upload

```python
PresignedUpload(
    url=...,
    method="PUT",
    headers={"Content-Type": "text/csv"},
    key="orgs/.../source.csv",
    max_bytes=52_428_800,
    expires_at=...,
)
```

Cloudflare R2 supports presigned `PUT` but not presigned HTML `POST` policies, so it cannot apply
an S3 `content-length-range` policy to this URL. The browser rejects files above `max_bytes`
before upload as a usability/cost guard. After upload, the API independently calls `HEAD`, deletes
an oversized object immediately, and refuses to profile it; streaming verification repeats the
bound so inconsistent metadata cannot bypass the limit. Plan entitlements and the 500 MB hard
ceiling still apply. This is a documented provider limitation, not a claim that client-side size
checking is a security boundary.

`Content-Type` is pinned to `text/csv`. Note that this is a *hygiene* control, not a security
one: `Content-Type` is client-asserted and the file's real content is whatever was uploaded.
The actual protection is that we never serve these objects back as web content — downloads
carry `Content-Disposition: attachment` and are parsed as CSV, never rendered.

---

## 5. Lifecycle and deletion

| Object | Retained | Deleted when |
| --- | --- | --- |
| Import source files | Org retention window (default 24 months) | Import deleted, retention elapsed, or org purged |
| Import error reports | 90 days | Batch deleted or expired |
| Exports | 30 days | Lifecycle rule, or user deletion |
| Future attachments | Org retention window | Job deleted or org purged |

**Deletion is two-phase and DB-first.** The database row is the source of truth for what
exists; a `storage.cleanup` job performs the object delete afterwards:

1. Mark the row deleted (transactional, immediately effective for the user).
2. Enqueue `storage.cleanup` with the key.
3. The job deletes the object and is idempotent — deleting an absent key succeeds.

Doing it in the other order creates the worse failure: an object deleted, then the transaction
rolls back, leaving a database row pointing at nothing. An orphaned object costs fractions of
a cent; an orphaned row breaks the product. A weekly reconciliation job lists prefixes and
deletes objects with no corresponding row, catching the orphans.

Organization purge calls `delete_prefix(f"orgs/{org_id}/")` — one call, complete, and correct
precisely because of the key structure in §2.

---

## 6. Security summary

| Risk | Control |
| --- | --- |
| Public bucket exposure | Public access blocked; no object is ever served directly |
| Cross-tenant object access | Org-namespaced keys + authorization before signing |
| Path traversal via filename | Keys contain no user input |
| Signed URL leakage | 5 min TTL, never logged, never emailed |
| Oversized upload | Browser pre-check; authoritative `HEAD` + streaming bound; immediate delete and rejection |
| Unbounded storage cost | Entitlement limits + lifecycle expiry |
| Stored malicious content | Never rendered as web content; always `Content-Disposition: attachment`; parsed only as CSV with hard limits ([06 §9](06-csv-ingestion.md)) |
| Credential compromise | Scoped R2 tokens per environment, rotatable; no long-lived root keys |

**Note on malware scanning:** not in V1. The files are CSVs we parse ourselves and never
execute or render. When user-uploaded attachments (photos, PDFs) arrive, that changes and
scanning must be reconsidered as part of that feature — recorded here so it is not forgotten
at the point it starts to matter.
