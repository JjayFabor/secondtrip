"""Entity-identity signals."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.detection.schemas import SignalOutcome
from app.modules.detection.signals.base import BaseSignal, CandidatePair, SignalResult

ZERO = Decimal(0)
ONE = Decimal(1)


def _shared_identifier(
    *,
    key: str,
    prior: UUID | None,
    followup: UUID | None,
    label: str,
) -> SignalResult:
    if prior is None or followup is None:
        return SignalResult(
            key=key,
            outcome=SignalOutcome.NOT_EVALUABLE,
            strength=ZERO,
            raw_value={
                "prior_present": prior is not None,
                "followup_present": followup is not None,
            },
            explanation=f"{label} could not be compared because one visit has no value.",
        )
    matched = prior == followup
    return SignalResult(
        key=key,
        outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
        strength=ONE if matched else ZERO,
        raw_value={"same": matched},
        explanation=(
            f"Same {label.lower()} on both visits."
            if matched
            else f"Different {label.lower()} on the two visits."
        ),
    )


class SameCustomerSignal(BaseSignal):
    key = "same_customer"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        return _shared_identifier(
            key=self.key,
            prior=pair.prior.customer_id,
            followup=pair.followup.customer_id,
            label="Customer",
        )


class SameLocationSignal(BaseSignal):
    key = "same_location"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        return _shared_identifier(
            key=self.key,
            prior=pair.prior.location_id,
            followup=pair.followup.location_id,
            label="Location",
        )


class SameEquipmentSignal(BaseSignal):
    key = "same_equipment"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        result = _shared_identifier(
            key=self.key,
            prior=pair.prior.equipment_id,
            followup=pair.followup.equipment_id,
            label="Equipment",
        )
        if result.outcome is SignalOutcome.MATCHED and pair.equipment_serial:
            serial_suffix = pair.equipment_serial[-4:]
            return SignalResult(
                key=self.key,
                outcome=result.outcome,
                strength=result.strength,
                raw_value={"same": True, "serial_suffix": serial_suffix},
                explanation=f"Same equipment (serial ending {serial_suffix}).",
            )
        return result


class SameServiceCategorySignal(BaseSignal):
    key = "same_service_category"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        return _shared_identifier(
            key=self.key,
            prior=pair.prior.service_category_id,
            followup=pair.followup.service_category_id,
            label="Service category",
        )


class SameTechnicianSignal(BaseSignal):
    key = "same_technician"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        return _shared_identifier(
            key=self.key,
            prior=pair.prior.technician_id,
            followup=pair.followup.technician_id,
            label="Technician",
        )
