"""Identity service. See docs/architecture/03-authentication.md.

Deferred, deliberately, out of Step 3's scope: email-change flow (no
exit criteria depends on it), breached-password list checking (needs a
wordlist this phase doesn't ship), exponential lockout backoff (a fixed
window per LOGIN_LOCKOUT_MINUTES stands in for it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.errors import ConflictError
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_bearer_token,
    verify_password,
)
from app.core.settings import Settings
from app.modules.identity.errors import (
    AccountLockedError,
    AccountNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.modules.identity.models import User, UserSession, UserStatus
from app.modules.identity.repository import IdentityRepository

# A fixed, valid-shaped hash verified against when no user is found, so a
# login attempt against a nonexistent email takes roughly the same time
# as one against a real email with a wrong password — see 03 §3.
_DUMMY_HASH = hash_password(new_bearer_token())


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    session: UserSession
    raw_session_token: str


@dataclass(frozen=True, slots=True)
class EmailDelivery:
    to: str
    template_key: str
    subject: str
    text_body: str


async def _issue_session(
    repo: IdentityRepository,
    settings: Settings,
    user: User,
    *,
    now: datetime,
    ip_hash: str | None,
    user_agent: str | None,
) -> tuple[UserSession, str]:
    raw_token = new_bearer_token()
    session_row = await repo.create_session(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        issued_at=now,
        expires_at=now + timedelta(days=settings.session_absolute_timeout_days),
        ip_hash=ip_hash,
        user_agent=user_agent,
    )
    return session_row, raw_token


async def register(
    repo: IdentityRepository,
    settings: Settings,
    *,
    email: str,
    password: str,
    full_name: str,
) -> EmailDelivery:
    """Always succeeds from the caller's point of view (the router
    returns 202 regardless) — see 03 §4. Enumeration protection: an
    existing email gets a notice, not a "verify your new account" email,
    and the two are indistinguishable to whoever made the request."""
    existing = await repo.get_user_by_email(email)
    if existing is not None:
        return EmailDelivery(
            to=email,
            template_key="registration_attempt_existing",
            subject="Someone tried to register with your email",
            text_body=(
                "Someone just tried to create a SecondTrip account with this email "
                "address, which already has one. If this wasn't you, no action is "
                "needed — your account is unaffected."
            ),
        )

    now = datetime.now(UTC)
    user = await repo.create_user(
        email=email, full_name=full_name, status=UserStatus.PENDING_VERIFICATION.value
    )
    await repo.create_credentials(user_id=user.id, password_hash=hash_password(password))

    raw_token = new_bearer_token()
    await repo.create_email_verification_token(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(hours=settings.email_verification_ttl_hours),
    )
    verify_url = f"{settings.frontend_url}/verify?token={raw_token}"
    return EmailDelivery(
        to=email,
        template_key="verify_email",
        subject="Verify your SecondTrip email",
        text_body=f"Confirm your email to finish creating your account:\n\n{verify_url}",
    )


async def resend_verification(
    repo: IdentityRepository, settings: Settings, *, email: str
) -> EmailDelivery | None:
    """Issue one fresh verification token without revealing account state."""
    user = await repo.get_user_by_email(email)
    if user is None or user.status != UserStatus.PENDING_VERIFICATION.value:
        return None

    now = datetime.now(UTC)
    await repo.invalidate_prior_email_verification_tokens(user.id, now=now)
    raw_token = new_bearer_token()
    await repo.create_email_verification_token(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(hours=settings.email_verification_ttl_hours),
    )
    verify_url = f"{settings.frontend_url}/verify?token={raw_token}"
    return EmailDelivery(
        to=email,
        template_key="verify_email",
        subject="Verify your SecondTrip email",
        text_body=f"Confirm your email to finish creating your account:\n\n{verify_url}",
    )


async def verify_email(
    repo: IdentityRepository,
    settings: Settings,
    *,
    raw_token: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> AuthResult:
    now = datetime.now(UTC)
    token_row = await repo.get_email_verification_token(hash_token(raw_token))
    if token_row is None or token_row.consumed_at is not None or token_row.expires_at < now:
        raise InvalidTokenError("This verification link is invalid or has expired.")

    user = await repo.get_user_by_id(token_row.user_id)
    assert user is not None  # FK guarantees this

    token_row.consumed_at = now
    user.status = UserStatus.ACTIVE.value
    user.email_verified_at = now
    user.last_login_at = now

    session_row, raw_session_token = await _issue_session(
        repo, settings, user, now=now, ip_hash=ip_hash, user_agent=user_agent
    )
    return AuthResult(user=user, session=session_row, raw_session_token=raw_session_token)


async def login(
    repo: IdentityRepository,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> AuthResult:
    now = datetime.now(UTC)
    user = await repo.get_user_by_email(email)
    if user is None:
        verify_password(_DUMMY_HASH, password)  # constant-time-ish — see module docstring
        raise InvalidCredentialsError("Incorrect email or password.")

    creds = await repo.get_credentials(user.id, for_update=True)
    assert creds is not None  # every user has credentials — enforced at creation

    if creds.locked_until is not None and creds.locked_until > now:
        raise AccountLockedError("Too many failed attempts. Try again later.")

    if not verify_password(creds.password_hash, password):
        creds.failed_attempt_count += 1
        if creds.failed_attempt_count >= settings.login_max_failures:
            creds.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        raise InvalidCredentialsError("Incorrect email or password.")

    if user.status != UserStatus.ACTIVE.value:
        raise AccountNotVerifiedError("Verify your email before signing in.")

    creds.failed_attempt_count = 0
    creds.locked_until = None
    if needs_rehash(creds.password_hash):
        creds.password_hash = hash_password(password)
    user.last_login_at = now

    session_row, raw_session_token = await _issue_session(
        repo, settings, user, now=now, ip_hash=ip_hash, user_agent=user_agent
    )
    return AuthResult(user=user, session=session_row, raw_session_token=raw_session_token)


async def logout(repo: IdentityRepository, *, session_id: UUID) -> None:
    await repo.revoke_session(session_id, now=datetime.now(UTC))


async def logout_all(repo: IdentityRepository, *, user_id: UUID) -> None:
    await repo.revoke_all_sessions(user_id, now=datetime.now(UTC))


async def request_password_reset(
    repo: IdentityRepository,
    settings: Settings,
    *,
    email: str,
) -> EmailDelivery | None:
    """Always a no-op from the caller's point of view — the router
    returns 202 regardless of whether the account exists (03 §4)."""
    user = await repo.get_user_by_email(email)
    if user is None:
        return None

    now = datetime.now(UTC)
    await repo.invalidate_prior_password_reset_tokens(user.id, now=now)
    raw_token = new_bearer_token()
    await repo.create_password_reset_token(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
    )
    reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
    return EmailDelivery(
        to=email,
        template_key="password_reset",
        subject="Reset your SecondTrip password",
        text_body=f"Reset your password:\n\n{reset_url}\n\nThis link expires in "
        f"{settings.password_reset_ttl_minutes} minutes.",
    )


async def change_password(
    repo: IdentityRepository,
    settings: Settings,
    *,
    user_id: UUID,
    current_password: str,
    new_password: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> AuthResult:
    user = await repo.get_user_by_id(user_id, for_update=True)
    creds = await repo.get_credentials(user_id, for_update=True)
    if user is None or creds is None or not verify_password(creds.password_hash, current_password):
        raise InvalidCredentialsError("Current password is incorrect.")

    now = datetime.now(UTC)
    creds.password_hash = hash_password(new_password)
    creds.password_updated_at = now
    creds.failed_attempt_count = 0
    creds.locked_until = None
    await repo.revoke_all_sessions(user_id, now=now)
    session_row, raw_session_token = await _issue_session(
        repo, settings, user, now=now, ip_hash=ip_hash, user_agent=user_agent
    )
    return AuthResult(user=user, session=session_row, raw_session_token=raw_session_token)


async def request_email_change(
    repo: IdentityRepository,
    settings: Settings,
    *,
    user_id: UUID,
    new_email: str,
) -> tuple[EmailDelivery, EmailDelivery] | None:
    user = await repo.get_user_by_id(user_id, for_update=True)
    if user is None:
        return None
    if user.email.lower() == new_email.lower():
        raise ConflictError("That is already your email address.")

    existing = await repo.get_user_by_email(new_email)
    if existing is not None and existing.id != user_id and existing.deleted_at is None:
        raise ConflictError("That email address is already in use.")

    now = datetime.now(UTC)
    await repo.invalidate_prior_email_change_tokens(user_id, now=now)
    raw_token = new_bearer_token()
    await repo.create_email_change_token(
        user_id=user_id,
        new_email=new_email,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
    )
    confirm_url = f"{settings.frontend_url}/confirm-email-change?token={raw_token}"
    return (
        EmailDelivery(
            to=new_email,
            template_key="email_change_confirmation",
            subject="Confirm your new SecondTrip email",
            text_body=f"Confirm your new email address:\n\n{confirm_url}",
        ),
        EmailDelivery(
            to=user.email,
            template_key="email_change_requested",
            subject="Your SecondTrip email is being changed",
            text_body=(
                f"A request was made to change your email to {new_email}. "
                "If this wasn't you, contact support immediately."
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class EmailChangeConfirmation:
    auth: AuthResult
    notification: EmailDelivery


async def confirm_email_change(
    repo: IdentityRepository,
    settings: Settings,
    *,
    raw_token: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> EmailChangeConfirmation:
    now = datetime.now(UTC)
    token_row = await repo.get_email_change_token(hash_token(raw_token))
    if token_row is None or token_row.consumed_at is not None or token_row.expires_at <= now:
        raise InvalidTokenError("This email-change link is invalid or has expired.")

    user = await repo.get_user_by_id(token_row.user_id, for_update=True)
    assert user is not None
    existing = await repo.get_user_by_email(token_row.new_email)
    if existing is not None and existing.id != user.id and existing.deleted_at is None:
        raise ConflictError("That email address is already in use.")

    old_email = user.email
    token_row.consumed_at = now
    user.email = token_row.new_email
    user.email_verified_at = now
    await repo.revoke_all_sessions(user.id, now=now)
    session_row, raw_session_token = await _issue_session(
        repo, settings, user, now=now, ip_hash=ip_hash, user_agent=user_agent
    )
    return EmailChangeConfirmation(
        auth=AuthResult(user=user, session=session_row, raw_session_token=raw_session_token),
        notification=EmailDelivery(
            to=old_email,
            template_key="email_changed",
            subject="Your SecondTrip email was changed",
            text_body=f"Your SecondTrip email is now {user.email}.",
        ),
    )


async def confirm_password_reset(
    repo: IdentityRepository,
    settings: Settings,
    *,
    raw_token: str,
    new_password: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> AuthResult:
    now = datetime.now(UTC)
    token_row = await repo.get_password_reset_token(hash_token(raw_token))
    if token_row is None or token_row.consumed_at is not None or token_row.expires_at < now:
        raise InvalidTokenError("This reset link is invalid or has expired.")

    user = await repo.get_user_by_id(token_row.user_id)
    assert user is not None
    creds = await repo.get_credentials(user.id)
    assert creds is not None

    token_row.consumed_at = now
    creds.password_hash = hash_password(new_password)
    creds.password_updated_at = now
    creds.failed_attempt_count = 0
    creds.locked_until = None

    # Non-negotiable — see 03 §4: consuming a reset token revokes every
    # existing session, not just the one that requested it.
    await repo.revoke_all_sessions(user.id, now=now)

    session_row, raw_session_token = await _issue_session(
        repo, settings, user, now=now, ip_hash=ip_hash, user_agent=user_agent
    )
    return AuthResult(user=user, session=session_row, raw_session_token=raw_session_token)


@dataclass(frozen=True, slots=True)
class SessionLookupResult:
    user: User
    session: UserSession


async def resolve_session(
    repo: IdentityRepository, settings: Settings, *, raw_token: str
) -> SessionLookupResult | None:
    """The core of require_session — see app/api/deps.py. Returns None
    for a missing, expired, or revoked session; the caller (the API
    dependency) turns that into 401. Touches last_seen_at at most once
    per hour per session — see 03 §2's sliding-refresh throttle."""
    now = datetime.now(UTC)
    session_row = await repo.get_session_by_token_hash(hash_token(raw_token))
    if session_row is None:
        return None
    if session_row.revoked_at is not None or session_row.expires_at <= now:
        return None

    user = await repo.get_user_by_id(session_row.user_id)
    if (
        user is None
        or user.deleted_at is not None
        or user.status != UserStatus.ACTIVE.value
        or now - session_row.last_seen_at > timedelta(days=settings.session_idle_timeout_days)
    ):
        return None

    if now - session_row.last_seen_at > timedelta(hours=1):
        await repo.touch_session(session_row.id, now=now)

    return SessionLookupResult(user=user, session=session_row)
