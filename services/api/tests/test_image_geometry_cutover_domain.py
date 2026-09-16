from __future__ import annotations

import pytest
from game_predictor_api.domain.image_geometry_cutover import (
    GeometryCutoverEvidence,
    assess_geometry_cutover,
)


def _evidence(
    *, accepted: int, boards: int = 500, sources: int = 100
) -> GeometryCutoverEvidence:
    return GeometryCutoverEvidence(
        source_count=sources,
        active_board_count=boards,
        boards_accepted_without_correction=accepted,
        quality_bucket_count=5,
        includes_all_historical_failures=True,
        is_holdout=True,
        provenance_validation_ready=True,
    )


@pytest.mark.parametrize(
    ("accepted", "decision", "geometry_mode", "cell_asset_mode", "fallback"),
    [
        (490, "structured_default", "structured_default", "virtual_default", False),
        (489, "structured_review", "structured_review", "virtual_shadow", False),
        (475, "structured_review", "structured_review", "virtual_shadow", False),
        (474, "legacy", "legacy", "legacy_files", True),
    ],
)
def test_cutover_uses_exact_board_level_thresholds(
    accepted: int,
    decision: str,
    geometry_mode: str,
    cell_asset_mode: str,
    fallback: bool,
) -> None:
    assessment = assess_geometry_cutover(_evidence(accepted=accepted))

    assert assessment.decision == decision
    assert assessment.geometry_mode == geometry_mode
    assert assessment.cell_asset_mode == cell_asset_mode
    assert assessment.trigger_keypoint_fallback is fallback


def test_incomplete_evidence_cannot_recommend_a_rollout_change() -> None:
    evidence = GeometryCutoverEvidence(
        source_count=99,
        active_board_count=499,
        boards_accepted_without_correction=499,
        quality_bucket_count=4,
        includes_all_historical_failures=False,
        is_holdout=False,
        provenance_validation_ready=False,
    )

    assessment = assess_geometry_cutover(evidence)

    assert assessment.decision == "insufficient_evidence"
    assert assessment.geometry_mode is None
    assert assessment.cell_asset_mode is None
    assert assessment.trigger_keypoint_fallback is False
    assert assessment.reason_codes == (
        "GEOMETRY_CUTOVER_SOURCE_SAMPLE_INCOMPLETE",
        "GEOMETRY_CUTOVER_BOARD_SAMPLE_INCOMPLETE",
        "GEOMETRY_CUTOVER_QUALITY_BUCKETS_INCOMPLETE",
        "GEOMETRY_CUTOVER_HISTORICAL_FAILURES_MISSING",
        "GEOMETRY_CUTOVER_HOLDOUT_REQUIRED",
        "GEOMETRY_CUTOVER_PROVENANCE_NOT_READY",
    )


def test_empty_board_sample_has_no_score_and_never_triggers_fallback() -> None:
    assessment = assess_geometry_cutover(_evidence(accepted=0, boards=0))

    assert assessment.decision == "insufficient_evidence"
    assert assessment.board_level_automatic_correctness is None
    assert assessment.trigger_keypoint_fallback is False


@pytest.mark.parametrize(
    "values",
    [
        {"source_count": -1},
        {"active_board_count": -1},
        {"boards_accepted_without_correction": -1},
        {"quality_bucket_count": -1},
    ],
)
def test_negative_evidence_counts_are_rejected(values: dict[str, int]) -> None:
    kwargs = {
        "source_count": 100,
        "active_board_count": 500,
        "boards_accepted_without_correction": 490,
        "quality_bucket_count": 5,
        "includes_all_historical_failures": True,
        "is_holdout": True,
        "provenance_validation_ready": True,
    }
    kwargs.update(values)

    with pytest.raises(ValueError):
        GeometryCutoverEvidence(**kwargs)


def test_accepted_board_count_cannot_exceed_denominator() -> None:
    with pytest.raises(ValueError):
        _evidence(accepted=501)
