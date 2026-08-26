from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.domain.image_reviews import ImageReviewAction, ImageReviewCell
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellReview,
    SymbolCellReviewError,
    SymbolCellReviewState,
    approve_symbol_cell_review,
    derive_symbol_cell_board_resolution,
    invalidate_symbol_cell_reviews_for_geometry,
    map_current_symbol_cell_reviews,
    mark_symbol_cell_grid_issue,
    reassign_symbol_cell_review,
)


def _sha(seed: int) -> str:
    return f"{seed:064x}"


def _current_cells(
    *, checksum_offset: int = 0, predicted: str = "cherry"
) -> tuple[ImageReviewCell, ...]:
    return tuple(
        ImageReviewCell(
            observation_id=UUID(int=index + 1),
            cell_index=index,
            row_index=index // 5,
            column_index=index % 5,
            crop_sample_id=_sha(1_000 + checksum_offset + index),
            crop_relative_path=f"crops/{checksum_offset}-{index}.jpg",
            crop_checksum_sha256=_sha(2_000 + checksum_offset + index),
            predicted_symbol_code=predicted,
            confidence=0.9,
            alternatives=(),
            current_symbol_code=predicted,
        )
        for index in range(15)
    )


def _mapped_reviews(*, predicted: str = "cherry"):
    return map_current_symbol_cell_reviews(
        cells=_current_cells(predicted=predicted),
        geometry_revision=0,
        cropper_version="board-cell-crops-v19",
        assignment_source=SymbolCellAssignmentSource.MODEL,
    )


def test_approve_requires_a_real_active_symbol_and_clears_grid_issue() -> None:
    review = _mapped_reviews()[0]
    unknown = replace(review, assigned_symbol_code=None)

    with pytest.raises(SymbolCellReviewError, match="active real game symbol") as error:
        approve_symbol_cell_review(unknown, active_symbol_codes=("cherry",))

    assert error.value.code == "SYMBOL_CELL_REVIEW_SYMBOL_INVALID"

    marked = mark_symbol_cell_grid_issue(review).review
    approved = approve_symbol_cell_review(marked, active_symbol_codes=("cherry",))

    assert approved.changed is True
    assert approved.review.review_state is SymbolCellReviewState.APPROVED
    assert approved.review.has_grid_issue is False
    assert approved.review.assignment_source is SymbolCellAssignmentSource.HUMAN
    assert approved.review.revision == review.revision + 2


def test_reassign_approves_and_is_idempotent_for_the_same_current_crop() -> None:
    review = _mapped_reviews()[4]

    reassigned = reassign_symbol_cell_review(
        review,
        target_symbol_code="wild",
        active_symbol_codes=("cherry", "wild"),
    )
    repeated = reassign_symbol_cell_review(
        reassigned.review,
        target_symbol_code="wild",
        active_symbol_codes=("cherry", "wild"),
    )

    assert reassigned.changed is True
    assert reassigned.review.assigned_symbol_code == "wild"
    assert reassigned.review.review_state is SymbolCellReviewState.APPROVED
    assert reassigned.review.assignment_source is SymbolCellAssignmentSource.HUMAN
    assert repeated.changed is False
    assert repeated.review == reassigned.review


def test_grid_issue_must_remain_pending() -> None:
    review = _mapped_reviews()[0]

    with pytest.raises(SymbolCellReviewError, match="must remain pending") as error:
        SymbolCellReview(
            crop=review.crop,
            predicted_symbol_code=review.predicted_symbol_code,
            assigned_symbol_code=review.assigned_symbol_code,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=True,
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=0,
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_GRID_ISSUE_STATE_INVALID"


def test_new_geometry_invalidates_all_fifteen_current_crop_reviews() -> None:
    initial = _mapped_reviews()
    approved = tuple(
        approve_symbol_cell_review(review, active_symbol_codes=("cherry",)).review
        for review in initial
    )
    marked = (*approved[:3], mark_symbol_cell_grid_issue(approved[3]).review, *approved[4:])

    invalidated = invalidate_symbol_cell_reviews_for_geometry(
        existing_reviews=marked,
        current_cells=_current_cells(checksum_offset=100),
        geometry_revision=1,
        cropper_version="board-cell-crops-v19",
    )

    assert len(invalidated) == 15
    assert all(review.review_state is SymbolCellReviewState.PENDING for review in invalidated)
    assert all(review.has_grid_issue is False for review in invalidated)
    assert all(
        review.assignment_source is SymbolCellAssignmentSource.MODEL for review in invalidated
    )
    assert [review.crop.geometry_revision for review in invalidated] == [1] * 15
    assert invalidated[3].revision == marked[3].revision + 1
    assert invalidated[3].crop.crop_checksum_sha256 != marked[3].crop.crop_checksum_sha256

    with pytest.raises(
        SymbolCellReviewError, match="advance one shared geometry revision"
    ) as error:
        invalidate_symbol_cell_reviews_for_geometry(
            existing_reviews=marked,
            current_cells=_current_cells(checksum_offset=100),
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID"


def test_mapping_requires_exactly_fifteen_row_major_current_crops() -> None:
    with pytest.raises(SymbolCellReviewError, match="0..14 exactly once") as error:
        map_current_symbol_cell_reviews(
            cells=_current_cells()[:-1],
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
            assignment_source=SymbolCellAssignmentSource.BACKFILL,
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE"

    invalid_row = list(_current_cells())
    invalid_row[6] = replace(invalid_row[6], row_index=0)
    with pytest.raises(SymbolCellReviewError, match="row-major indexes"):
        map_current_symbol_cell_reviews(
            cells=invalid_row,
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
            assignment_source=SymbolCellAssignmentSource.BACKFILL,
        )

    invalid_checksum = list(_current_cells())
    invalid_checksum[10] = replace(invalid_checksum[10], crop_checksum_sha256="not-a-sha256")
    with pytest.raises(SymbolCellReviewError, match="SHA-256") as checksum_error:
        map_current_symbol_cell_reviews(
            cells=invalid_checksum,
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
            assignment_source=SymbolCellAssignmentSource.BACKFILL,
        )

    assert checksum_error.value.code == "SYMBOL_CELL_REVIEW_CROP_IDENTITY_INVALID"


def test_all_approved_cells_choose_accepted_or_corrected_board_resolution() -> None:
    approved = tuple(
        approve_symbol_cell_review(review, active_symbol_codes=("cherry", "wild")).review
        for review in _mapped_reviews()
    )

    accepted = derive_symbol_cell_board_resolution(
        reviews=approved,
        active_symbol_codes=("cherry", "wild"),
    )
    corrected_reviews = list(approved)
    corrected_reviews[8] = reassign_symbol_cell_review(
        corrected_reviews[8],
        target_symbol_code="wild",
        active_symbol_codes=("cherry", "wild"),
    ).review
    corrected = derive_symbol_cell_board_resolution(
        reviews=corrected_reviews,
        active_symbol_codes=("cherry", "wild"),
    )
    incomplete = derive_symbol_cell_board_resolution(
        reviews=(mark_symbol_cell_grid_issue(corrected_reviews[0]).review, *corrected_reviews[1:]),
        active_symbol_codes=("cherry", "wild"),
    )

    assert accepted is not None
    assert accepted.action is ImageReviewAction.ACCEPTED
    assert accepted.symbol_codes == ("cherry",) * 15
    assert corrected is not None
    assert corrected.action is ImageReviewAction.CORRECTED
    assert corrected.symbol_codes[8] == "wild"
    assert incomplete is None
