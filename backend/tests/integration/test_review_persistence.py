from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.errors import ConflictError
from app.core.security import hash_token, new_bearer_token
from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.main import create_app
from app.modules.audit.models import AuditEvent
from app.modules.customers import models as customer_models
from app.modules.detection.models import (
    CandidateSignal,
    DetectionRun,
    ReworkCandidate,
    ReworkCategory,
    ReworkReview,
    RootCause,
)
from app.modules.detection.repository import DetectionRepository
from app.modules.detection.reviews import (
    CATEGORY_DEFAULTS,
    ROOT_CAUSE_DEFAULTS,
    ensure_review_taxonomy,
    record_review,
)
from app.modules.detection.schemas import (
    CandidateSort,
    CandidateWorkflowStatus,
    DetectionRunStatus,
    DetectionTrigger,
    ReviewDecision,
    RuleKind,
    ScoreBand,
    SignalOutcome,
)
from app.modules.detection.service import ensure_default_rule_set
from app.modules.identity.models import User, UserSession, UserStatus
from app.modules.imports import models as import_models
from app.modules.jobs.models import Job, SourceSystem, SourceSystemKind
from app.modules.jobs.schemas import JobStatus
from app.modules.organizations.models import Organization, OrganizationMembership
from app.modules.workforce import models as workforce_models
from seeds.runtime import ensure_principal, remove_principal

_MODEL_DEPENDENCIES = (customer_models, import_models, workforce_models)


async def _arrange_candidate(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> tuple[UUID, UUID, UUID]:
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        unique = uuid4()
        user = User(
            email=f"review-{unique}@example.test",
            full_name="Review Manager",
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()
        organization = Organization(
            name="Review Persistence",
            slug=f"review-persistence-{unique}",
            created_by_user_id=user.id,
        )
        session.add(organization)
        await session.flush()
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
            )
        )
        source = SourceSystem(
            organization_id=organization.id,
            kind=SourceSystemKind.CSV_UPLOAD,
            name="Review test source",
        )
        session.add(source)
        await session.flush()
        prior = Job(
            organization_id=organization.id,
            source_system_id=source.id,
            natural_key_hash=f"review-prior-{unique}".encode(),
            status=JobStatus.COMPLETED,
            service_date=date(2026, 9, 1),
            currency_code="USD",
        )
        followup = Job(
            organization_id=organization.id,
            source_system_id=source.id,
            natural_key_hash=f"review-followup-{unique}".encode(),
            status=JobStatus.COMPLETED,
            service_date=date(2026, 9, 5),
            currency_code="USD",
        )
        session.add_all([prior, followup])
        await session.flush()
        rule_set = await ensure_default_rule_set(
            session,
            settings,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )
        await ensure_review_taxonomy(session, organization_id=organization.id)
        detection_run = DetectionRun(
            organization_id=organization.id,
            rule_set_id=rule_set.id,
            trigger=DetectionTrigger.MANUAL,
            status=DetectionRunStatus.COMPLETED,
        )
        session.add(detection_run)
        await session.flush()
        candidate = ReworkCandidate(
            organization_id=organization.id,
            prior_job_id=prior.id,
            followup_job_id=followup.id,
            days_between=4,
            current_score=Decimal("82.50"),
            current_normalized_score=Decimal("82.50"),
            score_band=ScoreBand.HIGH,
            current_rule_set_id=rule_set.id,
            current_detection_run_id=detection_run.id,
        )
        session.add(candidate)
        await session.flush()
        session.add_all(
            [
                CandidateSignal(
                    organization_id=organization.id,
                    candidate_id=candidate.id,
                    detection_run_id=detection_run.id,
                    signal_key="same_customer",
                    rule_kind=RuleKind.ADDITIVE,
                    outcome=SignalOutcome.MATCHED,
                    strength=Decimal("1"),
                    raw_value={"matched": True},
                    weight_applied=Decimal("20"),
                    contribution=Decimal("20"),
                    explanation="Same customer.",
                ),
                CandidateSignal(
                    organization_id=organization.id,
                    candidate_id=candidate.id,
                    detection_run_id=detection_run.id,
                    signal_key="within_equipment_warranty",
                    rule_kind=RuleKind.ADDITIVE,
                    outcome=SignalOutcome.NOT_EVALUABLE,
                    strength=Decimal("0"),
                    raw_value=None,
                    weight_applied=Decimal("10"),
                    contribution=Decimal("0"),
                    explanation="No equipment warranty date was recorded.",
                ),
            ]
        )
        return organization.id, user.id, candidate.id


