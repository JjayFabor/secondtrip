"""Time-window and recurrence signals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.modules.detection.schemas import SignalOutcome
from app.modules.detection.signals.base import BaseSignal, CandidatePair, SignalResult

ZERO = Decimal(0)


class DaysBetweenSignal(BaseSignal):
    key = "days_between"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        bands = params.get("bands")
        if not isinstance(bands, list):
            raise ValueError("days_between params.bands must be a list")
        for band in bands:
            if not isinstance(band, list) or len(band) != 3:
                raise ValueError("each days_between band must contain start, end, and strength")
            start, end, raw_strength = band
            if not isinstance(start, int) or not isinstance(end, int):
                raise ValueError("days_between band boundaries must be integers")
            try:
                strength = Decimal(str(raw_strength))
            except InvalidOperation as exc:
                raise ValueError("days_between band strength must be decimal-compatible") from exc
            if start <= pair.days_between <= end:
                return SignalResult(
                    key=self.key,
                    outcome=SignalOutcome.MATCHED,
                    strength=strength,
                    raw_value={"days": pair.days_between},
                    explanation=(
                        f"Visits were {pair.days_between} calendar day"
                        f"{'s' if pair.days_between != 1 else ''} apart."
                    ),
                )
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.NOT_MATCHED,
            strength=ZERO,
            raw_value={"days": pair.days_between},
            explanation=f"The {pair.days_between}-day gap is outside configured score bands.",
        )


class RecurrenceDensitySignal(BaseSignal):
    key = "recurrence_density"

    def evaluate(self, pair: CandidatePair, params: dict[str, object]) -> SignalResult:
        minimum = params.get("minimum_visits", 3)
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
            raise ValueError("recurrence_density minimum_visits must be a positive integer")
        matched = pair.recurrence_count >= minimum
        return SignalResult(
            key=self.key,
            outcome=SignalOutcome.MATCHED if matched else SignalOutcome.NOT_MATCHED,
            strength=Decimal(1) if matched else ZERO,
            raw_value={"visits": pair.recurrence_count, "minimum_visits": minimum},
            explanation=(
                f"{pair.recurrence_count} related visits occurred inside the detection window."
            ),
        )
