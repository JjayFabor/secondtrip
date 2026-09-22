"""Free-tier fallback when an organization has no active subscription."""

from typing import Final

from app.modules.billing.entitlements.keys import EntitlementKey

FREE_PLAN_DEFAULTS: Final[dict[EntitlementKey, int | None]] = {
    EntitlementKey.JOBS_IMPORTED: 5_000,
    EntitlementKey.JOBS_RETAINED: 10_000,
    EntitlementKey.RETENTION_MONTHS: 6,
    EntitlementKey.IMPORT_FILE_BYTES: 5 * 1024 * 1024,
    EntitlementKey.IMPORTS_PER_MONTH: 3,
    EntitlementKey.CONCURRENT_IMPORTS: 1,
    EntitlementKey.TEAM_MEMBERS: 2,
    EntitlementKey.EXPORTS_ENABLED: 1,
    EntitlementKey.EXPORTS_PER_MONTH: 5,
    EntitlementKey.API_ACCESS: 0,
    EntitlementKey.INTEGRATIONS: 0,
    EntitlementKey.CUSTOM_DETECTION_RULES: 0,
    EntitlementKey.AUDIT_RETENTION_MONTHS: 3,
}
