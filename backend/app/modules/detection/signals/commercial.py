"""Commercial, warranty, and part signals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.modules.detection.schemas import SignalOutcome
from app.modules.detection.signals.base import BaseSignal, CandidatePair, SignalResult

ZERO = Decimal(0)
ONE = Decimal(1)


class ZeroValueFollowupSignal(BaseSignal):
    key = "zero_value_followup"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        value = pair.followup.revenue_amount
        if value is None:
            return _not_evaluable(self.key, "Follow-up revenue was not recorded.")
        matched = value == ZERO
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={"followup_revenue": str(value)},
            explanation=(
                "Follow-up revenue was recorded as zero."
                if matched
                else f"Follow-up revenue was {value}."
            ),
        )


class LowValueFollowupSignal(BaseSignal):
    key = "low_value_followup"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        prior = pair.prior.revenue_amount
        followup = pair.followup.revenue_amount
        if prior is None or followup is None or prior <= ZERO:
            return _not_evaluable(self.key, "Both visits need positive comparable revenue.")
        try:
            maximum_ratio = Decimal(str(params.get("maximum_ratio", "0.20")))
        except InvalidOperation as exc:
            raise ValueError("low_value_followup maximum_ratio must be decimal-compatible") from exc
        if not ZERO <= maximum_ratio <= ONE:
            raise ValueError("low_value_followup maximum_ratio must be between 0 and 1")
        ratio = followup / prior
        matched = ratio < maximum_ratio
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={
                "prior_revenue": str(prior),
                "followup_revenue": str(followup),
                "ratio": str(ratio),
            },
            explanation=f"Follow-up revenue was {ratio:.0%} of the prior visit.",
        )


class WarrantyMarkerSignal(BaseSignal):
    key = "warranty_marker"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        matched = pair.followup.is_warranty
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={"is_warranty": matched},
            explanation=(
                "Follow-up was marked as warranty work."
                if matched
                else "Follow-up was not marked as warranty work."
            ),
        )


class WithinEquipmentWarrantySignal(BaseSignal):
    key = "within_equipment_warranty"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        expires_on = pair.equipment_warranty_expires_on
        if pair.followup.equipment_id is None or expires_on is None:
            return _not_evaluable(self.key, "Equipment warranty expiry was not recorded.")
        matched = pair.followup.service_date <= expires_on
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={"warranty_expires_on": expires_on.isoformat()},
            explanation=(
                f"Follow-up occurred {'within' if matched else 'after'} the equipment warranty."
            ),
        )


class RepeatPartCodeSignal(BaseSignal):
    key = "repeat_part_code"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        if not pair.prior.part_codes or not pair.followup.part_codes:
            return _not_evaluable(self.key, "Both visits need recorded part codes.")
        repeated = sorted(pair.prior.part_codes & pair.followup.part_codes)
        matched = bool(repeated)
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=ONE if matched else ZERO,
            raw_value={"repeated_codes": repeated},
            explanation=(
                f"Repeated part code: {', '.join(repeated[:3])}."
                if matched
                else "No part code appeared on both visits."
            ),
        )


def _not_evaluable(key: str, explanation: str) -> SignalResult:
    return SignalResult(
        key=key,
        outcome=SignalOutcome.NOT_EVALUABLE,
        strength=ZERO,
        raw_value={},
        explanation=explanation,
    )
