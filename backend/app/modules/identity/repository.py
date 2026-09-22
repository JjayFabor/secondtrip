"""Identity repository. Plain queries, no TenantContext — `users` and its
child tables are not tenant-owned (docs/architecture/02-multi-tenancy.md
§1), so there is no org scoping to enforce here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import (
    EmailChangeToken,
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserCredentials,
    UserSession,
)


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_credentials(
        self, user_id: UUID, *, for_update: bool = False
    ) -> UserCredentials | None:
        statement = select(UserCredentials).where(UserCredentials.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def create_user(self, *, email: str, full_name: str, status: str) -> User:
        user = User(email=email, full_name=full_name, status=status)
        self._session.add(user)
        await self._session.flush()  # populate user.id for the caller
        return user

    async def create_credentials(self, *, user_id: UUID, password_hash: str) -> UserCredentials:
        creds = UserCredentials(user_id=user_id, password_hash=password_hash)
        self._session.add(creds)
        return creds

    async def create_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        issued_at: datetime,
        expires_at: datetime,
        ip_hash: str | None,
        user_agent: str | None,
    ) -> UserSession:
        session_row = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            issued_at=issued_at,
            expires_at=expires_at,
            last_seen_at=issued_at,
            ip_hash=ip_hash,
            user_agent=user_agent[:512] if user_agent else None,
        )
        self._session.add(session_row)
        await self._session.flush()
        return session_row

    async def create_email_verification_token(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> EmailVerificationToken:
        token_row = EmailVerificationToken(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self._session.add(token_row)
        return token_row

    async def create_password_reset_token(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        token_row = PasswordResetToken(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self._session.add(token_row)
        return token_row

    async def create_email_change_token(
        self,
        *,
        user_id: UUID,
        new_email: str,
        token_hash: str,
        expires_at: datetime,
    ) -> EmailChangeToken:
        token_row = EmailChangeToken(
            user_id=user_id,
            new_email=new_email,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token_row)
        return token_row

    async def get_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        result = await self._session.execute(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_session_by_id(self, user_id: UUID, session_id: UUID) -> UserSession | None:
        result = await self._session.execute(
            select(UserSession).where(UserSession.user_id == user_id, UserSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_active_sessions(self, user_id: UUID) -> list[UserSession]:
        result = await self._session.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_seen_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_session(self, session_id: UUID, *, now: datetime) -> None:
        await self._session.execute(
            update(UserSession).where(UserSession.id == session_id).values(revoked_at=now)
        )

    async def revoke_all_sessions(self, user_id: UUID, *, now: datetime) -> None:
        await self._session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_other_sessions(
        self, user_id: UUID, *, except_session_id: UUID, now: datetime
    ) -> None:
        await self._session.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.id != except_session_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def touch_session(self, session_id: UUID, *, now: datetime) -> None:
        await self._session.execute(
            update(UserSession).where(UserSession.id == session_id).values(last_seen_at=now)
        )

    async def get_email_verification_token(self, token_hash: str) -> EmailVerificationToken | None:
        result = await self._session.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_password_reset_token(self, token_hash: str) -> PasswordResetToken | None:
        result = await self._session.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_email_change_token(self, token_hash: str) -> EmailChangeToken | None:
        result = await self._session.execute(
            select(EmailChangeToken)
            .where(EmailChangeToken.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def invalidate_prior_password_reset_tokens(self, user_id: UUID, *, now: datetime) -> None:
        await self._session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.consumed_at.is_(None))
            .values(consumed_at=now)
        )

    async def invalidate_prior_email_verification_tokens(
        self, user_id: UUID, *, now: datetime
    ) -> None:
        await self._session.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

    async def invalidate_prior_email_change_tokens(self, user_id: UUID, *, now: datetime) -> None:
        await self._session.execute(
            update(EmailChangeToken)
            .where(EmailChangeToken.user_id == user_id, EmailChangeToken.consumed_at.is_(None))
            .values(consumed_at=now)
        )
