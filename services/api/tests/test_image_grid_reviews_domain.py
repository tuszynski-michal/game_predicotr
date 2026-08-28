from __future__ import annotations

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewError,
    ImageGridReviewState,
    approve_image_grid_review,
    derive_image_grid_review,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellQualityIssue


def _issues(
    topology: BoardTopology,
    issue: SymbolCellQualityIssue | None = None,
) -> tuple[SymbolCellQualityIssue | None, ...]:
    return (issue, *((None,) * (topology.cell_count - 1)))


def test_grid_queue_state_is_derived_with_correction_priority() -> None:
    topology = BoardTopology(rows=2, columns=4)

    correction = derive_image_grid_review(
        topology=topology,
        geometry_revision=2,
        approved_geometry_revision=2,
        cell_quality_issues=_issues(topology, SymbolCellQualityIssue.GRID_ISSUE),
    )
    validation = derive_image_grid_review(
        topology=topology,
        geometry_revision=2,
        approved_geometry_revision=1,
        cell_quality_issues=_issues(topology),
    )
    approved = derive_image_grid_review(
        topology=topology,
        geometry_revision=2,
        approved_geometry_revision=2,
        cell_quality_issues=_issues(topology),
    )

    assert correction.state is ImageGridReviewState.NEEDS_CORRECTION
    assert validation.state is ImageGridReviewState.NEEDS_VALIDATION
    assert approved.state is ImageGridReviewState.APPROVED


def test_grid_approval_is_revision_bound_and_rejects_unfixed_grid_issues() -> None:
    topology = BoardTopology(rows=3, columns=5)
    review = derive_image_grid_review(
        topology=topology,
        geometry_revision=3,
        approved_geometry_revision=2,
        cell_quality_issues=_issues(topology),
    )
    transition = approve_image_grid_review(review)

    assert transition.changed is True
    assert transition.review.state is ImageGridReviewState.APPROVED
    assert transition.review.approved_geometry_revision == 3

    needs_correction = derive_image_grid_review(
        topology=topology,
        geometry_revision=3,
        approved_geometry_revision=2,
        cell_quality_issues=_issues(topology, SymbolCellQualityIssue.GRID_ISSUE),
    )
    with pytest.raises(ImageGridReviewError) as error:
        approve_image_grid_review(needs_correction)

    assert error.value.code == "IMAGE_GRID_REVIEW_CORRECTION_REQUIRED"
