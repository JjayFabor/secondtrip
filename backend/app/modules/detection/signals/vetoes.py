"""Categorical veto signals."""

from __future__ import annotations

from decimal import Decimal

from app.modules.detection.schemas import SignalOutcome
from app.modules.detection.signals.base import BaseSignal, CandidatePair, SignalResult

ZERO = Decimal(0)
ONE = Decimal(1)
DEFAULT_MAINTENANCE_CATEGORIES = frozenset({"maintenance"})
DEFAULT_PLANNED_MARKERS = (
    "planned multi-visit",
    "planned multivisit",
    "multi-visit project",
)


class ScheduledMaintenanceSignal(BaseSignal):
    key = "scheduled_maintenance"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        category = pair.followup.service_category
        if not category:
            return _not_evaluable(self.key, "Follow-up service category was not recorded.")
        configured = _string_values(
            params.get("category_keys"),
            default=DEFAULT_MAINTENANCE_CATEGORIES,
            parameter="scheduled_maintenance category_keys",
        )
        normalized = category.strip().casefold()
        matched = normalized in configured
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={"category": category},
            explanation=(
                f"Follow-up category {category!r} is scheduled maintenance."
                if matched
                else f"Follow-up category {category!r} is not scheduled maintenance."
            ),
        )


class PlannedMultivisitSignal(BaseSignal):
    key = "planned_multivisit"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        markers = _string_values(
            params.get("markers"),
            default=DEFAULT_PLANNED_MARKERS,
            parameter="planned_multivisit markers",
        )
        values = [pair.prior.raw_job_type, *pair.prior.extra_fields.values()]
        text_values = [str(value) for value in values if value is not None and str(value).strip()]
        if not text_values:
            return _not_evaluable(self.key, "Prior visit has no project or job-type marker.")
        matched_value = next(
            (
                value
                for value in text_values
                if any(marker in value.strip().casefold() for marker in markers)
            ),
            None,
        )
        matched = matched_value is not None
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={"matched_marker": matched_value} if matched_value else {},
            explanation=(
                f"Prior visit was marked as planned multi-visit work ({matched_value})."
                if matched
                else "Prior visit was not marked as planned multi-visit work."
            ),
        )


def _string_values(
    value: object,
    *,
    default: object,
    parameter: str,
) -> frozenset[str]:
    selected = default if value is None else value
    if not isinstance(selected, (list, tuple, set, frozenset)):
        raise ValueError(f"{parameter} must be a list of strings")
    if not all(isinstance(item, str) and item.strip() for item in selected):
        raise ValueError(f"{parameter} must contain non-empty strings")
    return frozenset(str(item).strip().casefold() for item in selected)


def _not_evaluable(key: str, explanation: str) -> SignalResult:
    return SignalResult(
        key=key,
        outcome=SignalOutcome.NOT_EVALUABLE,
        strength=ZERO,
        raw_value={},
        explanation=explanation,
    )
