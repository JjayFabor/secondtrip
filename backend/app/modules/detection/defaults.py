"""Code-owned default signal catalogue and initial rule configuration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.detection.schemas import RuleKind, SignalValueType


@dataclass(frozen=True, slots=True)
class DefaultSignalDefinition:
    key: str
    label: str
    description: str
    value_type: SignalValueType
    weight: Decimal
    kind: RuleKind
    params: dict[str, object]


DEFAULT_SIGNAL_DEFINITIONS = (
    DefaultSignalDefinition(
        "same_customer",
        "Same customer",
        "Both visits belong to the same customer.",
        SignalValueType.BOOLEAN,
        Decimal("20"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "same_location",
        "Same location",
        "Both visits occurred at the same service location.",
        SignalValueType.BOOLEAN,
        Decimal("15"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "same_equipment",
        "Same equipment",
        "Both visits reference the same equipment record.",
        SignalValueType.BOOLEAN,
        Decimal("30"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "days_between",
        "Days between visits",
        "Scores the org-local calendar-day interval using configurable bands.",
        SignalValueType.NUMERIC,
        Decimal("25"),
        RuleKind.ADDITIVE,
        {
            "bands": [
                [0, 1, "0.70"],
                [2, 7, "1.00"],
                [8, 14, "0.80"],
                [15, 30, "0.50"],
                [31, 90, "0.25"],
            ]
        },
    ),
    DefaultSignalDefinition(
        "same_service_category",
        "Same service category",
        "Both visits share the same normalized service category.",
        SignalValueType.BOOLEAN,
        Decimal("10"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "zero_value_followup",
        "Zero-value follow-up",
        "The follow-up visit has an explicitly recorded zero revenue amount.",
        SignalValueType.BOOLEAN,
        Decimal("25"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "low_value_followup",
        "Low-value follow-up",
        "The follow-up revenue is below the configured share of the prior visit.",
        SignalValueType.RATIO,
        Decimal("10"),
        RuleKind.ADDITIVE,
        {"maximum_ratio": "0.20"},
    ),
    DefaultSignalDefinition(
        "warranty_marker",
        "Warranty marker",
        "The follow-up visit is explicitly marked as warranty work.",
        SignalValueType.BOOLEAN,
        Decimal("25"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "within_equipment_warranty",
        "Within equipment warranty",
        "The follow-up occurred on or before the equipment warranty expiry date.",
        SignalValueType.BOOLEAN,
        Decimal("10"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "same_technician",
        "Same technician",
        "The same technician is assigned to both visits.",
        SignalValueType.BOOLEAN,
        Decimal("5"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "repeat_part_code",
        "Repeated part code",
        "A part code appears on both visits.",
        SignalValueType.CATEGORICAL,
        Decimal("20"),
        RuleKind.ADDITIVE,
        {},
    ),
    DefaultSignalDefinition(
        "recurrence_density",
        "Recurrence density",
        "At least the configured number of related visits occurs inside the window.",
        SignalValueType.NUMERIC,
        Decimal("10"),
        RuleKind.ADDITIVE,
        {"minimum_visits": 3},
    ),
    DefaultSignalDefinition(
        "scheduled_maintenance",
        "Scheduled maintenance",
        "The follow-up category belongs to the organization's maintenance set.",
        SignalValueType.BOOLEAN,
        Decimal("0"),
        RuleKind.VETO,
        {},
    ),
    DefaultSignalDefinition(
        "planned_multivisit",
        "Planned multi-visit work",
        "The prior visit is identified as part of planned multi-visit work.",
        SignalValueType.BOOLEAN,
        Decimal("0"),
        RuleKind.VETO,
        {},
    ),
)

DEFAULT_SIGNAL_KEYS = frozenset(definition.key for definition in DEFAULT_SIGNAL_DEFINITIONS)
