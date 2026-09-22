"""Import lifecycle API through mapping confirmation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition import AppState, get_app_state
from app.core.errors import InvalidCursorRequestError, NotFoundError
from app.core.pagination import InvalidCursorError, clamp_limit
from app.core.permissions import Permission
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.audit.schemas import ActorType
from app.modules.audit.service import record as record_audit
from app.modules.billing.entitlements.keys import EntitlementKey
from app.modules.billing.entitlements.service import EntitlementService
from app.modules.idempotency.service import claim, complete, request_digest
from app.modules.imports.errors import ImportStateConflictError
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.models import ImportStatus
from app.modules.imports.repository import ImportsRepository
from app.modules.imports.schemas import (
    ConfirmUploadRequest,
    CreateImportOut,
    CreateImportRequest,
    ErrorReportOut,
    ImportBatchOut,
    ImportIssuePageOut,
    ImportIssueRowOut,
    ImportIssuesOut,
    ImportListOut,
    ImportPageOut,
    ImportPreviewOut,
    PresignedUploadOut,
)
from app.modules.imports.service import (
    apply_mapping,
    build_preview,
    confirm_upload,
    create_import,
    request_cancellation,
    request_commit,
    request_validation,
    verify_uploaded_object,
)
from app.modules.organizations.deps import get_tenant_session, require_permission

router = APIRouter(prefix="/orgs/{org_id}/imports", tags=["imports"])

require_imports_read = require_permission(Permission.IMPORTS_READ)
require_imports_manage = require_permission(Permission.IMPORTS_MANAGE)


@router.get("")
async def list_imports_endpoint(
    org_id: UUID,
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_imports_read),
) -> ImportListOut:
    del org_id
    page_limit = clamp_limit(limit)
    try:
        batches, next_cursor = await ImportsRepository(session, tenant).list_batches(
            cursor=cursor, limit=page_limit
        )
    except (InvalidCursorError, ValueError) as exc:
        raise InvalidCursorRequestError("Cursor is malformed or expired.") from exc
    return ImportListOut(
        data=[ImportBatchOut.model_validate(batch) for batch in batches],
        page=ImportPageOut(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            limit=page_limit,
        ),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_import_endpoint(
    org_id: UUID,
    body: CreateImportRequest,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_imports_manage),
) -> CreateImportOut:
    del org_id
    async with tenant_session(app_state.session_factory, tenant) as session:
        creation = await create_import(
            session,
            ImportsRepository(session, tenant),
            EntitlementService(session),
            app_state.storage_provider,
            app_state.settings,
            tenant,
            original_filename=body.original_filename,
            source_system_id=body.source_system_id,
        )
        await record_audit(
            session,
            organization_id=tenant.organization_id,
            action="import.created",
            summary=f"Created import for {body.original_filename}",
            actor_type=ActorType.USER,
            actor_user_id=tenant.actor_user_id,
            actor_label="Authenticated user",
            resource_type="import_batch",
            resource_id=creation.batch.id,
            request_id=getattr(request.state, "request_id", None),
        )
        return CreateImportOut(
            batch=ImportBatchOut.model_validate(creation.batch),
            upload=PresignedUploadOut(
                url=creation.upload.url,
                method=creation.upload.method,
                headers=creation.upload.headers,
                fields=creation.upload.fields,
                max_bytes=creation.upload.max_bytes,
                expires_at=creation.upload.expires_at,
            ),
        )


@router.get("/{batch_id}")
async def get_import_endpoint(
    org_id: UUID,
    batch_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_imports_read),
) -> ImportBatchOut:
    del org_id
    batch = await ImportsRepository(session, tenant).get_batch(batch_id)
    if batch is None:
        raise NotFoundError("Import not found.")
    return ImportBatchOut.model_validate(batch)


@router.post("/{batch_id}/uploaded", status_code=status.HTTP_202_ACCEPTED)
async def confirm_upload_endpoint(
    org_id: UUID,
    batch_id: UUID,
    request: Request,
    body: ConfirmUploadRequest | None = None,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_imports_manage),
) -> ImportBatchOut:
    del org_id
    allow_duplicate = body.allow_duplicate if body is not None else False
    async with tenant_session(app_state.session_factory, tenant) as session:
        repository = ImportsRepository(session, tenant)
        batch = await repository.get_batch(batch_id)
        if batch is None:
            raise NotFoundError("Import not found.")
        if batch.status in {
            ImportStatus.UPLOADED,
            ImportStatus.PROFILING,
            ImportStatus.AWAITING_MAPPING,
        }:
            return ImportBatchOut.model_validate(batch)
        if batch.status is not ImportStatus.AWAITING_FILE:
            raise ImportStateConflictError(f"Import cannot accept an upload while {batch.status}.")
        if batch.storage_key is None:
            raise ImportStateConflictError("Import has no upload destination.")
        storage_key = batch.storage_key
        plan_limit = await EntitlementService(session).limit(
            tenant, EntitlementKey.IMPORT_FILE_BYTES
        )
        max_bytes = app_state.settings.import_max_file_bytes
        if plan_limit is not None:
            max_bytes = min(max_bytes, plan_limit)

    metadata, digest = await verify_uploaded_object(
        app_state.storage_provider, storage_key, max_bytes=max_bytes
    )
    async with tenant_session(app_state.session_factory, tenant) as session:
        batch = await confirm_upload(
            session,
            ImportsRepository(session, tenant),
            app_state.job_queue,
            tenant,
            batch_id=batch_id,
            metadata=metadata,
            digest=digest,
            allow_duplicate=allow_duplicate,
        )
        await record_audit(
            session,
            organization_id=tenant.organization_id,
            action="import.uploaded",
            summary="Confirmed import upload and queued profiling",
            actor_type=ActorType.USER,
            actor_user_id=tenant.actor_user_id,
            actor_label="Authenticated user",
            resource_type="import_batch",
            resource_id=batch.id,
            request_id=getattr(request.state, "request_id", None),
        )
        return ImportBatchOut.model_validate(batch)


@router.get("/{batch_id}/preview")
async def preview_import_endpoint(
    org_id: UUID,
    batch_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_imports_manage),
) -> ImportPreviewOut:
    del org_id
    return await build_preview(ImportsRepository(session, tenant), batch_id=batch_id)


@router.put("/{batch_id}/mapping")
async def apply_mapping_endpoint(
    org_id: UUID,
    batch_id: UUID,
    body: MappingDocument,
    request: Request,
    template_id: UUID | None = None,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_imports_manage),
) -> ImportBatchOut:
    del org_id
    batch = await apply_mapping(
        session,
        ImportsRepository(session, tenant),
        batch_id=batch_id,
        mapping=body,
        template_id=template_id,
    )
    await record_audit(
        session,
        organization_id=tenant.organization_id,
        action="import.mapping_applied",
        summary="Applied import column mapping",
        actor_type=ActorType.USER,
        actor_user_id=tenant.actor_user_id,
        actor_label="Authenticated user",
        resource_type="import_batch",
        resource_id=batch.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return ImportBatchOut.model_validate(batch)


@router.post("/{batch_id}/validate", status_code=status.HTTP_202_ACCEPTED)
async def validate_import_endpoint(
    org_id: UUID,
    batch_id: UUID,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_imports_manage),
) -> ImportBatchOut:
    del org_id
    async with tenant_session(app_state.session_factory, tenant) as session:
        batch = await request_validation(
            session,
            ImportsRepository(session, tenant),
            app_state.job_queue,
            tenant,
            batch_id=batch_id,
        )
        await record_audit(
            session,
            organization_id=tenant.organization_id,
            action="import.validation_requested",
            summary="Queued import dry-run validation",
            actor_type=ActorType.USER,
            actor_user_id=tenant.actor_user_id,
            actor_label="Authenticated user",
            resource_type="import_batch",
            resource_id=batch.id,
            request_id=getattr(request.state, "request_id", None),
        )
        return ImportBatchOut.model_validate(batch)


@router.post("/{batch_id}/commit", status_code=status.HTTP_202_ACCEPTED)
async def commit_import_endpoint(
    org_id: UUID,
    batch_id: UUID,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255),
    ],
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_imports_manage),
) -> ImportBatchOut:
    del org_id
    route = "/imports/{batch_id}/commit"
    digest = request_digest({"batch_id": str(batch_id)})
    async with tenant_session(app_state.session_factory, tenant) as session:
        idempotency = await claim(
            session,
            organization_id=tenant.organization_id,
            route=route,
            idempotency_key=idempotency_key,
            digest=digest,
        )
        if idempotency.replay_body is not None:
            return ImportBatchOut.model_validate(idempotency.replay_body)
        batch = await request_commit(
            session,
            ImportsRepository(session, tenant),
            EntitlementService(session),
            app_state.job_queue,
            tenant,
            batch_id=batch_id,
        )
        await record_audit(
            session,
            organization_id=tenant.organization_id,
            action="import.commit_requested",
            summary="Reserved import capacity and queued processing",
            actor_type=ActorType.USER,
            actor_user_id=tenant.actor_user_id,
            actor_label="Authenticated user",
            resource_type="import_batch",
            resource_id=batch.id,
            request_id=getattr(request.state, "request_id", None),
        )
        response = ImportBatchOut.model_validate(batch)
        complete(
            idempotency,
            status_code=status.HTTP_202_ACCEPTED,
            response_body=response.model_dump(mode="json"),
        )
        return response


@router.get("/{batch_id}/issues")
async def list_import_issues_endpoint(
    org_id: UUID,
    batch_id: UUID,
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_imports_read),
) -> ImportIssuesOut:
    del org_id
    repository = ImportsRepository(session, tenant)
    batch = await repository.get_batch(batch_id)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status in {
        ImportStatus.AWAITING_FILE,
        ImportStatus.UPLOADED,
        ImportStatus.PROFILING,
        ImportStatus.AWAITING_MAPPING,
    }:
        raise ImportStateConflictError("Import validation has not started.")
    page_limit = clamp_limit(limit)
    try:
        rows, next_cursor = await repository.list_issue_rows(
            batch_id, cursor=cursor, limit=page_limit
        )
    except (InvalidCursorError, TypeError, ValueError) as exc:
        raise InvalidCursorRequestError("Cursor is malformed or expired.") from exc
    return ImportIssuesOut(
        data=[ImportIssueRowOut.model_validate(row) for row in rows],
        page=ImportIssuePageOut(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            limit=page_limit,
        ),
    )


@router.get("/{batch_id}/issues/export")
async def export_import_issues_endpoint(
    org_id: UUID,
    batch_id: UUID,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_imports_read),
) -> ErrorReportOut:
    del org_id
    async with tenant_session(app_state.session_factory, tenant) as session:
        batch = await ImportsRepository(session, tenant).get_batch(batch_id)
        if batch is None:
            raise NotFoundError("Import not found.")
        if batch.error_report_key is None:
            raise ImportStateConflictError("The import error report is not ready yet.")
        key = batch.error_report_key
    url = await app_state.storage_provider.signed_download_url(
        key,
        expires_in=app_state.settings.storage_signed_url_ttl_seconds,
        download_filename="import-errors.csv",
    )
    return ErrorReportOut(url=url)


@router.post("/{batch_id}/cancel")
async def cancel_import_endpoint(
    org_id: UUID,
    batch_id: UUID,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_imports_manage),
) -> ImportBatchOut:
    del org_id
    async with tenant_session(app_state.session_factory, tenant) as session:
        batch = await request_cancellation(
            session,
            ImportsRepository(session, tenant),
            app_state.job_queue,
            tenant,
            batch_id=batch_id,
        )
        await record_audit(
            session,
            organization_id=tenant.organization_id,
            action="import.cancel_requested",
            summary="Requested import cancellation",
            actor_type=ActorType.USER,
            actor_user_id=tenant.actor_user_id,
            actor_label="Authenticated user",
            resource_type="import_batch",
            resource_id=batch.id,
            request_id=getattr(request.state, "request_id", None),
        )
        return ImportBatchOut.model_validate(batch)
