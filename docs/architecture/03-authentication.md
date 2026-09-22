# 03 — Authentication & Session Architecture

**Decision:** application-managed authentication in FastAPI. Opaque, server-side sessions
carried in an `httpOnly` cookie. No third-party identity provider.

---

## 1. Why this, and what it costs

FastAPI already owns authorization (roles, memberships, entitlements). Putting identity
anywhere else splits the security model across two runtimes and creates a class of bug where
a token's claims disagree with the database — a demoted user keeps admin rights until their
JWT expires.

| | App-managed sessions (chosen) | Better Auth in Next.js | Clerk / WorkOS |
| --- | --- | --- | --- |
| Monthly cost | $0 | $0 | $0 → $25+/mo past free MAU |
| Revocation | Immediate (delete a row) | Depends on JWT TTL | Immediate |
| Role change takes effect | Next request | Next token refresh | Next request |
| Auth + authz in one place | ✅ | ❌ | ❌ |
| Build effort | ~1 week | ~2 days | ~1 day |
| Org/invite model | Ours | Ours | Vendor's |

We pay roughly a week of implementation to remove a vendor, a dollar cost, and a whole class
of distributed-authorization bug. At this project's scale that trade is correct.

**Stateful (opaque) sessions over JWTs.** A stateless JWT saves a database read per request —
an optimization worth nothing here, because every request already reads the membership row to
resolve the tenant. In exchange, JWTs make logout, revocation, and "sign out all devices"
genuinely hard. We are already paying for the lookup; we should take the revocability.

---

## 2. Session mechanics

### Token format

- 32 bytes from `secrets.token_urlsafe(32)` → the raw token, sent to the browser once.
- Stored as `sha256(raw_token)` in `user_sessions.token_hash` (`bytea`, unique).
  A database leak therefore does not yield usable sessions.
- Lookup is `WHERE token_hash = :h` — an indexed equality on a hash, constant time. (HMAC
  with a pepper is an option; plain SHA-256 is sufficient here because the token is
  high-entropy and random, not a password.)
- Token is never logged, never placed in a URL, never returned in a response body.

### Cookie

```
Set-Cookie: st_session=<raw_token>;
            Domain=.<COOKIE_DOMAIN>;       # e.g. .secondtrip.example.com
            Path=/;
            HttpOnly;
            Secure;                        # always in prod; omitted only when APP_ENV=local
            SameSite=Lax;
            Max-Age=2592000                # 30 days, matched to absolute expiry
```

`SameSite=Lax` (not `Strict`): `Strict` breaks the "click the verification link in your
email → land logged in" flow, because the cookie is withheld on cross-site top-level
navigation. `Lax` sends it on top-level GETs while still blocking cross-site POSTs, which is
precisely the CSRF property we want.

**Deployment constraint (repeat of [01 §2](01-system-architecture.md)):** frontend and API
must be subdomains of one registrable domain. `*.vercel.app` + `*.onrender.com` are
cross-site and `SameSite=Lax` will not work between them. Custom domains are a prerequisite
for auth, not a finishing touch.

### Lifetimes

| Property | Value | Rationale |
| --- | --- | --- |
| Idle timeout | 14 days | Balance for a weekly-use B2B tool |
| Absolute expiry | 30 days | Bounds the damage of a stolen cookie |
| Sliding refresh | Yes, at most once per hour | Updating `last_seen_at` on every request is a write per request; throttle it |
| Rotation | On privilege change (password change, email change, MFA enrol) | Invalidate all other sessions |

### `user_sessions` table

| Column | Type | Note |
| --- | --- | --- |
| `id` | uuid PK (v7) | |
| `user_id` | uuid FK → users, `ON DELETE CASCADE` | |
| `token_hash` | bytea UNIQUE NOT NULL | sha256 of raw token |
| `issued_at` | timestamptz NOT NULL | |
| `expires_at` | timestamptz NOT NULL | absolute expiry |
| `last_seen_at` | timestamptz NOT NULL | sliding; throttled writes |
| `revoked_at` | timestamptz NULL | explicit logout / admin revoke |
| `ip_hash` | bytea NULL | `sha256(ip + APP_SECRET)`; for "suspicious login" UX without storing raw IPs |
| `user_agent` | text NULL | truncated to 512 chars, for a device list UI |

