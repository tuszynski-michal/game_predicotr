"""Fail-closed acceptance policy for the v0.10 geometry rollout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GeometryCutoverDecision = Literal[
    "insufficient_evidence",
    "legacy",
    "structured_review",
    "structured_default",
]

_MIN_SOURCE_COUNT = 100
_MIN_ACTIVE_BOARD_COUNT = 500
_MIN_QUALITY_BUCKET_COUNT = 5
_REVIEW_PERCENT = 95
_DEFAULT_PERCENT = 98


@dataclass(frozen=True, slots=True)
class GeometryCutoverEvidence:
    """Human-inspected, source-disjoint evidence for one engine version."""

    source_count: int
    active_board_count: int
    boards_accepted_without_correction: int
    quality_bucket_count: int
    includes_all_historical_failures: bool
    is_holdout: bool
    provenance_validation_ready: bool

    def __post_init__(self) -> None:
        values = (
            self.source_count,
            self.active_board_count,
            self.boards_accepted_without_correction,
            self.quality_bucket_count,
        )
        if any(value < 0 for value in values):
            raise ValueError("geometry cutover counts cannot be negative")
        if self.boards_accepted_without_correction > self.active_board_count:
            raise ValueError(
                "boards accepted without correction cannot exceed active boards"
            )

    @property
    def board_level_automatic_correctness(self) -> float | None:
        if self.active_board_count == 0:
            return None
        return self.boards_accepted_without_correction / self.active_board_count

    @property
    def meets_sample_contract(self) -> bool:
        return (
            self.source_count >= _MIN_SOURCE_COUNT
            and self.active_board_count >= _MIN_ACTIVE_BOARD_COUNT
            and self.quality_bucket_count >= _MIN_QUALITY_BUCKET_COUNT
            and self.includes_all_historical_failures
            and self.is_holdout
            and self.provenance_validation_ready
        )


@dataclass(frozen=True, slots=True)
class GeometryCutoverAssessment:
    decision: GeometryCutoverDecision
    board_level_automatic_correctness: float | None
    geometry_mode: str | None
    cell_asset_mode: str | None
    trigger_keypoint_fallback: bool
    reason_codes: tuple[str, ...]


def assess_geometry_cutover(
    evidence: GeometryCutoverEvidence,
) -> GeometryCutoverAssessment:
    """Return the only rollout level justified by immutable acceptance evidence."""

    reasons = _sample_failure_reasons(evidence)
    score = evidence.board_level_automatic_correctness
    if reasons:
        return GeometryCutoverAssessment(
            decision="insufficient_evidence",
            board_level_automatic_correctness=score,
            geometry_mode=None,
            cell_asset_mode=None,
            trigger_keypoint_fallback=False,
            reason_codes=reasons,
        )
    assert score is not None
    if (
        evidence.boards_accepted_without_correction * 100
        >= evidence.active_board_count * _DEFAULT_PERCENT
    ):
        return GeometryCutoverAssessment(
            decision="structured_default",
            board_level_automatic_correctness=score,
            geometry_mode="structured_default",
            cell_asset_mode="virtual_default",
            trigger_keypoint_fallback=False,
            reason_codes=(),
        )
    if (
        evidence.boards_accepted_without_correction * 100
        >= evidence.active_board_count * _REVIEW_PERCENT
    ):
        return GeometryCutoverAssessment(
            decision="structured_review",
            board_level_automatic_correctness=score,
            geometry_mode="structured_review",
            cell_asset_mode="virtual_shadow",
            trigger_keypoint_fallback=False,
            reason_codes=("GEOMETRY_CUTOVER_DEFAULT_THRESHOLD_NOT_MET",),
        )
    return GeometryCutoverAssessment(
        decision="legacy",
        board_level_automatic_correctness=score,
        geometry_mode="legacy",
        cell_asset_mode="legacy_files",
        trigger_keypoint_fallback=True,
        reason_codes=("GEOMETRY_CUTOVER_REVIEW_THRESHOLD_NOT_MET",),
    )


def _sample_failure_reasons(evidence: GeometryCutoverEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    if evidence.source_count < _MIN_SOURCE_COUNT:
        reasons.append("GEOMETRY_CUTOVER_SOURCE_SAMPLE_INCOMPLETE")
    if evidence.active_board_count < _MIN_ACTIVE_BOARD_COUNT:
        reasons.append("GEOMETRY_CUTOVER_BOARD_SAMPLE_INCOMPLETE")
    if evidence.quality_bucket_count < _MIN_QUALITY_BUCKET_COUNT:
        reasons.append("GEOMETRY_CUTOVER_QUALITY_BUCKETS_INCOMPLETE")
    if not evidence.includes_all_historical_failures:
        reasons.append("GEOMETRY_CUTOVER_HISTORICAL_FAILURES_MISSING")
    if not evidence.is_holdout:
        reasons.append("GEOMETRY_CUTOVER_HOLDOUT_REQUIRED")
    if not evidence.provenance_validation_ready:
        reasons.append("GEOMETRY_CUTOVER_PROVENANCE_NOT_READY")
    return tuple(reasons)


__all__ = [
    "GeometryCutoverAssessment",
    "GeometryCutoverDecision",
    "GeometryCutoverEvidence",
    "assess_geometry_cutover",
]
