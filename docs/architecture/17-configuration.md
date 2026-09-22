# 17 — Configuration

All configuration is environment variables, read in exactly one place:
`app/core/settings.py` (backend) and `next.config.ts` / `process.env` (frontend). No module
anywhere else calls `os.environ`.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__",
                                      extra="forbid", frozen=True)
```

`extra="forbid"` catches typo'd variable names at boot rather than silently using a default.
`frozen=True` prevents runtime mutation of configuration, which is a genuine source of
heisenbugs in long-running workers.

Legend — **R** required · **O** optional · **D** development only · **P** production only.

---

## 1. Application

| Variable | | Default | Notes |
| --- | :---: | --- | --- |
| `APP_ENV` | R | — | `local` · `ci` · `staging` · `production` |
| `APP_NAME` | O | `SecondTrip` | |
| `APP_SECRET` | R | — | ≥ 32 bytes. Pepper for IP/email hashing and CSRF tokens. **Rotating invalidates existing hashes** |
| `APP_URL` | R | — | Public API base, e.g. `https://api.secondtrip.example.com` |
| `FRONTEND_URL` | R | — | Used in emails and redirects. **Never hard-code the domain anywhere else** |
| `COOKIE_DOMAIN` | R | — | e.g. `.secondtrip.example.com`. Must be the parent of both app and API ([01 §2](01-system-architecture.md)) |
| `CORS_ALLOWED_ORIGINS` | R | — | Comma-separated. Startup fails if it contains `*` |
| `LOG_LEVEL` | O | `INFO` | |
| `LOG_FORMAT` | O | `json` | `console` locally |
| `DEBUG` | D | `false` | Never `true` in production; asserted at startup |

**Startup assertions** (fail fast, in `settings.py`):

- `APP_ENV=production` ⇒ `DEBUG=false`, `APP_URL`/`FRONTEND_URL` are `https`, `APP_SECRET` is
  not the development default, `COOKIE_SECURE=true`.
- `CORS_ALLOWED_ORIGINS` contains no wildcard while credentials are enabled.

A misconfigured production boot should crash loudly, not serve insecurely.

---

## 2. Database

| Variable | | Default | Notes |
| --- | :---: | --- | --- |
| `DATABASE_URL` | R | — | App connection. **Pooled** Neon endpoint, **non-owner** role `secondtrip_app`. `postgresql+asyncpg://` |
| `DATABASE_URL_MIGRATIONS` | R | — | Alembic. **Direct** (unpooled) endpoint, **owner** role |
| `DB_POOL_SIZE` | O | `5` | Neon connection limits are lower than self-hosted |
| `DB_MAX_OVERFLOW` | O | `5` | |
| `DB_POOL_RECYCLE_SECONDS` | O | `1800` | |
| `DB_STATEMENT_TIMEOUT_MS` | O | `30000` | Per-session; long analytics run in jobs, not requests |
| `DB_ECHO` | D | `false` | |

Two URLs is a hard requirement, not a convenience. The app role must not own the tables, or
RLS is bypassed ([02 §2](02-multi-tenancy.md)). The asyncpg driver must be configured with
`statement_cache_size=0` against the pooled endpoint, or PgBouncer transaction mode will
produce intermittent "prepared statement already exists" errors under load.

---

## 3. Authentication & sessions

| Variable | | Default |
| --- | :---: | --- |
| `SESSION_COOKIE_NAME` | O | `st_session` |
| `SESSION_IDLE_TIMEOUT_DAYS` | O | `14` |
| `SESSION_ABSOLUTE_TIMEOUT_DAYS` | O | `30` |
| `COOKIE_SECURE` | O | `true` (`false` only when `APP_ENV=local`) |
| `COOKIE_SAMESITE` | O | `lax` |
| `CSRF_COOKIE_NAME` | O | `st_csrf` |
| `PASSWORD_MIN_LENGTH` | O | `12` |
| `ARGON2_TIME_COST` / `ARGON2_MEMORY_KIB` / `ARGON2_PARALLELISM` | O | `3` / `65536` / `4` |
| `EMAIL_VERIFICATION_TTL_HOURS` | O | `24` |
| `PASSWORD_RESET_TTL_MINUTES` | O | `60` |
| `INVITATION_TTL_DAYS` | O | `7` |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_MINUTES` | O | `5` / `15` |

---

## 4. Storage

| Variable | | Default | Notes |
| --- | :---: | --- | --- |
| `STORAGE_PROVIDER` | O | `r2` | `r2` · `local` (dev) · `memory` (tests) |
| `STORAGE_BUCKET` | R | — | Per environment; never shared |
| `STORAGE_ENDPOINT_URL` | R | — | `https://<account>.r2.cloudflarestorage.com`; HTTPS required outside local development |
| `STORAGE_ACCESS_KEY_ID` | R | — | Secret |
| `STORAGE_SECRET_ACCESS_KEY` | R | — | Secret |
| `STORAGE_REGION` | O | `auto` | R2 requires `auto`; other values fail startup |
| `STORAGE_SIGNED_URL_TTL_SECONDS` | O | `300` | Downloads |
| `STORAGE_UPLOAD_URL_TTL_SECONDS` | O | `900` | Uploads |
| `STORAGE_LOCAL_PATH` | D | `./.storage` | |

---

## 5. Email

| Variable | | Default | Notes |
| --- | :---: | --- | --- |
| `EMAIL_PROVIDER` | O | `resend` | `resend` · `console` (dev) · `memory` (tests) |
| `EMAIL_API_KEY` | P | — | Secret |
| `EMAIL_FROM_ADDRESS` | R | — | e.g. `noreply@secondtrip.example.com` |
| `EMAIL_FROM_NAME` | O | `SecondTrip` | |
| `EMAIL_REPLY_TO` | O | — | |

