"""Proof that the live database enforces tenant isolation.

These tests use raw SQL through the actual ``secondtrip_app`` role. They do
not exercise the ORM or a mocked connection, so a passing test proves the
Postgres mechanism rather than Python code that assumes the mechanism works.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(autouse=True)
async def _clean_tables(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    async def clean() -> None:
        async with owner_engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE audit_events, organization_invitations, "
                    "organization_memberships, organizations, user_credentials, users CASCADE"
                )
            )

    await clean()
    try:
        yield
    finally:
        await clean()


async def _seed_two_tenants(
    owner_engine: AsyncEngine,
) -> tuple[UUID, UUID, UUID, UUID]:
    user_a, user_b = uuid4(), uuid4()
    org_a, org_b = uuid4(), uuid4()

    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, full_name, status) "
                "VALUES (:user_a, 'rls-a@example.test', 'RLS A', 'active'), "
                "       (:user_b, 'rls-b@example.test', 'RLS B', 'active')"
            ),
            {"user_a": user_a, "user_b": user_b},
        )
        await conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_by_user_id) "
                "VALUES (:org_a, 'RLS A', 'rls-a', :user_a), "
                "       (:org_b, 'RLS B', 'rls-b', :user_b)"
            ),
            {"org_a": org_a, "org_b": org_b, "user_a": user_a, "user_b": user_b},
        )
        await conn.execute(
            text(
                "INSERT INTO organization_memberships "
                "(organization_id, user_id, role) "
                "VALUES (:org_a, :user_a, 'owner'), (:org_b, :user_b, 'owner')"
            ),
            {"org_a": org_a, "org_b": org_b, "user_a": user_a, "user_b": user_b},
        )
        await conn.execute(
            text(
                "INSERT INTO audit_events "
                "(organization_id, actor_type, actor_user_id, actor_label, action, summary) "
                "VALUES (:org_a, 'user', :user_a, 'RLS A', 'test', 'a-row'), "
                "       (:org_b, 'user', :user_b, 'RLS B', 'test', 'b-row')"
            ),
            {"org_a": org_a, "org_b": org_b, "user_a": user_a, "user_b": user_b},
        )
        await conn.execute(
            text(
                "INSERT INTO organization_invitations "
                "(organization_id, email, role, token_hash, invited_by_user_id, expires_at) "
                "VALUES (:org_a, 'rls-a@example.test', 'member', 'hash-a', :user_a, "
                "        now() + interval '1 hour'), "
                "       (:org_b, 'rls-b@example.test', 'member', 'hash-b', :user_b, "
                "        now() + interval '1 hour')"
            ),
            {"org_a": org_a, "org_b": org_b, "user_a": user_a, "user_b": user_b},
        )

    return org_a, org_b, user_a, user_b


async def test_app_role_only_sees_its_own_tenant(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    org_a, _org_b, _user_a, _user_b = await _seed_two_tenants(owner_engine)

    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"),
            {"org": str(org_a)},
        )
        rows = (await conn.execute(text("SELECT summary FROM audit_events"))).scalars().all()

    assert rows == ["a-row"]


async def test_app_role_cannot_write_into_another_tenant(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    org_a, org_b, _user_a, _user_b = await _seed_two_tenants(owner_engine)

    with pytest.raises(DBAPIError):
        async with app_engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(org_a)},
            )
            await conn.execute(
                text(
                    "INSERT INTO audit_events "
                    "(organization_id, actor_type, actor_label, action, summary) "
                    "VALUES (:org, 'system', 'test', 'forged', 'forged')"
                ),
                {"org": org_b},
            )


async def test_missing_tenant_context_returns_zero_rows_not_an_error(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await _seed_two_tenants(owner_engine)

    async with app_engine.connect() as conn:
        rows = (await conn.execute(text("SELECT summary FROM audit_events"))).scalars().all()

    assert rows == []


async def test_explicitly_cleared_context_also_returns_zero_rows_not_an_error(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await _seed_two_tenants(owner_engine)

    async with app_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.current_org_id', NULL, true)"))
        rows = (await conn.execute(text("SELECT summary FROM audit_events"))).scalars().all()

    assert rows == []


async def test_owner_role_bypasses_rls_which_is_why_the_app_never_uses_it(
    owner_engine: AsyncEngine,
) -> None:
    await _seed_two_tenants(owner_engine)

    async with owner_engine.connect() as conn:
        rows = (await conn.execute(text("SELECT summary FROM audit_events"))).scalars().all()

    assert set(rows) == {"a-row", "b-row"}


async def test_self_membership_discovery_is_select_only(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    _org_a, _org_b, user_a, _user_b = await _seed_two_tenants(owner_engine)

    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_a)},
        )
        rows = (
            (
                await conn.execute(
                    text("SELECT user_id FROM organization_memberships ORDER BY organization_id")
                )
            )
            .scalars()
            .all()
        )

    assert rows == [user_a]

    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_a)},
        )
        result = await conn.execute(
            text("DELETE FROM organization_memberships WHERE user_id = :user_id"),
            {"user_id": user_a},
        )

    assert result.rowcount == 0
    async with owner_engine.connect() as conn:
        membership_count = (
            await conn.execute(text("SELECT count(*) FROM organization_memberships"))
        ).scalar_one()
    assert membership_count == 2


async def test_invitation_token_lookup_is_select_only(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    org_a, _org_b, _user_a, _user_b = await _seed_two_tenants(owner_engine)

    async with app_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.lookup_token_hash', 'hash-a', true)"))
        rows = (
            (await conn.execute(text("SELECT organization_id FROM organization_invitations")))
            .scalars()
            .all()
        )

    assert rows == [org_a]

    async with app_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.lookup_token_hash', 'hash-a', true)"))
        result = await conn.execute(
            text("DELETE FROM organization_invitations WHERE token_hash = 'hash-a'")
        )

    assert result.rowcount == 0
    async with owner_engine.connect() as conn:
        invitation_count = (
            await conn.execute(text("SELECT count(*) FROM organization_invitations"))
        ).scalar_one()
    assert invitation_count == 2


async def test_pending_invitations_are_visible_only_to_the_invited_user(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    _org_a, _org_b, user_a, _user_b = await _seed_two_tenants(owner_engine)

    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_a)},
        )
        rows = (
            (
                await conn.execute(
                    text("SELECT token_hash FROM organization_invitations ORDER BY token_hash")
                )
            )
            .scalars()
            .all()
        )

    assert rows == ["hash-a"]


async def test_database_rejects_removing_the_last_active_owner(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    org_a, _org_b, user_a, _user_b = await _seed_two_tenants(owner_engine)

    with pytest.raises(DBAPIError):
        async with app_engine.begin() as conn:
            await conn.execute(
                text(
                    "SELECT set_config('app.current_org_id', :org_id, true), "
                    "set_config('app.current_user_id', :user_id, true)"
                ),
                {"org_id": str(org_a), "user_id": str(user_a)},
            )
            await conn.execute(
                text(
                    "UPDATE organization_memberships "
                    "SET revoked_at = now() "
                    "WHERE organization_id = :org_id AND user_id = :user_id"
                ),
                {"org_id": org_a, "user_id": user_a},
            )

    async with owner_engine.connect() as conn:
        revoked_at = (
            await conn.execute(
                text(
                    "SELECT revoked_at FROM organization_memberships "
                    "WHERE organization_id = :org_id AND user_id = :user_id"
                ),
                {"org_id": org_a, "user_id": user_a},
            )
        ).scalar_one()
    assert revoked_at is None
