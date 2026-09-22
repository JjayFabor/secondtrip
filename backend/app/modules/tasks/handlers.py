"""Composition of the foundational job handlers shipped in this slice."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.modules.detection.service import execute_detection_run
from app.modules.imports.handlers import generate_error_report, profile_import, validate_import
from app.modules.imports.processing.processor import process_import
from app.modules.tasks.control import JobControl
from app.modules.tasks.registry import JobRegistry
from app.modules.tasks.schemas import (
    DetectionRunPayload,
    ImportErrorReportPayload,
    ImportProcessPayload,
    ImportProfilePayload,
    ImportValidatePayload,
    StorageCleanupPayload,
)
from app.modules.tasks.service import PostgresJobQueue
from app.providers.storage.base import StorageProvider


def build_job_registry(
    storage: StorageProvider,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> JobRegistry:
    registry = JobRegistry()
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)

    async def cleanup_storage(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        del tenant
        cleanup = cast(StorageCleanupPayload, payload)
        await control.checkpoint()
        await storage.delete(cleanup.key)

    registry.register(
        "storage.cleanup",
        payload_model=StorageCleanupPayload,
        handler=cleanup_storage,
        timeout_seconds=60,
    )

    async def profile_csv_import(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        profile_payload = cast(ImportProfilePayload, payload)
        await profile_import(
            tenant,
            batch_id=profile_payload.batch_id,
            control=control,
            storage=storage,
            session_factory=session_factory,
            settings=settings,
        )

    registry.register(
        "import.profile",
        payload_model=ImportProfilePayload,
        handler=profile_csv_import,
        timeout_seconds=120,
    )

    async def validate_csv_import(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        validate_payload = cast(ImportValidatePayload, payload)
        await validate_import(
            tenant,
            batch_id=validate_payload.batch_id,
            control=control,
            storage=storage,
            session_factory=session_factory,
            settings=settings,
        )

    registry.register(
        "import.validate",
        payload_model=ImportValidatePayload,
        handler=validate_csv_import,
        timeout_seconds=600,
    )

    async def report_import_issues(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        report_payload = cast(ImportErrorReportPayload, payload)
        await generate_error_report(
            tenant,
            batch_id=report_payload.batch_id,
            control=control,
            storage=storage,
            session_factory=session_factory,
        )

    registry.register(
        "import.error_report",
        payload_model=ImportErrorReportPayload,
        handler=report_import_issues,
        timeout_seconds=300,
    )

    async def process_csv_import(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        process_payload = cast(ImportProcessPayload, payload)
        await process_import(
            tenant,
            batch_id=process_payload.batch_id,
            control=control,
            session_factory=session_factory,
            settings=settings,
            queue=queue,
        )

    registry.register(
        "import.process",
        payload_model=ImportProcessPayload,
        handler=process_csv_import,
        timeout_seconds=1800,
    )

    async def run_detection(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        run_payload = cast(DetectionRunPayload, payload)
        await execute_detection_run(
            tenant,
            detection_run_id=run_payload.detection_run_id,
            control=control,
            session_factory=session_factory,
        )

    registry.register(
        "detection.run",
        payload_model=DetectionRunPayload,
        handler=run_detection,
        timeout_seconds=1800,
    )
    return registry
