"""Public, transport-neutral job domain types."""

from enum import StrEnum


class JobStatus(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    UNKNOWN = "unknown"
