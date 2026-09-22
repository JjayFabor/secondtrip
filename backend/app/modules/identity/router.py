"""Identity routes — see docs/architecture/15-api-design.md §2 (/auth, /me).

Every state-changing endpoint here is a plain (non-tenant) session — see
db/session.py's module docstring for why: registration, login, and
password reset all happen before there's any org context to set.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition import AppState, get_app_state
from app.core.rate_limit import enforce_rate_limit
from app.db.session import user_session
from app.modules.identity.deps import (
    AuthenticatedUser,
    get_client_ip_hash,
    get_user_scoped_session,
    require_session,
)
from app.modules.identity.errors import InvalidCredentialsError
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    ConfirmEmailChangeRequest,
    EmailChangeRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    RegisterRequest,
    ResendVerificationRequest,
    SessionOut,
    UpdateProfileRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.modules.identity.service import (
    change_password,
    confirm_email_change,
    confirm_password_reset,
    login,
    logout,
    logout_all,
    register,
    request_email_change,
    request_password_reset,
    resend_verification,
    verify_email,
)

router = APIRouter(tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["me"])


def _set_session_cookie(response: Response, app_state: AppState, raw_token: str) -> None:
    response.set_cookie(
        app_state.settings.session_cookie_name,
        raw_token,
        max_age=app_state.settings.session_absolute_timeout_days * 24 * 3600,
        secure=app_state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
        domain=app_state.settings.cookie_domain,
        path="/",
    )


def _clear_session_cookie(response: Response, app_state: AppState) -> None:
    response.delete_cookie(
        app_state.settings.session_cookie_name,
        domain=app_state.settings.cookie_domain,
        path="/",
    )


@router.post("/auth/register", status_code=status.HTTP_202_ACCEPTED)
async def register_endpoint(
    body: RegisterRequest,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> dict[str, str]:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"auth:register:ip:{ip_hash or 'unknown'}",
        limit=app_state.settings.register_ip_limit,
        window_seconds=app_state.settings.register_ip_window_seconds,
    )
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        delivery = await register(
            repo,
            app_state.settings,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
        )
    await app_state.email_provider.send(
        to=delivery.to,
        template_key=delivery.template_key,
        subject=delivery.subject,
        text_body=delivery.text_body,
    )
    return {"detail": "Check your email to verify your account."}


@router.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification_endpoint(
    body: ResendVerificationRequest,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> dict[str, str]:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"auth:verify-resend:ip:{ip_hash or 'unknown'}",
        limit=app_state.settings.verification_ip_limit,
        window_seconds=app_state.settings.verification_ip_window_seconds,
    )
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        delivery = await resend_verification(repo, app_state.settings, email=body.email)
    if delivery is not None:
        await app_state.email_provider.send(
            to=delivery.to,
            template_key=delivery.template_key,
            subject=delivery.subject,
            text_body=delivery.text_body,
        )
    return {"detail": "If that account needs verification, a new link has been sent."}


@router.post("/auth/verify-email")
async def verify_email_endpoint(
    body: VerifyEmailRequest,
    response: Response,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> UserOut:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        result = await verify_email(
            repo,
            app_state.settings,
            raw_token=body.token,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent"),
        )
    _set_session_cookie(response, app_state, result.raw_session_token)
    return UserOut.model_validate(result.user)


@router.post("/auth/login")
async def login_endpoint(
    body: LoginRequest,
    response: Response,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> UserOut:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"auth:login:ip:{ip_hash or 'unknown'}",
        limit=app_state.settings.login_ip_limit,
        window_seconds=app_state.settings.login_ip_window_seconds,
    )
    result = None
    login_error: InvalidCredentialsError | None = None
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        try:
            result = await login(
                repo,
                app_state.settings,
                email=body.email.lower(),
                password=body.password,
                ip_hash=ip_hash,
                user_agent=request.headers.get("user-agent"),
            )
        except InvalidCredentialsError as exc:
            # A failed-password counter is deliberately committed before the
            # error is rendered; raising inside the transaction would roll it
            # back and make lockout ineffective.
            login_error = exc
    if login_error is not None:
        raise login_error
    assert result is not None
    _set_session_cookie(response, app_state, result.raw_session_token)
    return UserOut.model_validate(result.user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    response: Response,
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
) -> None:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        await logout(repo, session_id=user.session_id)
    _clear_session_cookie(response, app_state)


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_endpoint(
    response: Response,
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
) -> None:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        await logout_all(repo, user_id=user.id)
    _clear_session_cookie(response, app_state)


@router.post("/auth/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def password_reset_request_endpoint(
    body: PasswordResetRequestRequest,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> dict[str, str]:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"auth:password-reset:email:{body.email}",
        limit=app_state.settings.password_reset_email_limit,
        window_seconds=app_state.settings.password_reset_window_seconds,
    )
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"auth:password-reset:ip:{ip_hash or 'unknown'}",
        limit=app_state.settings.password_reset_ip_limit,
        window_seconds=app_state.settings.password_reset_window_seconds,
    )
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        delivery = await request_password_reset(repo, app_state.settings, email=body.email)
    if delivery is not None:
        await app_state.email_provider.send(
            to=delivery.to,
            template_key=delivery.template_key,
            subject=delivery.subject,
            text_body=delivery.text_body,
        )
    return {"detail": "If that account exists, a reset link has been sent."}


@router.post("/auth/password-reset/confirm")
async def password_reset_confirm_endpoint(
    body: PasswordResetConfirmRequest,
    response: Response,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> UserOut:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        result = await confirm_password_reset(
            repo,
            app_state.settings,
            raw_token=body.token,
            new_password=body.new_password,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent"),
        )
    _set_session_cookie(response, app_state, result.raw_session_token)
    return UserOut.model_validate(result.user)


@me_router.get("")
async def get_me_endpoint(
    session: AsyncSession = Depends(get_user_scoped_session),
    user: AuthenticatedUser = Depends(require_session),
) -> UserOut:
    repo = IdentityRepository(session)
    current = await repo.get_user_by_id(user.id)
    assert current is not None
    return UserOut.model_validate(current)


@me_router.patch("")
async def update_me_endpoint(
    body: UpdateProfileRequest,
    session: AsyncSession = Depends(get_user_scoped_session),
    user: AuthenticatedUser = Depends(require_session),
) -> UserOut:
    repo = IdentityRepository(session)
    current = await repo.get_user_by_id(user.id, for_update=True)
    assert current is not None
    if body.full_name is not None:
        current.full_name = body.full_name
    if body.timezone is not None:
        current.timezone = body.timezone
    return UserOut.model_validate(current)


@me_router.post("/password")
async def change_password_endpoint(
    body: ChangePasswordRequest,
    response: Response,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> UserOut:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        result = await change_password(
            repo,
            app_state.settings,
            user_id=user.id,
            current_password=body.current_password,
            new_password=body.new_password,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent"),
        )
    _set_session_cookie(response, app_state, result.raw_session_token)
    return UserOut.model_validate(result.user)


@me_router.post("/email", status_code=status.HTTP_202_ACCEPTED)
async def request_email_change_endpoint(
    body: EmailChangeRequest,
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
) -> dict[str, str]:
    async with user_session(app_state.session_factory, user.id) as session:
        repo = IdentityRepository(session)
        deliveries = await request_email_change(
            repo, app_state.settings, user_id=user.id, new_email=body.new_email
        )
    if deliveries is not None:
        for delivery in deliveries:
            await app_state.email_provider.send(
                to=delivery.to,
                template_key=delivery.template_key,
                subject=delivery.subject,
                text_body=delivery.text_body,
            )
    return {"detail": "Check the new address to confirm the email change."}


@router.post("/auth/email-change/confirm")
async def confirm_email_change_endpoint(
    body: ConfirmEmailChangeRequest,
    response: Response,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_client_ip_hash),
) -> UserOut:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        result = await confirm_email_change(
            repo,
            app_state.settings,
            raw_token=body.token,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent"),
        )
    await app_state.email_provider.send(
        to=result.notification.to,
        template_key=result.notification.template_key,
        subject=result.notification.subject,
        text_body=result.notification.text_body,
    )
    _set_session_cookie(response, app_state, result.auth.raw_session_token)
    return UserOut.model_validate(result.auth.user)


@me_router.get("/sessions")
async def list_my_sessions_endpoint(
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
) -> list[SessionOut]:
    async with app_state.session_factory() as session:
        repo = IdentityRepository(session)
        sessions = await repo.list_active_sessions(user.id)
    return [SessionOut.model_validate(s) for s in sessions]


@me_router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_session_endpoint(
    session_id: UUID,
    response: Response,
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
) -> None:
    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        session_row = await repo.get_session_by_id(user.id, session_id)
        if session_row is None:
            return
        await logout(repo, session_id=session_row.id)
    if str(session_row.id) == str(user.session_id):
        _clear_session_cookie(response, app_state)