async def _cleanup(
    owner_engine: AsyncEngine,
    organization_id: UUID,
    user_id: UUID,
    *additional_user_ids: UUID,
) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(delete(Organization).where(Organization.id == organization_id))
        await connection.execute(delete(User).where(User.id.in_((user_id, *additional_user_ids))))


async def test_review_taxonomy_is_complete_and_idempotent_for_new_organization(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    organization_id, user_id, _ = await _arrange_candidate(owner_engine, settings)
    try:
        async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
            first_categories, first_root_causes = await ensure_review_taxonomy(
                session, organization_id=organization_id
            )
            second_categories, second_root_causes = await ensure_review_taxonomy(
                session, organization_id=organization_id
            )

        assert len(first_categories) == len(second_categories) == len(CATEGORY_DEFAULTS)
        assert len(first_root_causes) == len(second_root_causes) == len(ROOT_CAUSE_DEFAULTS)
        assert {category.key for category in first_categories} == {
            default.key for default in CATEGORY_DEFAULTS
        }
        assert {root_cause.key for root_cause in first_root_causes} == {
            key for key, _ in ROOT_CAUSE_DEFAULTS
        }
    finally:
        await _cleanup(owner_engine, organization_id, user_id)


async def test_migration_seeded_complete_taxonomy_for_existing_organizations(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as connection:
        incomplete_categories = (
            await connection.execute(
                select(Organization.id)
                .outerjoin(
                    ReworkCategory,
                    ReworkCategory.organization_id == Organization.id,
                )
                .group_by(Organization.id)
                .having(func.count(ReworkCategory.id) != len(CATEGORY_DEFAULTS))
            )
        ).all()
        incomplete_root_causes = (
            await connection.execute(
                select(Organization.id)
                .outerjoin(RootCause, RootCause.organization_id == Organization.id)
                .group_by(Organization.id)
                .having(func.count(RootCause.id) != len(ROOT_CAUSE_DEFAULTS))
            )
        ).all()

    assert incomplete_categories == []
    assert incomplete_root_causes == []


async def test_local_seed_principal_receives_review_taxonomy(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    unique = uuid4()
    owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    principal = await ensure_principal(
        owner_factory,
        settings,
        email=f"review-seed-{unique}@example.test",
        password="Review-seed-2026!",
        organization_name="Review Seed",
        organization_slug=f"review-seed-{unique}",
        plan_key="pro",
    )
    try:
        async with AsyncSession(owner_engine) as session:
            category_count = await session.scalar(
                select(func.count())
                .select_from(ReworkCategory)
                .where(ReworkCategory.organization_id == principal.organization_id)
            )
            root_cause_count = await session.scalar(
                select(func.count())
                .select_from(RootCause)
                .where(RootCause.organization_id == principal.organization_id)
            )
        assert category_count == len(CATEGORY_DEFAULTS)
        assert root_cause_count == len(ROOT_CAUSE_DEFAULTS)
    finally:
        await remove_principal(owner_factory, principal)


async def test_reclassification_appends_history_and_only_links_the_old_review(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    settings: Settings,
) -> None:
    organization_id, user_id, candidate_id = await _arrange_candidate(owner_engine, settings)
    factory = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    tenant = TenantContext(
        organization_id=organization_id,
        actor_user_id=user_id,
        request_id="review-persistence-test",
    )
    try:
        async with tenant_session(factory, tenant) as session:
            confirmed_category = await session.scalar(
                select(ReworkCategory).where(ReworkCategory.key == "confirmed_callback")
            )
            workmanship = await session.scalar(
                select(RootCause).where(RootCause.key == "workmanship")
            )
            assert confirmed_category is not None
            assert workmanship is not None
            first = await record_review(
                session,
                organization_id=organization_id,
                candidate_id=candidate_id,
                decision=ReviewDecision.CONFIRMED,
                category_id=confirmed_category.id,
                root_cause_id=workmanship.id,
                note="Return visit confirmed.",
                reviewed_by_user_id=user_id,
                reviewer_label="Review Manager",
                request_id=tenant.request_id,
            )
            first_id = first.id

        async with tenant_session(factory, tenant) as session:
            unrelated = await session.scalar(
                select(ReworkCategory).where(ReworkCategory.key == "unrelated")
            )
            assert unrelated is not None
            second = await record_review(
                session,
                organization_id=organization_id,
                candidate_id=candidate_id,
                decision=ReviewDecision.REJECTED,
                category_id=unrelated.id,
                root_cause_id=None,
                note="Different problem after inspection.",
                reviewed_by_user_id=user_id,
                reviewer_label="Review Manager",
                request_id=tenant.request_id,
            )
            second_id = second.id

        async with AsyncSession(owner_engine) as session:
            reviews = list(
                (
                    await session.execute(
                        select(ReworkReview)
                        .where(ReworkReview.candidate_id == candidate_id)
                        .order_by(ReworkReview.created_at)
                    )
                )
                .scalars()
                .all()
            )
            candidate = await session.get(ReworkCandidate, candidate_id)
            current_count = await session.scalar(
                select(func.count())
                .select_from(ReworkReview)
                .where(
                    ReworkReview.candidate_id == candidate_id,
                    ReworkReview.superseded_by_review_id.is_(None),
                )
            )
            audit_count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.action == "candidate.reviewed",
                )
            )

        assert [review.id for review in reviews] == [first_id, second_id]
        assert reviews[0].decision is ReviewDecision.CONFIRMED
        assert reviews[0].superseded_by_review_id == second_id
        assert reviews[1].decision is ReviewDecision.REJECTED
        assert reviews[1].superseded_by_review_id is None
        assert reviews[0].score_at_review == reviews[1].score_at_review == Decimal("82.50")
        assert candidate is not None
        assert candidate.workflow_status is CandidateWorkflowStatus.REVIEWED
        assert current_count == 1
        assert audit_count == 2

        async with owner_engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(DBAPIError):
                    await connection.execute(
                        delete(ReworkCategory).where(ReworkCategory.id == unrelated.id)
                    )
            finally:
                await transaction.rollback()
    finally:
        await _cleanup(owner_engine, organization_id, user_id)


async def test_review_choice_must_match_category_outcome(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    settings: Settings,
) -> None:
    organization_id, user_id, candidate_id = await _arrange_candidate(owner_engine, settings)
    factory = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    tenant = TenantContext(organization_id=organization_id, actor_user_id=user_id)
    try:
        with pytest.raises(ConflictError, match="category outcome"):
            async with tenant_session(factory, tenant) as session:
                unrelated = await session.scalar(
                    select(ReworkCategory).where(ReworkCategory.key == "unrelated")
                )
                assert unrelated is not None
                await record_review(
                    session,
                    organization_id=organization_id,
                    candidate_id=candidate_id,
                    decision=ReviewDecision.CONFIRMED,
                    category_id=unrelated.id,
                    root_cause_id=None,
                    note=None,
                    reviewed_by_user_id=user_id,
                    reviewer_label="Review Manager",
                )
    finally:
        await _cleanup(owner_engine, organization_id, user_id)


async def test_candidate_queue_cursor_filters_and_sorting(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    settings: Settings,
) -> None:
    organization_id, user_id, first_candidate_id = await _arrange_candidate(owner_engine, settings)
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        first_candidate = await session.get(ReworkCandidate, first_candidate_id)
        assert first_candidate is not None
        prior_job = await session.get(Job, first_candidate.prior_job_id)
        assert prior_job is not None
        followup = Job(
            organization_id=organization_id,
            source_system_id=prior_job.source_system_id,
            natural_key_hash=f"review-filter-{uuid4()}".encode(),
            status=JobStatus.COMPLETED,
            service_date=date(2026, 9, 10),
            currency_code="USD",
        )
        session.add(followup)
        await session.flush()
        second_candidate = ReworkCandidate(
            organization_id=organization_id,
            prior_job_id=prior_job.id,
            followup_job_id=followup.id,
            days_between=9,
            current_score=Decimal("60"),
            current_normalized_score=Decimal("60"),
            score_band=ScoreBand.MEDIUM,
            current_rule_set_id=first_candidate.current_rule_set_id,
            current_detection_run_id=first_candidate.current_detection_run_id,
        )
        session.add(second_candidate)
        await session.flush()
        second_candidate_id = second_candidate.id

    factory = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    tenant = TenantContext(organization_id=organization_id, actor_user_id=user_id)
    common: dict[str, Any] = {
        "min_score": None,
        "band": None,
        "workflow_status": CandidateWorkflowStatus.OPEN,
        "include_suppressed": False,
        "customer_id": None,
        "equipment_id": None,
        "technician_id": None,
        "date_from": None,
        "date_to": None,
    }
    try:
        async with tenant_session(factory, tenant) as session:
            repository = DetectionRepository(session, tenant)
            first_page, cursor = await repository.list_candidates(
                **common,
                sort=CandidateSort.SCORE,
                cursor=None,
                limit=1,
            )
            assert [row.candidate.id for row in first_page] == [first_candidate_id]
            assert cursor is not None
            second_page, next_cursor = await repository.list_candidates(
                **common,
                sort=CandidateSort.SCORE,
                cursor=cursor,
                limit=1,
            )
            assert [row.candidate.id for row in second_page] == [second_candidate_id]
            assert next_cursor is None

            medium_rows, _ = await repository.list_candidates(
                **(common | {"band": ScoreBand.MEDIUM}),
                sort=CandidateSort.SCORE,
                cursor=None,
                limit=10,
            )
            assert [row.candidate.id for row in medium_rows] == [second_candidate_id]

            dated_rows, _ = await repository.list_candidates(
                **(common | {"date_from": date(2026, 9, 10)}),
                sort=CandidateSort.SCORE,
                cursor=None,
                limit=10,
            )
            assert [row.candidate.id for row in dated_rows] == [second_candidate_id]

            days_rows, _ = await repository.list_candidates(
                **common,
                sort=CandidateSort.DAYS_BETWEEN,
                cursor=None,
                limit=10,
            )
            assert [row.candidate.id for row in days_rows] == [
                second_candidate_id,
                first_candidate_id,
            ]
    finally:
        await _cleanup(owner_engine, organization_id, user_id)


async def test_review_api_lists_taxonomy_and_exposes_reclassification_history(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    organization_id, user_id, candidate_id = await _arrange_candidate(owner_engine, settings)
    raw_session = new_bearer_token()
    member_raw_session = new_bearer_token()
    now = datetime.now(UTC)
    async with AsyncSession(owner_engine) as session, session.begin():
        member = User(
            email=f"review-member-{uuid4()}@example.test",
            full_name="Review Member",
            status=UserStatus.ACTIVE.value,
        )
        session.add(member)
        await session.flush()
        member_id = member.id
        session.add_all(
            [
                UserSession(
                    user_id=user_id,
                    token_hash=hash_token(raw_session),
                    issued_at=now,
                    expires_at=now + timedelta(days=1),
                    last_seen_at=now,
                ),
                UserSession(
                    user_id=member_id,
                    token_hash=hash_token(member_raw_session),
                    issued_at=now,
                    expires_at=now + timedelta(days=1),
                    last_seen_at=now,
                ),
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=member_id,
                    role="member",
                ),
            ]
        )

    try:
        app = create_app()
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with (
                httpx.AsyncClient(transport=transport, base_url="http://test") as client,
                httpx.AsyncClient(transport=transport, base_url="http://test") as member_client,
            ):
                client.cookies.set(settings.session_cookie_name, raw_session)
                assert (await client.get("/health")).status_code == 200
                csrf = client.cookies.get(settings.csrf_cookie_name)
                assert csrf is not None
                write_headers = {
                    "Origin": settings.frontend_url,
                    "X-CSRF-Token": csrf,
                }
                org_path = f"/api/v1/orgs/{organization_id}"

                member_client.cookies.set(settings.session_cookie_name, member_raw_session)
                assert (await member_client.get("/health")).status_code == 200
                member_csrf = member_client.cookies.get(settings.csrf_cookie_name)
                assert member_csrf is not None

                categories_response = await client.get(f"{org_path}/settings/categories")
                root_causes_response = await client.get(f"{org_path}/settings/root-causes")
                queue_response = await client.get(f"{org_path}/rework", params={"limit": 1})
                detail_response = await client.get(f"{org_path}/rework/{candidate_id}")
                assert categories_response.status_code == 200
                assert root_causes_response.status_code == 200
                assert queue_response.status_code == 200
                assert detail_response.status_code == 200
                categories = categories_response.json()
                root_causes = root_causes_response.json()
                queue = queue_response.json()
                detail = detail_response.json()
                assert len(categories) == len(CATEGORY_DEFAULTS)
                assert len(root_causes) == len(ROOT_CAUSE_DEFAULTS)
                assert [row["id"] for row in queue["data"]] == [str(candidate_id)]
                assert queue["data"][0]["score"] == "82.50"
                assert queue["data"][0]["prior_job"]["service_date"] == "2026-09-01"
                assert queue["data"][0]["followup_job"]["service_date"] == "2026-09-05"
                assert [signal["key"] for signal in detail["signals"]] == [
                    "same_customer",
                    "within_equipment_warranty",
                ]
                assert detail["signals"][1]["outcome"] == "not_evaluable"
                malformed_cursor = await client.get(
                    f"{org_path}/rework", params={"cursor": "not-a-cursor"}
                )
                assert malformed_cursor.status_code == 422
                assert malformed_cursor.json()["code"] == "INVALID_CURSOR"
                assert (
                    await member_client.get(f"{org_path}/settings/categories")
                ).status_code == 200
                member_review_response = await member_client.post(
                    f"{org_path}/rework/{candidate_id}/review",
                    headers={
                        "Origin": settings.frontend_url,
                        "X-CSRF-Token": member_csrf,
                    },
                    json={"decision": "uncertain"},
                )
                assert member_review_response.status_code == 403
                confirmed_category_id = next(
                    row["id"] for row in categories if row["key"] == "confirmed_callback"
                )
                workmanship_id = next(
                    row["id"] for row in root_causes if row["key"] == "workmanship"
                )
                unrelated_id = next(row["id"] for row in categories if row["key"] == "unrelated")

                first_response = await client.post(
                    f"{org_path}/rework/{candidate_id}/review",
                    headers=write_headers,
                    json={
                        "decision": "confirmed",
                        "category_id": confirmed_category_id,
                        "root_cause_id": workmanship_id,
                        "note": "Confirmed through the API.",
                    },
                )
                assert first_response.status_code == 201
                first = first_response.json()

                second_response = await client.post(
                    f"{org_path}/rework/{candidate_id}/review",
                    headers=write_headers,
                    json={
                        "decision": "rejected",
                        "category_id": unrelated_id,
                        "note": "Reclassified through the API.",
                    },
                )
                assert second_response.status_code == 201
                second = second_response.json()

                history_response = await client.get(f"{org_path}/rework/{candidate_id}/reviews")
                assert history_response.status_code == 200
                history = history_response.json()
                assert [row["id"] for row in history] == [second["id"], first["id"]]
                assert history[0]["superseded_by_review_id"] is None
                assert history[1]["superseded_by_review_id"] == second["id"]
                reviewed_queue_response = await client.get(
                    f"{org_path}/rework", params={"status": "reviewed"}
                )
                reviewed_detail_response = await client.get(f"{org_path}/rework/{candidate_id}")
                assert reviewed_queue_response.status_code == 200
                assert (
                    reviewed_queue_response.json()["data"][0]["current_review"]["id"]
                    == second["id"]
                )
                assert reviewed_detail_response.status_code == 200
                assert reviewed_detail_response.json()["current_review"]["id"] == second["id"]
    finally:
        await _cleanup(owner_engine, organization_id, user_id, member_id)
