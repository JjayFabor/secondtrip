"""Narrow, read-only job projections published for the detection engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.modules.jobs.models import Job, JobLineItem, LineItemKind
from app.modules.jobs.schemas import JobStatus

CANDIDATE_PAIR_QUERY = text(
    """
    WITH scoped AS (
        SELECT id, customer_id, location_id, equipment_id, technician_id, service_date,
               COALESCE(started_at, service_date::timestamptz) AS order_ts
        FROM jobs
        WHERE organization_id = :organization_id
          AND deleted_at IS NULL
          AND status IN ('completed', 'unknown')
          AND service_date BETWEEN
              CAST(:from_date AS date) - CAST(:window_days AS integer)
              AND CAST(:to_date AS date)
    ),
    paired AS (
        SELECT p.id AS prior_job_id,
               f.id AS followup_job_id,
               COALESCE(f.customer_id, p.customer_id) AS customer_id,
               COALESCE(f.location_id, p.location_id) AS location_id,
               COALESCE(f.equipment_id, p.equipment_id) AS equipment_id,
               p.technician_id AS technician_prior_id,
               f.technician_id AS technician_followup_id,
               (f.service_date - p.service_date) AS days_between,
               ROW_NUMBER() OVER (
                   PARTITION BY p.id
                   ORDER BY f.service_date, f.order_ts, f.id
               ) AS fanout_rank
        FROM scoped AS p
        JOIN scoped AS f
          ON (f.customer_id = p.customer_id AND p.customer_id IS NOT NULL)
          OR (f.equipment_id = p.equipment_id AND p.equipment_id IS NOT NULL)
          OR (f.location_id = p.location_id AND p.location_id IS NOT NULL)
        WHERE f.service_date BETWEEN
                  p.service_date AND p.service_date + CAST(:window_days AS integer)
          AND (f.service_date, f.order_ts, f.id) >
              (p.service_date, p.order_ts, p.id)
    )
    SELECT DISTINCT ON (prior_job_id, followup_job_id)
           prior_job_id,
           followup_job_id,
           customer_id,
           location_id,
           equipment_id,
           technician_prior_id,
           technician_followup_id,
           days_between
    FROM paired
    WHERE fanout_rank <= :max_followups_per_job
    ORDER BY prior_job_id, followup_job_id
    """
)


@dataclass(frozen=True, slots=True)
class DetectionJob:
    id: UUID
    customer_id: UUID | None
    location_id: UUID | None
    equipment_id: UUID | None
    technician_id: UUID | None
    service_category_id: UUID | None
    raw_service_category: str | None
    raw_job_type: str | None
    service_date: date
    revenue_amount: Decimal | None
    is_warranty: bool
    extra_fields: dict[str, object]


@dataclass(frozen=True, slots=True)
class DetectionVisit:
    id: UUID
    customer_id: UUID | None
    equipment_id: UUID | None
    service_date: date


@dataclass(frozen=True, slots=True)
class CandidateJob:
    id: UUID
    external_id: str | None
    job_number: str | None
    customer_id: UUID | None
    location_id: UUID | None
    equipment_id: UUID | None
    technician_id: UUID | None
    status: JobStatus
    service_date: date
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    raw_service_category: str | None
    raw_job_type: str | None
    summary: str | None
    description: str | None
    symptoms_text: str | None
    diagnosis_text: str | None
    resolution_text: str | None
    invoice_number: str | None
    revenue_amount: Decimal | None
    parts_amount: Decimal | None
    labor_amount: Decimal | None
    currency_code: str
    is_warranty: bool
    is_no_charge: bool
    warranty_reference: str | None


def candidate_job_ids_in_date_range(
    *,
    organization_id: UUID,
    date_from: date | None,
    date_to: date | None,
) -> Select[tuple[UUID]]:
    statement = select(Job.id).where(
        Job.organization_id == organization_id,
        Job.deleted_at.is_(None),
    )
    if date_from is not None:
        statement = statement.where(Job.service_date >= date_from)
    if date_to is not None:
        statement = statement.where(Job.service_date <= date_to)
    return statement


async def load_candidate_jobs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    job_ids: set[UUID],
) -> dict[UUID, CandidateJob]:
    if not job_ids:
        return {}
    rows = (
        await session.execute(
            select(
                Job.id,
                Job.external_id,
                Job.job_number,
                Job.customer_id,
                Job.location_id,
                Job.equipment_id,
                Job.technician_id,
                Job.status,
                Job.service_date,
                Job.scheduled_at,
                Job.started_at,
                Job.completed_at,
                Job.raw_service_category,
                Job.raw_job_type,
                Job.summary,
                Job.description,
                Job.symptoms_text,
                Job.diagnosis_text,
                Job.resolution_text,
                Job.invoice_number,
                Job.revenue_amount,
                Job.parts_amount,
                Job.labor_amount,
                Job.currency_code,
                Job.is_warranty,
                Job.is_no_charge,
                Job.warranty_reference,
            ).where(
                Job.organization_id == organization_id,
                Job.id.in_(job_ids),
            )
        )
    ).all()
    return {row.id: CandidateJob(*row) for row in rows}


def detection_job_ids_in_scope(
    *,
    organization_id: UUID,
    from_date: date,
    to_date: date,
    window_days: int,
) -> Select[tuple[UUID]]:
    return select(Job.id).where(
        Job.organization_id == organization_id,
        Job.deleted_at.is_(None),
        Job.status.in_((JobStatus.COMPLETED, JobStatus.UNKNOWN)),
        Job.service_date.between(from_date - timedelta(days=window_days), to_date),
    )


async def load_detection_jobs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    job_ids: set[UUID],
) -> dict[UUID, DetectionJob]:
    if not job_ids:
        return {}
    rows = (
        await session.execute(
            select(
                Job.id,
                Job.customer_id,
                Job.location_id,
                Job.equipment_id,
                Job.technician_id,
                Job.service_category_id,
                Job.raw_service_category,
                Job.raw_job_type,
                Job.service_date,
                Job.revenue_amount,
                Job.is_warranty,
                Job.extra_fields,
            ).where(
                Job.organization_id == organization_id,
                Job.id.in_(job_ids),
            )
        )
    ).all()
    return {
        row.id: DetectionJob(
            id=row.id,
            customer_id=row.customer_id,
            location_id=row.location_id,
            equipment_id=row.equipment_id,
            technician_id=row.technician_id,
            service_category_id=row.service_category_id,
            raw_service_category=row.raw_service_category,
            raw_job_type=row.raw_job_type,
            service_date=row.service_date,
            revenue_amount=row.revenue_amount,
            is_warranty=row.is_warranty,
            extra_fields=row.extra_fields,
        )
        for row in rows
    }


async def load_detection_part_codes(
    session: AsyncSession,
    *,
    organization_id: UUID,
    job_ids: set[UUID],
) -> dict[UUID, set[str]]:
    codes: defaultdict[UUID, set[str]] = defaultdict(set)
    if not job_ids:
        return codes
    rows = (
        await session.execute(
            select(JobLineItem.job_id, JobLineItem.code).where(
                JobLineItem.organization_id == organization_id,
                JobLineItem.job_id.in_(job_ids),
                JobLineItem.kind == LineItemKind.PART,
                JobLineItem.code.is_not(None),
            )
        )
    ).all()
    for job_id, code in rows:
        if code and code.strip():
            codes[job_id].add(code.strip().casefold())
    return codes


async def load_detection_visits(
    session: AsyncSession,
    *,
    organization_id: UUID,
    customer_ids: set[UUID],
    equipment_ids: set[UUID],
    first_date: date,
    last_date: date,
) -> list[DetectionVisit]:
    filters = []
    if customer_ids:
        filters.append(Job.customer_id.in_(customer_ids))
    if equipment_ids:
        filters.append(Job.equipment_id.in_(equipment_ids))
    if not filters:
        return []
    rows = (
        await session.execute(
            select(Job.id, Job.customer_id, Job.equipment_id, Job.service_date).where(
                Job.organization_id == organization_id,
                Job.deleted_at.is_(None),
                Job.status.in_((JobStatus.COMPLETED, JobStatus.UNKNOWN)),
                Job.service_date.between(first_date, last_date),
                or_(*filters),
            )
        )
    ).all()
    return [DetectionVisit(*row) for row in rows]
