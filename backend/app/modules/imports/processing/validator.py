"""Pure per-row dry-run validation and source-record construction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import cast
from uuid import UUID

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.mapping.catalogue import TARGET_FIELDS, TargetType
from app.modules.imports.mapping.document import (
    BooleanTransform,
    DateTransform,
    MappingDocument,
    MoneyTransform,
    SkipFilter,
    ValueMapTransform,
)
from app.modules.imports.models import ImportRowStatus
from app.modules.imports.normalization.booleans import normalize_boolean
from app.modules.imports.normalization.dates import DateOrder, normalize_date, normalize_datetime
from app.modules.imports.normalization.identity import customer_key, equipment_key, location_key
from app.modules.imports.normalization.money import normalize_money
from app.modules.imports.normalization.phones import normalize_phone
from app.modules.imports.normalization.records import SourceRecord
from app.modules.imports.normalization.text import normalize_text
from app.modules.imports.processing.reader import ParsedCsvRow
from app.modules.jobs.schemas import JobStatus


@dataclass(frozen=True, slots=True)
class RowValidation:
    row_number: int
    raw_data: dict[str, str]
    row_hash: bytes
    status: ImportRowStatus
    issues: tuple[ImportIssue, ...]
    source_record: SourceRecord | None


def _with_field(
    issues: tuple[ImportIssue, ...], field: str, raw_value: str | None
) -> list[ImportIssue]:
    return [
        replace(issue, field=issue.field or field, raw_value=issue.raw_value or raw_value)
        for issue in issues
    ]


def _filter_matches(rule: SkipFilter, raw_data: dict[str, str]) -> bool:
    actual = raw_data.get(rule.column, "").strip().casefold()
    expected = (rule.value or "").strip().casefold()
    if rule.operator == "equals":
        return actual == expected
    if rule.operator == "not_equals":
        return actual != expected
    if rule.operator == "contains":
        return expected in actual
    if rule.operator == "is_empty":
        return not actual
    return bool(actual)


def _issue_dict(issue: ImportIssue) -> dict[str, str | None]:
    return {
        "code": issue.code.value,
        "severity": issue.severity.value,
        "message": issue.message,
        "field": issue.field,
        "raw_value": issue.raw_value,
    }


def serialize_issues(issues: tuple[ImportIssue, ...]) -> list[dict[str, str | None]]:
    return [_issue_dict(issue) for issue in issues]


def validate_row(
    parsed: ParsedCsvRow,
    mapping: MappingDocument,
    *,
    organization_id: UUID,
    source_system_id: UUID,
    organization_timezone: str,
    date_order: DateOrder,
    max_field_bytes: int,
) -> RowValidation:
    issues = list(parsed.issues)
    if any(_filter_matches(rule, parsed.raw_data) for rule in mapping.skip_rows_where):
        issues.append(
            ImportIssue(
                code=IssueCode.ROW_SKIPPED_BY_FILTER,
                severity=IssueSeverity.INFO,
                message="Row matched an import filter.",
            )
        )
        return RowValidation(
            parsed.row_number,
            parsed.raw_data,
            parsed.row_hash,
            ImportRowStatus.SKIPPED_FILTERED,
            tuple(issues),
            None,
        )

    values: dict[str, object] = {}
    for target_name, field_mapping in mapping.fields.items():
        raw = parsed.raw_data.get(field_mapping.source_column)
        target = TARGET_FIELDS[target_name]
        transform = field_mapping.transform

        if target.data_type is TargetType.TEXT:
            text_result = normalize_text(raw, max_bytes=max_field_bytes)
            normalized_value: object = text_result.value
            normalized_issues = text_result.issues
        elif target.data_type is TargetType.DATE:
            explicit = transform.format if isinstance(transform, DateTransform) else None
            date_result = normalize_date(raw, explicit_format=explicit, order=date_order)
            normalized_value = date_result.value
            normalized_issues = date_result.issues
        elif target.data_type is TargetType.DATETIME:
            explicit = transform.format if isinstance(transform, DateTransform) else None
            timezone = (
                transform.timezone
                if isinstance(transform, DateTransform) and transform.timezone
                else organization_timezone
            )
            datetime_result = normalize_datetime(
                raw,
                organization_timezone=timezone,
                explicit_format=explicit,
                order=date_order,
            )
            normalized_value = datetime_result.value
            normalized_issues = datetime_result.issues
        elif target.data_type is TargetType.MONEY:
            money_result = normalize_money(
                raw,
                decimal_separator=(
                    transform.decimal_separator if isinstance(transform, MoneyTransform) else None
                ),
                thousands_separator=(
                    transform.thousands_separator if isinstance(transform, MoneyTransform) else None
                ),
            )
            normalized_value = money_result.value
            normalized_issues = money_result.issues
        elif target.data_type is TargetType.BOOLEAN:
            boolean_result = normalize_boolean(
                raw,
                true_values=(
                    transform.true_values if isinstance(transform, BooleanTransform) else None
                ),
            )
            normalized_value = boolean_result.value
            normalized_issues = boolean_result.issues
        else:
            if raw is None or not raw.strip():
                result_value: int | None = None
                result_issues: tuple[ImportIssue, ...] = ()
            else:
                try:
                    number = Decimal(raw.strip())
                    if number != number.to_integral_value():
                        raise InvalidOperation
                    result_value = int(number)
                    result_issues = ()
                except (InvalidOperation, ValueError):
                    result_value = None
                    result_issues = (
                        ImportIssue(
                            code=IssueCode.INVALID_NUMBER,
                            severity=IssueSeverity.ERROR,
                            message="Integer could not be parsed.",
                            raw_value=raw,
                        ),
                    )
            values[target_name] = result_value
            issues.extend(_with_field(result_issues, target_name, raw))
            continue

        values[target_name] = normalized_value
        issues.extend(_with_field(normalized_issues, target_name, raw))

    if "job_status" in values:
        mapping_item = mapping.fields["job_status"]
        transform = mapping_item.transform
        status_value = cast(str | None, values["job_status"])
        if isinstance(transform, ValueMapTransform) and status_value is not None:
            status_value = transform.map.get(status_value, status_value)
        if status_value is not None and status_value.casefold() not in {
            item.value for item in JobStatus
        }:
            issues.append(
                ImportIssue(
                    code=IssueCode.UNKNOWN_ENUM_VALUE,
                    severity=IssueSeverity.WARNING,
                    message="Unknown job status; unknown will be used.",
                    field="job_status",
                    raw_value=cast(str | None, values["job_status"]),
                )
            )
            status_value = JobStatus.UNKNOWN.value
        values["job_status"] = status_value

    extra_fields: dict[str, str] = {}
    for source_column in mapping.retain_unmapped:
        result = normalize_text(parsed.raw_data.get(source_column), max_bytes=max_field_bytes)
        if result.value is not None:
            extra_fields[source_column] = result.value
        issues.extend(_with_field(result.issues, source_column, parsed.raw_data.get(source_column)))

    # Organizations do not yet store a country. "ZZ" accepts explicit
    # international numbers without guessing a region for local numbers.
    phone = normalize_phone(cast(str | None, values.get("customer_phone")), default_region="ZZ")
    values["customer_phone_raw"] = phone.raw
    values["customer_phone_e164"] = phone.e164
    values.pop("customer_phone", None)

    customer = customer_key(
        organization_id,
        source_system_id,
        external_id=cast(str | None, values.get("customer_external_id")),
        phone_e164=phone.e164,
        name=cast(str | None, values.get("customer_name")),
        postal_code=cast(str | None, values.get("postal_code")),
    )
    if customer is None:
        issues.append(
            ImportIssue(
                code=IssueCode.UNRESOLVABLE_CUSTOMER,
                severity=IssueSeverity.ERROR,
                message="Customer needs an external ID, phone, or name.",
                field="customer_name",
            )
        )

    location = location_key(
        organization_id,
        source_system_id,
        external_id=cast(str | None, values.get("location_external_id")),
        customer_digest=customer.digest if customer else None,
        address_line1=cast(str | None, values.get("address_line1")),
        postal_code=cast(str | None, values.get("postal_code")),
    )
    equipment = equipment_key(
        organization_id,
        source_system_id,
        external_id=cast(str | None, values.get("equipment_external_id")),
        serial_number=cast(str | None, values.get("equipment_serial")),
        location_digest=location.digest if location else None,
        manufacturer=cast(str | None, values.get("equipment_manufacturer")),
        model=cast(str | None, values.get("equipment_model")),
        equipment_type=cast(str | None, values.get("equipment_type")),
    )
    if equipment is None:
        issues.append(
            ImportIssue(
                code=IssueCode.EQUIPMENT_NOT_RESOLVED,
                severity=IssueSeverity.INFO,
                message="No equipment identity could be resolved; the job will remain unlinked.",
                field="equipment_serial",
            )
        )

    has_error = any(issue.severity is IssueSeverity.ERROR for issue in issues)
    has_warning = any(issue.severity is IssueSeverity.WARNING for issue in issues)
    status = (
        ImportRowStatus.ERROR
        if has_error
        else ImportRowStatus.WARNING
        if has_warning
        else ImportRowStatus.PENDING
    )
    source_record: SourceRecord | None = None
    if not has_error:
        source_record = SourceRecord(
            service_date=cast(date, values["service_date"]),
            external_job_id=cast(str | None, values.get("external_job_id")),
            customer_name=cast(str | None, values.get("customer_name")),
            customer_external_id=cast(str | None, values.get("customer_external_id")),
            customer_phone_raw=phone.raw,
            customer_phone_e164=phone.e164,
            customer_email=cast(str | None, values.get("customer_email")),
            address_line1=cast(str | None, values.get("address_line1")),
            city=cast(str | None, values.get("city")),
            region=cast(str | None, values.get("region")),
            postal_code=cast(str | None, values.get("postal_code")),
            location_external_id=cast(str | None, values.get("location_external_id")),
            equipment_serial=cast(str | None, values.get("equipment_serial")),
            equipment_manufacturer=cast(str | None, values.get("equipment_manufacturer")),
            equipment_model=cast(str | None, values.get("equipment_model")),
            equipment_type=cast(str | None, values.get("equipment_type")),
            equipment_external_id=cast(str | None, values.get("equipment_external_id")),
            technician_name=cast(str | None, values.get("technician_name")),
            technician_external_id=cast(str | None, values.get("technician_external_id")),
            technician_code=cast(str | None, values.get("technician_code")),
            service_category=cast(str | None, values.get("service_category")),
            job_type=cast(str | None, values.get("job_type")),
            job_status=cast(str | None, values.get("job_status")),
            summary=cast(str | None, values.get("summary")),
            description=cast(str | None, values.get("description")),
            symptoms=cast(str | None, values.get("symptoms")),
            diagnosis=cast(str | None, values.get("diagnosis")),
            resolution=cast(str | None, values.get("resolution")),
            technician_notes=cast(str | None, values.get("technician_notes")),
            invoice_number=cast(str | None, values.get("invoice_number")),
            revenue_amount=cast(Decimal | None, values.get("revenue_amount")),
            parts_amount=cast(Decimal | None, values.get("parts_amount")),
            labor_amount=cast(Decimal | None, values.get("labor_amount")),
            duration_minutes=cast(int | None, values.get("duration_minutes")),
            is_warranty=cast(bool, values.get("is_warranty", False)),
            warranty_reference=cast(str | None, values.get("warranty_reference")),
            scheduled_at=cast(datetime | None, values.get("scheduled_at")),
            started_at=cast(datetime | None, values.get("started_at")),
            completed_at=cast(datetime | None, values.get("completed_at")),
            extra_fields=MappingProxyType(extra_fields),
        )
    return RowValidation(
        parsed.row_number,
        parsed.raw_data,
        parsed.row_hash,
        status,
        tuple(issues),
        source_record,
    )
