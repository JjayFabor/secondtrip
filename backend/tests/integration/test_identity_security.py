from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from asgi_lifespan import LifespanManager
from fastapi.routing import APIRoute, APIRouter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.v1.router import api_v1_router
from app.core.security import hash_password, hash_token, new_bearer_token
from app.core.settings import Settings
from app.main import create_app
from app.modules.identity.models import (
    PasswordResetToken,
    User,
    UserCredentials,
    UserSession,
    UserStatus,
)
from app.modules.organizations.models import Organization, OrganizationMembership


@dataclass(frozen=True, slots=True)
class SeededUser:
    id: UUID
    raw_sessions: tuple[str, ...]
    session_ids: tuple[UUID, ...]


@asynccontextmanager
async def _client_group(count: int) -> AsyncIterator[list[httpx.AsyncClient]]:
    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        clients = [
            httpx.AsyncClient(transport=transport, base_url="http://test")
            for _ in range(count)
        ]
        try:
            yield clients
        finally:
            for client in clients:
                await client.aclose()


async def _seed_user(
    session: AsyncSession,
    *,
    label: str,
    session_count: int = 1,
    password: str | None = None,
) -> SeededUser:
    now = datetime.now(UTC)
    user = User(
        email=f"{label}-{uuid4()}@example.test",
        full_name=label,
        status=UserStatus.ACTIVE.value,
        email_verified_at=now,
    )
    session.add(user)
    await session.flush()
    if password is not None:
        session.add(UserCredentials(user_id=user.id, password_hash=hash_password(password)))

    raw_sessions = tuple(new_bearer_token() for _ in range(session_count))
    rows = [
        UserSession(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            issued_at=now,
            expires_at=now + timedelta(days=30),
            last_seen_at=now,
        )
        for raw_token in raw_sessions
    ]
    session.add_all(rows)
    await session.flush()
    return SeededUser(
        id=user.id,
        raw_sessions=raw_sessions,
        session_ids=tuple(row.id for row in rows),
    )


async def _seed_organization(
    session: AsyncSession,
    *,
    owner_id: UUID,
    member_id: UUID | None = None,
) -> Organization:
    unique = uuid4()
    organization = Organization(
        name=f"Security {unique}",
        slug=f"security-{unique}",
        created_by_user_id=owner_id,
    )
    session.add(organization)
    await session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=owner_id,
            role="owner",
        )
    )
    if member_id is not None:
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=member_id,
                role="member",
            )
        )
    await session.flush()
    return organization


async def _set_auth(
    client: httpx.AsyncClient,
    settings: Settings,
    raw_session: str,
) -> dict[str, str]:
    client.cookies.set(settings.session_cookie_name, raw_session)
    response = await client.get("/health")
    assert response.status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)
    assert csrf is not None
    return {"Origin": settings.frontend_url, "X-CSRF-Token": csrf}


async def _cleanup(
    owner_engine: AsyncEngine,
    *,
    organization_ids: tuple[UUID, ...] = (),
    user_ids: tuple[UUID, ...],
) -> None:
    async with AsyncSession(owner_engine) as session, session.begin():
        if organization_ids:
            await session.execute(
                delete(Organization).where(Organization.id.in_(organization_ids))
            )
        await session.execute(delete(User).where(User.id.in_(user_ids)))


