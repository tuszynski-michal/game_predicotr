from __future__ import annotations

from uuid import uuid4

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewCursorDirection,
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewState,
    ImageGridReviewView,
    approve_image_grid_review,
    decode_image_grid_review_cursor,
    derive_image_grid_review,
    encode_image_grid_review_cursor,
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


def test_grid_review_cursor_is_bound_to_game_view_import_and_direction() -> None:
    review_filter = ImageGridReviewListFilter(
        game_id=uuid4(),
        view=ImageGridReviewView.NEEDS_VALIDATION,
        import_job_id=uuid4(),
    )
    key = (101, str(uuid4()))
    cursor = encode_image_grid_review_cursor(
        review_filter=review_filter,
        direction=ImageGridReviewCursorDirection.AFTER,
        key=key,
    )

    assert (
        decode_image_grid_review_cursor(
            cursor,
            review_filter=review_filter,
            direction=ImageGridReviewCursorDirection.AFTER,
        )
        == key
    )
    with pytest.raises(ImageGridReviewError) as wrong_view:
        decode_image_grid_review_cursor(
            cursor,
            review_filter=ImageGridReviewListFilter(
                game_id=review_filter.game_id,
                view=ImageGridReviewView.ALL,
                import_job_id=review_filter.import_job_id,
            ),
            direction=ImageGridReviewCursorDirection.AFTER,
        )
    with pytest.raises(ImageGridReviewError) as wrong_direction:
        decode_image_grid_review_cursor(
            cursor,
            review_filter=review_filter,
            direction=ImageGridReviewCursorDirection.BEFORE,
        )

    assert wrong_view.value.code == "IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID"
    assert wrong_direction.value.code == "IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID"
