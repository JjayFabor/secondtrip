"""Pure composite scoring for detection signals."""

from app.modules.detection.scoring.calculator import (
    ScoreOutcome,
    ScoringRule,
    ScoringRuleSet,
    score,
)

__all__ = ["ScoreOutcome", "ScoringRule", "ScoringRuleSet", "score"]