async def test_password_reset_revokes_every_existing_session(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    old_password = "Old-password-2026!"
    reset_token = new_bearer_token()
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        user = await _seed_user(
            session,
            label="password-reset",
            session_count=2,
            password=old_password,
        )
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(reset_token),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    try:
        async with _client_group(3) as clients:
            reset_client, old_client_a, old_client_b = clients
            headers = await _set_auth(reset_client, settings, user.raw_sessions[0])
            response = await reset_client.post(
                "/api/v1/auth/password-reset/confirm",
                headers=headers,
                json={"token": reset_token, "new_password": "New-password-2026!"},
            )
            assert response.status_code == 200

            for client, raw_session in zip(
                (old_client_a, old_client_b), user.raw_sessions, strict=True
            ):
                client.cookies.set(settings.session_cookie_name, raw_session)
                assert (await client.get("/api/v1/me")).status_code == 401

            assert (await reset_client.get("/api/v1/me")).status_code == 200

        async with AsyncSession(owner_engine) as session:
            revoked_at = list(
                (
                    await session.execute(
                        select(UserSession.revoked_at).where(
                            UserSession.id.in_(user.session_ids)
                        )
                    )
                ).scalars()
            )
            active_count = len(
                (
                    await session.execute(
                        select(UserSession.id).where(
                            UserSession.user_id == user.id,
                            UserSession.revoked_at.is_(None),
                        )
                    )
                ).all()
            )
        assert all(value is not None for value in revoked_at)
        assert active_count == 1
    finally:
        await _cleanup(owner_engine, user_ids=(user.id,))


async def test_membership_revocation_is_immediate_and_last_owner_is_protected(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        owner = await _seed_user(session, label="owner")
        member = await _seed_user(session, label="member")
        organization = await _seed_organization(
            session,
            owner_id=owner.id,
            member_id=member.id,
        )

    try:
        async with _client_group(2) as clients:
            owner_client, member_client = clients
            owner_headers = await _set_auth(owner_client, settings, owner.raw_sessions[0])
            await _set_auth(member_client, settings, member.raw_sessions[0])
            org_path = f"/api/v1/orgs/{organization.id}"

            assert (await member_client.get(org_path)).status_code == 200
            removed = await owner_client.delete(
                f"{org_path}/members/{member.id}", headers=owner_headers
            )
            assert removed.status_code == 204
            assert (await member_client.get(org_path)).status_code == 404

            last_owner = await owner_client.delete(
                f"{org_path}/members/{owner.id}", headers=owner_headers
            )
            assert last_owner.status_code == 409
            assert last_owner.json()["code"] == "LAST_OWNER"
    finally:
        await _cleanup(
            owner_engine,
            organization_ids=(organization.id,),
            user_ids=(owner.id, member.id),
        )


def _walk_routes(router: APIRouter) -> Iterator[APIRoute]:
    for route in router.routes:
        if hasattr(route, "original_router"):
            yield from _walk_routes(route.original_router)
        elif isinstance(route, APIRoute):
            yield route


def _tenant_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in _walk_routes(api_v1_router):
        if "/orgs/{org_id}" not in route.path:
            continue
        methods = route.methods or set()
        assert len(methods) == 1, route.path
        routes.append((next(iter(methods)), route.path))
    return sorted(routes)


def _request_body(method: str, path: str, identifier: UUID) -> dict[str, object] | None:
    if method == "PATCH" and "/members/{user_id}" in path:
        return {"role": "member"}
    if path.endswith("/members/transfer-ownership"):
        return {"to_user_id": str(identifier)}
    if method == "POST" and path.endswith("/invitations"):
        return {"email": f"permission-{uuid4()}@example.test", "role": "member"}
    if method == "POST" and path.endswith("/imports"):
        return {
            "original_filename": "permission-check.csv",
            "source_system_id": str(identifier),
        }
    if path.endswith("/uploaded"):
        return {"allow_duplicate": False}
    if method == "POST" and path.endswith("/review"):
        return {"decision": "uncertain"}
    if method == "PUT" and path.endswith("/mapping"):
        return {
            "version": 1,
            "fields": {
                "service_date": {"source_column": "Date"},
                "customer_name": {"source_column": "Customer"},
            },
            "retain_unmapped": [],
            "skip_rows_where": [],
        }
    return None


async def test_every_tenant_route_hides_another_organization(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        caller = await _seed_user(session, label="tenant-a-member")
        other_owner = await _seed_user(session, label="tenant-b-owner")
        caller_org = await _seed_organization(session, owner_id=caller.id)
        other_org = await _seed_organization(session, owner_id=other_owner.id)

    identifier = uuid4()
    try:
        async with _client_group(1) as clients:
            client = clients[0]
            csrf_headers = await _set_auth(client, settings, caller.raw_sessions[0])
            routes = _tenant_routes()
            assert routes
            for method, template in routes:
                path = "/api/v1" + template.format(
                    org_id=other_org.id,
                    user_id=identifier,
                    invitation_id=identifier,
                    batch_id=identifier,
                    candidate_id=identifier,
                )
                headers = dict(csrf_headers)
                if path.endswith("/commit"):
                    headers["Idempotency-Key"] = str(uuid4())
                response = await client.request(
                    method,
                    path,
                    headers=headers,
                    json=_request_body(method, template, identifier),
                )
                assert response.status_code == 404, (method, template, response.text)
    finally:
        await _cleanup(
            owner_engine,
            organization_ids=(caller_org.id, other_org.id),
            user_ids=(caller.id, other_owner.id),
        )


def _minimum_role(method: str, path: str) -> str:
    if "/members/transfer-ownership" in path:
        return "owner"
    if "/members/{user_id}" in path or "/invitations" in path or "/audit" in path:
        return "admin"
    if "/imports" in path and (
        method in {"POST", "PUT"} or path.endswith("/preview")
    ):
        return "manager"
    if method == "POST" and path.endswith("/review"):
        return "manager"
    return "member"


async def test_permission_gates_are_enforced_for_every_role_and_tenant_route(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    roles = ("member", "manager", "admin", "owner")
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        users = [await _seed_user(session, label=f"permission-{role}") for role in roles]
        organization = await _seed_organization(session, owner_id=users[-1].id)
        session.add_all(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=role,
            )
            for role, user in zip(roles[:-1], users[:-1], strict=True)
        )

    role_rank = {role: rank for rank, role in enumerate(roles)}
    identifier = uuid4()
    try:
        async with _client_group(len(roles)) as clients:
            headers_by_role = {
                role: await _set_auth(client, settings, user.raw_sessions[0])
                for role, user, client in zip(roles, users, clients, strict=True)
            }
            for role, client in zip(roles, clients, strict=True):
                for method, template in _tenant_routes():
                    path = "/api/v1" + template.format(
                        org_id=organization.id,
                        user_id=identifier,
                        invitation_id=identifier,
                        batch_id=identifier,
                        candidate_id=identifier,
                    )
                    headers = dict(headers_by_role[role])
                    if path.endswith("/commit"):
                        headers["Idempotency-Key"] = str(uuid4())
                    response = await client.request(
                        method,
                        path,
                        headers=headers,
                        json=_request_body(method, template, identifier),
                    )
                    minimum = _minimum_role(method, template)
                    allowed = role_rank[role] >= role_rank[minimum]
                    if allowed:
                        assert response.status_code not in {401, 403}, (
                            role,
                            method,
                            template,
                            response.text,
                        )
                    else:
                        assert response.status_code == 403, (
                            role,
                            method,
                            template,
                            response.text,
                        )
    finally:
        await _cleanup(
            owner_engine,
            organization_ids=(organization.id,),
            user_ids=tuple(user.id for user in users),
        )
