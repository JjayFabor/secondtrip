"""Blocked candidate generation and stable candidate upserts."""

from app.modules.detection.generation.runner import (
    CandidateGenerationOutcome,
    generate_candidates,
)

__all__ = ["CandidateGenerationOutcome", "generate_candidates"]
