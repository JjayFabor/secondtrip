from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.detection.defaults import DEFAULT_SIGNAL_DEFINITIONS, DEFAULT_SIGNAL_KEYS
from app.modules.detection.schemas import SignalOutcome
from app.modules.detection.signals.base import CandidatePair, JobSignalData
from app.modules.detection.signals.registry import SIGNAL_REGISTRY, evaluate_signals


def _job(*, followup: bool = False) -> JobSignalData:
    shared_customer = IDS["customer"]
    shared_location = IDS["location"]
    shared_equipment = IDS["equipment"]
    shared_technician = IDS["technician"]
    shared_category = IDS["category"]
    return JobSignalData(
        id=uuid4(),
        customer_id=shared_customer,
        location_id=shared_location,
        equipment_id=shared_equipment,
        technician_id=shared_technician,
        service_category_id=shared_category,
        service_category="Repair",
        raw_job_type="Service",
        service_date=date(2026, 1, 5) if followup else date(2026, 1, 1),
        revenue_amount=Decimal("0") if followup else Decimal("100"),
        is_warranty=followup,
        extra_fields={"Contract Type": "Residential service"},
        part_codes=frozenset({"cap-42"}),
    )


def _pair() -> CandidatePair:
    return CandidatePair(
        candidate_id=uuid4(),
        prior=_job(),
        followup=_job(followup=True),
        days_between=4,
        recurrence_count=3,
        equipment_serial="SERIAL-4821",
        equipment_warranty_expires_on=date(2027, 1, 1),
    )


IDS = {
    "customer": uuid4(),
    "location": uuid4(),
    "equipment": uuid4(),
    "technician": uuid4(),
    "category": uuid4(),
}
DEFAULT_PARAMS = {item.key: item.params for item in DEFAULT_SIGNAL_DEFINITIONS}


def test_registry_matches_the_catalogue_and_evaluates_all_v1_signals() -> None:
    results = {result.key: result for result in evaluate_signals(_pair(), DEFAULT_PARAMS)}

    assert set(SIGNAL_REGISTRY) == DEFAULT_SIGNAL_KEYS
    assert set(results) == DEFAULT_SIGNAL_KEYS
    assert results["same_customer"].outcome is SignalOutcome.MATCHED
    assert results["same_location"].outcome is SignalOutcome.MATCHED
    assert results["same_equipment"].raw_value["serial_suffix"] == "4821"
    assert results["days_between"].strength == Decimal("1.00")
    assert results["same_service_category"].outcome is SignalOutcome.MATCHED
    assert results["zero_value_followup"].outcome is SignalOutcome.MATCHED
    assert results["low_value_followup"].outcome is SignalOutcome.MATCHED
    assert results["warranty_marker"].outcome is SignalOutcome.MATCHED
    assert results["within_equipment_warranty"].outcome is SignalOutcome.MATCHED
    assert results["same_technician"].outcome is SignalOutcome.MATCHED
    assert results["repeat_part_code"].outcome is SignalOutcome.MATCHED
    assert results["recurrence_density"].outcome is SignalOutcome.MATCHED
    assert results["scheduled_maintenance"].outcome is SignalOutcome.NOT_MATCHED
    assert results["planned_multivisit"].outcome is SignalOutcome.NOT_MATCHED


def test_missing_data_is_not_evaluable_instead_of_a_false_non_match() -> None:
    empty = replace(
        _job(),
        customer_id=None,
        location_id=None,
        equipment_id=None,
        technician_id=None,
        service_category_id=None,
        service_category=None,
        raw_job_type=None,
        revenue_amount=None,
        extra_fields={},
        part_codes=frozenset(),
    )
    pair = replace(
        _pair(),
        prior=empty,
        followup=replace(empty, id=uuid4()),
        equipment_warranty_expires_on=None,
    )
    results = {result.key: result for result in evaluate_signals(pair, DEFAULT_PARAMS)}

    for key in (
        "same_customer",
        "same_location",
        "same_equipment",
        "same_service_category",
        "zero_value_followup",
        "low_value_followup",
        "within_equipment_warranty",
        "same_technician",
        "repeat_part_code",
        "scheduled_maintenance",
        "planned_multivisit",
    ):
        assert results[key].outcome is SignalOutcome.NOT_EVALUABLE


def test_both_documented_vetoes_match_their_v1_markers() -> None:
    maintenance_pair = replace(
        _pair(),
        followup=replace(_job(followup=True), service_category="Maintenance"),
    )
    planned_pair = replace(
        _pair(),
        prior=replace(
            _job(),
            extra_fields={"Contract Type": "Planned multi-visit project"},
        ),
    )

    assert (
        SIGNAL_REGISTRY["scheduled_maintenance"].evaluate(maintenance_pair, {}).outcome
        is SignalOutcome.MATCHED
    )
    assert (
        SIGNAL_REGISTRY["planned_multivisit"].evaluate(planned_pair, {}).outcome
        is SignalOutcome.MATCHED
    )


@pytest.mark.parametrize(
    ("days", "strength"),
    [(0, "0.70"), (1, "0.70"), (2, "1.00"), (7, "1.00"), (8, "0.80"), (30, "0.50")],
)
def test_days_between_uses_inclusive_configured_bands(days: int, strength: str) -> None:
    pair = replace(_pair(), days_between=days)
    result = SIGNAL_REGISTRY["days_between"].evaluate(pair, DEFAULT_PARAMS["days_between"])

    assert result.outcome is SignalOutcome.MATCHED
    assert result.strength == Decimal(strength)


def test_unknown_configured_signal_fails_closed() -> None:
    with pytest.raises(ValueError, match="no signal implementation"):
        evaluate_signals(_pair(), {"not_real": {}})
