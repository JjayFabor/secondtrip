"""Password hashing and secret-token helpers.

See docs/architecture/03-authentication.md §2–3. Argon2id parameters
match the spec exactly. Every bearer token in this codebase (session,
email verification, password reset, invitation) follows the same shape:
a high-entropy random value sent to the client once, stored only as a
hash, single-use where applicable, short-lived.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_bearer_token() -> str:
    """A high-entropy value to send to the client once. Never stored raw."""
    return secrets.token_urlsafe(32)


def hash_ip(ip: str, *, app_secret: str) -> str:
    """`sha256(ip + APP_SECRET)` — see docs/architecture/03-authentication.md
    §2. Raw IPs are never stored; rotating APP_SECRET invalidates every
    existing hash by design (17-configuration.md §11)."""
    return hashlib.sha256(f"{ip}{app_secret}".encode()).hexdigest()


def hash_token(raw_token: str) -> str:
    """Hex-encoded SHA-256 of a bearer token — what we actually store and
    compare against. Stored as `text`, not `bytea` (a deliberate deviation
    from 04-data-model.md's original column type): hex text compares
    cleanly through Postgres GUCs used by RLS policies that need to match
    against a token hash (see organization_invitations' policy in
    02-multi-tenancy.md §2), and it's far less friction everywhere else
    (logs-redaction matching, psql debugging) for a column that is never
    read as bytes."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
