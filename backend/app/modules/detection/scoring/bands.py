"""Detection score-band boundaries. See architecture 07 §5."""

from decimal import Decimal

from app.modules.detection.schemas import ScoreBand

HIGH_SCORE_MINIMUM = Decimal("75")
MEDIUM_SCORE_MINIMUM = Decimal("50")


def band_for(normalized_score: Decimal) -> ScoreBand:
    if normalized_score >= HIGH_SCORE_MINIMUM:
        return ScoreBand.HIGH
    if normalized_score >= MEDIUM_SCORE_MINIMUM:
        return ScoreBand.MEDIUM
    return ScoreBand.LOW