Index: `(user_id, revoked_at)` for "list my sessions" and bulk revoke.
A daily `system.purge_expired_sessions` job deletes rows past `expires_at + 7 days`.

**No `organization_id` on the session.** See
[02-multi-tenancy.md §4 risk 15](02-multi-tenancy.md).

---

## 3. Password handling

- **Argon2id** via `argon2-cffi`. Parameters: `time_cost=3`, `memory_cost=65536` (64 MiB),
  `parallelism=4`, 32-byte hash, 16-byte salt. Tune `memory_cost` down only if Render's
  512 MB starter instance shows pressure under concurrent logins — and if so, document the
  new value rather than silently weakening it.
- Store the full PHC-format string in `user_credentials.password_hash`; it encodes the
  algorithm and parameters, so raising cost later is a transparent rehash-on-login.
- **Rehash on successful login** when `hasher.check_needs_rehash()` is true.
- Minimum length 12, maximum 128 (guard against a DoS via a megabyte password). No
  composition rules — they reduce entropy in practice. Check candidate passwords against a
  local breached-password list (`zxcvbn` or a bloom filter of the top 100k) and reject the
  obviously compromised.
- **Timing:** the login path must execute a dummy Argon2 verification when the email does not
  exist, so response time does not disclose account existence.
- **Enumeration:** `POST /auth/login` returns one error for both "no such user" and "wrong
  password". `POST /auth/register` with an existing email returns `202 Accepted` and sends a
  "someone tried to register with your address" email rather than confirming the account
  exists.

---

## 4. Flows

All tokens below follow the same pattern: **a high-entropy random value, sent by email,
stored only as a hash, single-use, short-lived.**

| Flow | Table | TTL | Single use | Notes |
| --- | --- | --- | --- | --- |
| Email verification | `email_verification_tokens` | 24 h | ✅ | Account exists but is `pending_verification`; cannot create or join an org until verified |
| Password reset | `password_reset_tokens` | 60 min | ✅ | Consuming it revokes **all** the user's sessions |
| Organization invitation | `organization_invitations` | 7 days | ✅ | Carries `organization_id` + `role`; see below |
| Email change | `email_change_tokens` | 60 min | ✅ | Confirmation sent to the **new** address; notification to the old |

### Registration

```
POST /auth/register {email, password, name}
  → user (status=pending_verification) + user_credentials
  → email_verification_token issued, emailed
  → 202 Accepted (no session yet)

GET  /verify?token=...     (frontend route)
POST /auth/verify-email {token}
  → user.status = active, email_verified_at set
  → session created, cookie set
  → if a pending invitation matches this email, surface it for acceptance
```

Requiring verification before session creation prevents a signup flood from creating usable
accounts, and guarantees that every org owner controls a reachable mailbox.

### Password reset

```
POST /auth/password-reset/request {email}
  → ALWAYS 202, regardless of whether the account exists
  → if it exists: invalidate prior unused tokens, issue one, email it

POST /auth/password-reset/confirm {token, new_password}
  → verify hash + unexpired + unused
  → update password_hash, mark token used
  → revoke ALL sessions for the user   ← non-negotiable
  → create one fresh session, set cookie
  → send "your password was changed" notification email
```

### Organization invitations

```
POST /orgs/{org_id}/invitations {email, role}        (admin+)
  → row: organization_id, email (lowercased), role, token_hash, invited_by, expires_at
  → email with link to /accept-invite?token=...

POST /auth/invitations/accept {token}
  → resolve invitation BY TOKEN HASH, and read organization_id + role FROM THE ROW
  → require an authenticated, verified user
  → if the session user's email ≠ invitation email → 403 with a clear message
  → create organization_membership, mark invitation accepted
```

Two rules that matter:

- **The organization and role come from the invitation row, never from the request body.**
  Otherwise the token becomes a coupon redeemable for a role of the attacker's choosing.
- **Binding the invite to the email address** prevents a forwarded link from granting a
  stranger access. It costs a little UX friction (the invitee must register with the invited
  address) and is worth it.
- Re-inviting an existing pending invitation revokes the old token and issues a new one, so
  only one live token exists per (org, email).

### Logout

```
POST /auth/logout        → revoked_at = now() on the current session; clear cookie
POST /auth/logout-all    → revoke every session for the user; clear cookie
```

