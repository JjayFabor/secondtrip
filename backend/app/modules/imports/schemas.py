"""Strict API and worker-facing import schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.imports.issues import IssueCode, IssueSeverity
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.mapping.suggester import SuggestionStrategy
from app.modules.imports.models import ImportRowStatus, ImportStatus


class CreateImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_filename: str = Field(min_length=1, max_length=255)
    source_system_id: UUID | None = None


class PresignedUploadOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    method: str
    headers: dict[str, str]
    fields: dict[str, str]
    max_bytes: int
    expires_at: datetime


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    organization_id: UUID
    source_system_id: UUID
    status: ImportStatus
    original_filename: str | None
    file_size_bytes: int | None
    encoding: str | None
    delimiter: str | None
    has_header: bool | None
    mapping: MappingDocument | None
    duplicate_of_batch_id: UUID | None
    total_rows: int
    processed_rows: int
    created_jobs: int
    updated_jobs: int
    skipped_rows: int
    warning_rows: int
    error_rows: int
    error_report_ready: bool
    cancel_requested_at: datetime | None
    failure_reason: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateImportOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch: ImportBatchOut
    upload: PresignedUploadOut


class ImportPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None
    has_more: bool
    limit: int


class ImportListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ImportBatchOut]
    page: ImportPageOut


class ConfirmUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_duplicate: bool = False


class ProfileIssueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: IssueCode
    severity: IssueSeverity
    message: str
    field: str | None = None
    raw_value: str | None = None


class DetectedColumnOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    name: str
    sample_values: list[str]
    inferred_type: str


class MappingSuggestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    target_field: str
    source_column: str
    confidence: float
    strategy: SuggestionStrategy


class ImportPreviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    encoding: str
    delimiter: str
    has_header: bool
    approximate_row_count: int
    columns: list[DetectedColumnOut]
    sample_rows: list[dict[str, str]]
    profile_issues: list[ProfileIssueOut]
    suggested_mapping: MappingDocument | None
    suggestions: list[MappingSuggestionOut]
    matched_template_id: UUID | None


class ImportIssueRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    row_number: int
    status: ImportRowStatus
    issues: list[ProfileIssueOut]


class ImportIssuePageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None
    has_more: bool
    limit: int


class ImportIssuesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ImportIssueRowOut]
    page: ImportIssuePageOut


class ErrorReportOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
