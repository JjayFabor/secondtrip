from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.settings import Settings
from app.modules.detection.defaults import DEFAULT_SIGNAL_KEYS
from app.modules.detection.models import DetectionRule, DetectionRuleSet
from app.modules.detection.service import ensure_default_rule_set
from app.modules.identity.models import User, UserStatus
from app.modules.organizations.models import Organization, OrganizationMembership


async def test_migration_seeded_catalogue_and_complete_rule_sets(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as connection:
        keys = set(
            (
                await connection.execute(
                    text("SELECT key FROM detection_signal_definitions ORDER BY key")
                )
            )
            .scalars()
            .all()
        )
        incomplete_rule_sets = (
            await connection.execute(
                text(
                    "SELECT detection_rule_sets.id "
                    "FROM detection_rule_sets "
                    "LEFT JOIN detection_rules ON "
                    "detection_rules.rule_set_id = detection_rule_sets.id "
                    "GROUP BY detection_rule_sets.id "
                    "HAVING count(detection_rules.id) <> :expected_count"
                ),
                {"expected_count": len(DEFAULT_SIGNAL_KEYS)},
            )
        ).all()

    assert keys == DEFAULT_SIGNAL_KEYS
    assert incomplete_rule_sets == []


async def test_new_organization_default_rule_set_is_idempotent(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    user_id = uuid4()
    organization_id = uuid4()
    factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    id=user_id,
                    email=f"detection-defaults-{user_id}@example.test",
                    full_name="Detection Defaults",
                    status=UserStatus.ACTIVE.value,
                )
            )
            session.add(
                Organization(
                    id=organization_id,
                    name="Detection Defaults",
                    slug=f"detection-defaults-{organization_id}",
                    created_by_user_id=user_id,
                )
            )
            await session.flush()
            session.add(
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=user_id,
                    role="owner",
                )
            )

            first = await ensure_default_rule_set(
                session,
                settings,
                organization_id=organization_id,
                created_by_user_id=user_id,
            )
            second = await ensure_default_rule_set(
                session,
                settings,
                organization_id=organization_id,
                created_by_user_id=user_id,
            )
            rule_count = await session.scalar(
                select(func.count())
                .select_from(DetectionRule)
                .where(DetectionRule.rule_set_id == first.id)
            )
            active_count = await session.scalar(
                select(func.count())
                .select_from(DetectionRuleSet)
                .where(
                    DetectionRuleSet.organization_id == organization_id,
                    DetectionRuleSet.is_active.is_(True),
                )
            )

            assert first.id == second.id
            assert rule_count == len(DEFAULT_SIGNAL_KEYS)
            assert active_count == 1
    finally:
        async with owner_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM organizations WHERE id = :organization_id"),
                {"organization_id": organization_id},
            )
            await connection.execute(
                text("DELETE FROM users WHERE id = :user_id"),
                {"user_id": user_id},
            )