Revocation is a single `UPDATE`. The auth dependency treats `revoked_at IS NOT NULL` as
unauthenticated, so revocation is effective on the very next request across all instances —
no token blocklist, no propagation delay.

---

## 5. CSRF

The threat exists because we authenticate with a cookie. Defence is layered:

1. **`SameSite=Lax`** blocks cross-site `POST`/`PUT`/`PATCH`/`DELETE` from carrying the
   cookie. This alone stops the classic form-post CSRF.
2. **Origin/Referer validation** on every state-changing request: reject unless `Origin`
   matches an entry in `CORS_ALLOWED_ORIGINS`. Cheap, stateless, and covers browsers or
   contexts where `SameSite` behaves unexpectedly.
3. **Double-submit token** for state-changing requests issued from the browser directly to
   the API: a non-`httpOnly` `st_csrf` cookie whose value must be echoed in an `X-CSRF-Token`
   header. The cookie uses the same shared `COOKIE_DOMAIN` as the session cookie so frontend
   JavaScript can read it. The API compares the two values and rejects a mismatch.
4. **No state-changing `GET`s.** Ever. A `GET` that mutates bypasses every mitigation above.

Requests proxied through Next.js server components carry no browser-originating CSRF risk
(the server explicitly attaches the cookie), but they are subject to the same checks — the
Next.js server sends the `Origin` header of the app domain.

---

## 6. CORS

```python
CORSMiddleware(
    allow_origins=settings.cors_allowed_origins,   # explicit list from env; never "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-Id", "Idempotency-Key"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)
```

`allow_credentials=True` with `allow_origins=["*"]` is rejected by browsers and would be a
severe bug; the settings loader should **fail at startup** if `"*"` appears in the list while
credentials are enabled. Preview deployments get their origins added explicitly via env, not
by a regex wildcard.

---

## 7. Brute force and abuse

| Surface | Limit | Mechanism |
| --- | --- | --- |
| `POST /auth/login` per email | 5 failures / 15 min, then exponential lockout to 1 h | `login_attempts` counter on the credential row |
| `POST /auth/login` per IP | 20 / 5 min | Sliding window in Postgres |
| `POST /auth/password-reset/request` | 3 / hour per email, 10 / hour per IP | Same |
| `POST /auth/register` | 5 / hour per IP | Same |
| Invitation sends | 50 / day per org | Entitlement + rate limit |

V1 stores counters in a small `rate_limit_counters` table (`key`, `window_start`, `count`)
with an upsert. It is not elegant and it is entirely adequate at this volume; the interface
(`RateLimiter.check(key, limit, window)`) is what matters, so swapping in Redis later is a
one-file change. Cloudflare in front of the API provides a coarse outer layer for free.

Successful logins **reset** the failure counter. Lockout messages must not reveal whether the
account exists.

---

## 8. What the frontend may and may not do

- **May:** call `GET /api/v1/me` to render the current user and their organizations; hide UI
  affordances based on role for usability.
- **May:** rely on Next.js `proxy.ts` to redirect an unauthenticated visitor away from
  `/app/*` — a UX optimisation that checks only for cookie *presence*, never validity.
- **May not:** treat any frontend check as enforcement. Every `/app` page's data comes from an
  API call that independently authenticates and authorizes.
- **May not:** read, copy, or persist the session token (it is `httpOnly`, so this is
  structurally prevented).
- **May not:** cache authenticated API responses in a shared/CDN cache. All `/api/v1/orgs/**`
  responses carry `Cache-Control: private, no-store`.

---

## 9. Deferred, with a clean path

| Feature | Notes on readiness |
| --- | --- |
| TOTP MFA | `user_mfa_factors` table; session gains `mfa_satisfied_at`. Additive |
| OAuth (Google) | `user_identities (user_id, provider, subject)`; the session model is unchanged |
| SSO / SAML | Enterprise-tier concern; would attach at the organization level with a domain claim |
| API keys for customers | `api_keys (organization_id, prefix, secret_hash, scopes)`; produces a `TenantContext` with `actor_type=api_key`. The `TenantContext` already models a null user, so this is additive |
| Device/session management UI | The `user_sessions` columns (`ip_hash`, `user_agent`) already support it |