`console` in development prints the rendered email to stdout, including the verification link.
This removes the need for a real mail provider locally, which in turn removes the temptation to
put a real API key in a developer `.env`.

---

## 6. Background worker

| Variable | | Default | Notes |
| --- | :---: | --- | --- |
| `WORKER_ENABLED` | O | `true` | In-process in V1; set `false` on the API when splitting to a dedicated service ([09 §7](09-background-jobs.md)) |
| `WORKER_ID` | O | hostname+pid | Recorded in `locked_by` |
| `WORKER_CONCURRENCY` | O | `2` | |
| `WORKER_BATCH_SIZE` | O | `5` | Jobs claimed per poll |
| `WORKER_POLL_MIN_SECONDS` / `_MAX_SECONDS` | O | `0.5` / `5` | Adaptive backoff bounds |
| `WORKER_HEARTBEAT_SECONDS` | O | `15` | |
| `WORKER_STALE_AFTER_SECONDS` | O | `120` | Must be > 4× heartbeat |
| `JOB_MAX_ATTEMPTS` | O | `5` | |
| `JOB_BACKOFF_BASE_SECONDS` / `_MAX_SECONDS` | O | `10` / `3600` | |

---

## 7. Imports & detection defaults

These are **defaults for new organizations**, not runtime limits — an org's own settings, once
created, live in the database and are not affected by changing these.

| Variable | | Default |
| --- | :---: | --- |
| `IMPORT_MAX_FILE_BYTES` | O | `524288000` (hard ceiling, above every plan limit) |
| `IMPORT_MAX_ROWS` | O | `2000000` (hard ceiling) |
| `IMPORT_CHUNK_SIZE` | O | `500` |
| `IMPORT_MAX_FIELD_BYTES` | O | `32768` |
| `IMPORT_MAX_COLUMNS` | O | `200` |
| `DETECTION_DEFAULT_WINDOW_DAYS` | O | `30` |
| `DETECTION_DEFAULT_MIN_SCORE_TO_SURFACE` | O | `40` |
| `DETECTION_MAX_FOLLOWUPS_PER_JOB` | O | `25` |

---

## 8. Observability & billing

| Variable | | Default | Notes |
| --- | :---: | --- | --- |
| `SENTRY_DSN` | O | — | Errors go to stdout only when unset |
| `SENTRY_TRACES_SAMPLE_RATE` | O | `0.05` | |
| `SENTRY_ENVIRONMENT` | O | `APP_ENV` | |
| `BILLING_PROVIDER` | O | `noop` | `noop` in V1 |
| `BILLING_API_KEY` | P | — | Secret; unused in V1 |
| `BILLING_WEBHOOK_SECRET` | P | — | Secret; unused in V1 |
| `RATE_LIMIT_ENABLED` | O | `true` | |
| `RATE_LIMIT_USER_PER_MINUTE` / `_ORG_PER_MINUTE` | O | `300` / `1000` | |

---

## 9. Frontend

| Variable | | Notes |
| --- | :---: | --- |
| `NEXT_PUBLIC_APP_URL` | R | Public site URL — canonical tags, sitemap, OG images |
| `NEXT_PUBLIC_API_URL` | R | Browser-visible API base |
| `API_INTERNAL_URL` | O | Server-side API base if it differs (avoids a public round trip) |
| `NEXT_PUBLIC_ENVIRONMENT` | O | Gates analytics and `noindex` on preview deployments |
| `NEXT_PUBLIC_SENTRY_DSN` | O | Client errors |
| `NEXT_PUBLIC_PLAUSIBLE_DOMAIN` | O | Privacy-friendly analytics; omit to disable |

**Only `NEXT_PUBLIC_*` reaches the browser.** A build-time check fails the build if a name
matching `/(SECRET|KEY|TOKEN|PASSWORD|DSN_PRIVATE)/` carries the `NEXT_PUBLIC_` prefix —
because the failure mode (a secret shipped in a JS bundle, cached at the edge, indexed) is
unrecoverable by rotation alone.

---

## 10. Secrets summary

Marked secret; never committed, never logged, never in `NEXT_PUBLIC_*`:

`APP_SECRET`, `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`, `STORAGE_ACCESS_KEY_ID`,
`STORAGE_SECRET_ACCESS_KEY`, `EMAIL_API_KEY`, `BILLING_API_KEY`,
`BILLING_WEBHOOK_SECRET`.

`.env.example` lists every variable above with placeholder values and a one-line comment. It is
committed; `.env` is git-ignored and covered by gitleaks.

---

## 11. Per-environment matrix

| | local | ci | staging | production |
| --- | --- | --- | --- | --- |
| `APP_ENV` | `local` | `ci` | `staging` | `production` |
| `DEBUG` | `true` | `false` | `false` | `false` |
| `COOKIE_SECURE` | `false` | `false` | `true` | `true` |
| `STORAGE_PROVIDER` | `local` | `memory` | `r2` | `r2` |
| `EMAIL_PROVIDER` | `console` | `memory` | `resend` | `resend` |
| `WORKER_ENABLED` | `true` | `false` | `true` | `true` |
| `SENTRY_DSN` | unset | unset | set | set |
| `RATE_LIMIT_ENABLED` | `false` | `true` | `true` | `true` |

`RATE_LIMIT_ENABLED=true` in CI specifically so the rate-limit tests are meaningful.
