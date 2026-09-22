"""Pure composite scoring. See docs/architecture/07-detection-engine.md §5."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from app.modules.detection.schemas import RuleKind, ScoreBand
from app.modules.detection.scoring.bands import band_for
from app.modules.detection.signals.base import SignalOutcome, SignalResult

ZERO = Decimal(0)
ONE_HUNDRED = Decimal(100)


@dataclass(frozen=True, slots=True)
class ScoringRule:
    key: str
    kind: RuleKind
    weight: Decimal

    def __post_init__(self) -> None:
        if self.weight < ZERO:
            msg = "rule weight must not be negative"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ScoringRuleSet:
    rules: Mapping[str, ScoringRule]

    def __post_init__(self) -> None:
        copied = dict(self.rules)
        for key, rule in copied.items():
            if key != rule.key:
                msg = f"rule mapping key {key!r} does not match rule key {rule.key!r}"
                raise ValueError(msg)
        object.__setattr__(self, "rules", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class ScoreOutcome:
    raw: Decimal
    normalized: Decimal
    band: ScoreBand
    surfaced: bool
    suppressed: bool
    suppressed_by: str | None
    contributions: Mapping[str, Decimal]


def score(results: list[SignalResult], rule_set: ScoringRuleSet) -> ScoreOutcome:
    """Score one candidate using only the evidence evaluable for that pair."""

    _require_matching_keys(_index_results(results), rule_set.rules)

    evaluable = [result for result in results if result.outcome is not SignalOutcome.NOT_EVALUABLE]
    contributions = {
        result.key: _additive_contribution(result, rule_set.rules[result.key]) for result in results
    }

    for result in evaluable:
        rule = rule_set.rules[result.key]
        if rule.kind is RuleKind.VETO and result.outcome is SignalOutcome.MATCHED:
            return ScoreOutcome(
                raw=ZERO,
                normalized=ZERO,
                band=ScoreBand.LOW,
                surfaced=False,
                suppressed=True,
                suppressed_by=result.key,
                contributions=MappingProxyType(contributions),
            )

    raw = sum(contributions.values(), start=ZERO)
    multiplier = Decimal(1)
    for result in evaluable:
        rule = rule_set.rules[result.key]
        if rule.kind is RuleKind.MULTIPLIER and result.outcome is SignalOutcome.MATCHED:
            multiplier *= rule.weight
    raw *= multiplier

    max_possible = sum(
        (
            rule_set.rules[result.key].weight
            for result in evaluable
            if rule_set.rules[result.key].kind is RuleKind.ADDITIVE
        ),
        start=ZERO,
    )
    normalized = ZERO if max_possible == ZERO else raw / max_possible * ONE_HUNDRED
    normalized = max(ZERO, min(ONE_HUNDRED, normalized))

    surfaced = all(
        result.outcome is SignalOutcome.MATCHED
        for result in evaluable
        if rule_set.rules[result.key].kind is RuleKind.GATE
    )
    return ScoreOutcome(
        raw=raw,
        normalized=normalized,
        band=band_for(normalized),
        surfaced=surfaced,
        suppressed=False,
        suppressed_by=None,
        contributions=MappingProxyType(contributions),
    )


def _index_results(results: list[SignalResult]) -> dict[str, SignalResult]:
    indexed: dict[str, SignalResult] = {}
    for result in results:
        if result.key in indexed:
            msg = f"duplicate signal result: {result.key}"
            raise ValueError(msg)
        indexed[result.key] = result
    return indexed


def _require_matching_keys(
    results: Mapping[str, SignalResult],
    rules: Mapping[str, ScoringRule],
) -> None:
    result_keys = set(results)
    rule_keys = set(rules)
    if result_keys == rule_keys:
        return
    missing = sorted(rule_keys - result_keys)
    unexpected = sorted(result_keys - rule_keys)
    msg = f"signal results and scoring rules differ; missing={missing}, unexpected={unexpected}"
    raise ValueError(msg)


def _additive_contribution(result: SignalResult, rule: ScoringRule) -> Decimal:
    if rule.kind is not RuleKind.ADDITIVE or result.outcome is not SignalOutcome.MATCHED:
        return ZERO
    return rule.weight * result.strength
