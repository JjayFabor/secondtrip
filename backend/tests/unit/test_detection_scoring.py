from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.detection.schemas import RuleKind, ScoreBand
from app.modules.detection.scoring.bands import band_for
from app.modules.detection.scoring.calculator import ScoringRule, ScoringRuleSet, score
from app.modules.detection.signals.base import SignalOutcome, SignalResult


def signal(
    key: str,
    outcome: SignalOutcome,
    *,
    strength: str = "1",
) -> SignalResult:
    return SignalResult(
        key=key,
        outcome=outcome,
        strength=Decimal(strength),
        raw_value={},
        explanation=key.replace("_", " "),
    )


def rules(*values: tuple[str, RuleKind, str]) -> ScoringRuleSet:
    return ScoringRuleSet(
        rules={
            key: ScoringRule(key=key, kind=kind, weight=Decimal(weight))
            for key, kind, weight in values
        }
    )


def test_known_signal_set_produces_known_score() -> None:
    outcome = score(
        [
            signal("same_customer", SignalOutcome.MATCHED),
            signal("days_between", SignalOutcome.MATCHED, strength="0.8"),
            signal("same_category", SignalOutcome.NOT_MATCHED),
        ],
        rules(
            ("same_customer", RuleKind.ADDITIVE, "20"),
            ("days_between", RuleKind.ADDITIVE, "25"),
            ("same_category", RuleKind.ADDITIVE, "10"),
        ),
    )

    assert outcome.raw == Decimal("40.0")
    assert outcome.normalized == Decimal("40") / Decimal("55") * Decimal("100")
    assert outcome.band is ScoreBand.MEDIUM
    assert outcome.surfaced is True
    assert outcome.contributions["days_between"] == Decimal("20.0")


def test_not_evaluable_is_excluded_from_numerator_and_denominator() -> None:
    outcome = score(
        [
            signal("same_customer", SignalOutcome.MATCHED),
            signal("same_equipment", SignalOutcome.NOT_EVALUABLE, strength="0"),
        ],
        rules(
            ("same_customer", RuleKind.ADDITIVE, "20"),
            ("same_equipment", RuleKind.ADDITIVE, "30"),
        ),
    )

    assert outcome.raw == Decimal("20")
    assert outcome.normalized == Decimal("100")
    assert outcome.band is ScoreBand.HIGH


def test_veto_suppresses_regardless_of_additive_matches() -> None:
    outcome = score(
        [
            signal("same_equipment", SignalOutcome.MATCHED),
            signal("scheduled_maintenance", SignalOutcome.MATCHED),
        ],
        rules(
            ("same_equipment", RuleKind.ADDITIVE, "30"),
            ("scheduled_maintenance", RuleKind.VETO, "0"),
        ),
    )

    assert outcome.suppressed is True
    assert outcome.suppressed_by == "scheduled_maintenance"
    assert outcome.surfaced is False
    assert outcome.raw == Decimal("0")


def test_unmatched_gate_hides_candidate_but_preserves_score() -> None:
    outcome = score(
        [
            signal("same_customer", SignalOutcome.MATCHED),
            signal("required_marker", SignalOutcome.NOT_MATCHED, strength="0"),
        ],
        rules(
            ("same_customer", RuleKind.ADDITIVE, "20"),
            ("required_marker", RuleKind.GATE, "0"),
        ),
    )

    assert outcome.raw == Decimal("20")
    assert outcome.normalized == Decimal("100")
    assert outcome.surfaced is False
    assert outcome.suppressed is False


def test_multiplier_result_is_independent_of_evaluation_order() -> None:
    rule_set = rules(
        ("base", RuleKind.ADDITIVE, "25"),
        ("first_multiplier", RuleKind.MULTIPLIER, "1.2"),
        ("second_multiplier", RuleKind.MULTIPLIER, "1.5"),
    )
    values = [
        signal("base", SignalOutcome.MATCHED),
        signal("first_multiplier", SignalOutcome.MATCHED),
        signal("second_multiplier", SignalOutcome.MATCHED),
    ]

    assert score(values, rule_set) == score(list(reversed(values)), rule_set)
    assert score(values, rule_set).raw == Decimal("45.00")


def test_normalized_score_is_clamped_to_one_hundred() -> None:
    outcome = score(
        [
            signal("base", SignalOutcome.MATCHED),
            signal("multiplier", SignalOutcome.MATCHED),
        ],
        rules(
            ("base", RuleKind.ADDITIVE, "10"),
            ("multiplier", RuleKind.MULTIPLIER, "2"),
        ),
    )

    assert outcome.raw == Decimal("20")
    assert outcome.normalized == Decimal("100")


def test_all_zero_weights_score_zero_without_division() -> None:
    outcome = score(
        [signal("same_customer", SignalOutcome.MATCHED)],
        rules(("same_customer", RuleKind.ADDITIVE, "0")),
    )

    assert outcome.raw == Decimal("0")
    assert outcome.normalized == Decimal("0")
    assert isinstance(outcome.raw, Decimal)
    assert isinstance(outcome.normalized, Decimal)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("49.99", ScoreBand.LOW),
        ("50.00", ScoreBand.MEDIUM),
        ("74.99", ScoreBand.MEDIUM),
        ("75.00", ScoreBand.HIGH),
    ],
)
def test_band_boundaries(value: str, expected: ScoreBand) -> None:
    assert band_for(Decimal(value)) is expected


def test_not_evaluable_veto_does_not_suppress() -> None:
    outcome = score(
        [
            signal("same_customer", SignalOutcome.MATCHED),
            signal("scheduled_maintenance", SignalOutcome.NOT_EVALUABLE, strength="0"),
        ],
        rules(
            ("same_customer", RuleKind.ADDITIVE, "20"),
            ("scheduled_maintenance", RuleKind.VETO, "0"),
        ),
    )

    assert outcome.suppressed is False
    assert outcome.normalized == Decimal("100")


def test_signal_strength_must_be_a_decimal_between_zero_and_one() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        signal("days_between", SignalOutcome.MATCHED, strength="1.01")


def test_mismatched_signal_and_rule_keys_fail_closed() -> None:
    with pytest.raises(ValueError, match=r"missing=\['same_equipment'\]"):
        score(
            [signal("same_customer", SignalOutcome.MATCHED)],
            rules(
                ("same_customer", RuleKind.ADDITIVE, "20"),
                ("same_equipment", RuleKind.ADDITIVE, "30"),
            ),
        )
