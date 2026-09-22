from decimal import Decimal

from app.modules.detection.defaults import DEFAULT_SIGNAL_DEFINITIONS, DEFAULT_SIGNAL_KEYS
from app.modules.detection.schemas import RuleKind


def test_default_signal_catalogue_matches_the_architecture() -> None:
    assert {
        "same_customer",
        "same_location",
        "same_equipment",
        "days_between",
        "same_service_category",
        "zero_value_followup",
        "low_value_followup",
        "warranty_marker",
        "within_equipment_warranty",
        "same_technician",
        "repeat_part_code",
        "recurrence_density",
        "scheduled_maintenance",
        "planned_multivisit",
    } == DEFAULT_SIGNAL_KEYS
    assert len(DEFAULT_SIGNAL_DEFINITIONS) == len(DEFAULT_SIGNAL_KEYS)


def test_default_weights_are_decimal_and_vetoes_have_no_additive_weight() -> None:
    by_key = {definition.key: definition for definition in DEFAULT_SIGNAL_DEFINITIONS}

    assert all(isinstance(definition.weight, Decimal) for definition in by_key.values())
    assert by_key["same_equipment"].weight == Decimal("30")
    assert by_key["scheduled_maintenance"].kind is RuleKind.VETO
    assert by_key["scheduled_maintenance"].weight == Decimal("0")
    assert by_key["planned_multivisit"].kind is RuleKind.VETO
    assert by_key["planned_multivisit"].weight == Decimal("0")
