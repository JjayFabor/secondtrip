"""Typed entitlement key catalogue."""

from enum import StrEnum


class EntitlementKey(StrEnum):
    JOBS_IMPORTED = "jobs_imported"
    JOBS_RETAINED = "jobs_retained"
    RETENTION_MONTHS = "retention_months"
    IMPORT_FILE_BYTES = "import_file_bytes"
    IMPORTS_PER_MONTH = "imports_per_month"
    CONCURRENT_IMPORTS = "concurrent_imports"
    TEAM_MEMBERS = "team_members"
    EXPORTS_ENABLED = "exports_enabled"
    EXPORTS_PER_MONTH = "exports_per_month"
    API_ACCESS = "api_access"
    INTEGRATIONS = "integrations"
    CUSTOM_DETECTION_RULES = "custom_detection_rules"
    AUDIT_RETENTION_MONTHS = "audit_retention_months"
