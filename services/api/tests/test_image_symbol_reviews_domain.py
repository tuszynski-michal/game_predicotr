from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY, BoardTopology
from game_predictor_api.domain.image_reviews import ImageReviewAction, ImageReviewCell
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellCropApprovalState,
    SymbolCellQualityIssue,
    SymbolCellReview,
    SymbolCellReviewError,
    SymbolCellReviewState,
    approve_symbol_cell_review,
    derive_symbol_cell_board_resolution,
    invalidate_symbol_cell_reviews_for_geometry,
    is_symbol_cell_training_eligible,
    map_current_symbol_cell_reviews,
    mark_symbol_cell_grid_issue,
    mark_symbol_cell_unreadable,
    reassign_symbol_cell_review,
    resolve_unreadable_symbol_cell_review,
)


def _sha(seed: int) -> str:
    return f"{seed:064x}"


def _current_cells(
    *,
    checksum_offset: int = 0,
    predicted: str = "cherry",
    topology: BoardTopology = LEGACY_IMAGE_BOARD_TOPOLOGY,
) -> tuple[ImageReviewCell, ...]:
    return tuple(
        ImageReviewCell(
            observation_id=UUID(int=index + 1),
            cell_index=index,
            row_index=index // topology.columns,
            column_index=index % topology.columns,
            crop_sample_id=_sha(1_000 + checksum_offset + index),
            crop_relative_path=f"crops/{checksum_offset}-{index}.jpg",
            crop_checksum_sha256=_sha(2_000 + checksum_offset + index),
            predicted_symbol_code=predicted,
            confidence=0.9,
            alternatives=(),
            current_symbol_code=predicted,
        )
        for index in range(topology.cell_count)
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
    assert approved.review.quality_issue is None
    assert approved.review.crop_approval_state is SymbolCellCropApprovalState.CURRENT
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


def test_legacy_approved_crop_without_provenance_remains_idempotent_but_not_training() -> None:
    legacy = replace(
        _mapped_reviews()[0],
        review_state=SymbolCellReviewState.APPROVED,
        assignment_source=SymbolCellAssignmentSource.HUMAN,
    )

    repeated = approve_symbol_cell_review(legacy, active_symbol_codes=("cherry",))

    assert repeated.changed is False
    assert legacy.crop_approval_state is SymbolCellCropApprovalState.UNVERIFIED
    assert not is_symbol_cell_training_eligible(
        legacy,
        active_symbol_codes=("cherry",),
        is_current_owner=True,
        asset_checksum_verified=True,
    )


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
            quality_issue=SymbolCellQualityIssue.GRID_ISSUE,
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_GRID_ISSUE_STATE_INVALID"


def test_new_geometry_preserves_safe_labels_and_reopens_grid_issue() -> None:
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
    assert invalidated[3].review_state is SymbolCellReviewState.PENDING
    assert invalidated[3].quality_issue is None
    assert invalidated[3].assignment_source is SymbolCellAssignmentSource.MODEL
    assert all(
        review.review_state is SymbolCellReviewState.APPROVED
        for index, review in enumerate(invalidated)
        if index != 3
    )
    assert all(
        review.crop_approval_state is SymbolCellCropApprovalState.CHANGED_SINCE_APPROVAL
        for index, review in enumerate(invalidated)
        if index != 3
    )
    assert [review.crop.geometry_revision for review in invalidated] == [1] * 15
    assert invalidated[3].revision == marked[3].revision + 1
    assert invalidated[3].crop.crop_checksum_sha256 != marked[3].crop.crop_checksum_sha256

    with pytest.raises(SymbolCellReviewError, match="advance one shared revision") as error:
        invalidate_symbol_cell_reviews_for_geometry(
            existing_reviews=marked,
            current_cells=_current_cells(checksum_offset=100),
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID"


def test_mapping_requires_every_configured_row_major_current_crop() -> None:
    with pytest.raises(SymbolCellReviewError, match="every configured row-major") as error:
        map_current_symbol_cell_reviews(
            cells=_current_cells()[:-1],
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
            assignment_source=SymbolCellAssignmentSource.BACKFILL,
        )

    assert error.value.code == "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE"

    invalid_row = list(_current_cells())
    invalid_row[6] = replace(invalid_row[6], row_index=0)
    with pytest.raises(SymbolCellReviewError, match="configured row-major"):
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


def test_mapping_and_aggregation_support_a_non_legacy_topology() -> None:
    topology = BoardTopology(rows=2, columns=4)
    reviews = map_current_symbol_cell_reviews(
        cells=_current_cells(topology=topology),
        geometry_revision=0,
        cropper_version="manual-source-direct-v1",
        assignment_source=SymbolCellAssignmentSource.MODEL,
        topology=topology,
    )
    approved = tuple(
        approve_symbol_cell_review(review, active_symbol_codes=("cherry",)).review
        for review in reviews
    )

    resolution = derive_symbol_cell_board_resolution(
        reviews=approved,
        active_symbol_codes=("cherry",),
        topology=topology,
    )

    assert len(reviews) == 8
    assert resolution is not None
    assert resolution.symbol_codes == ("cherry",) * 8


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


def test_unreadable_crop_can_be_resolved_as_unknown_without_becoming_training_data() -> None:
    review = approve_symbol_cell_review(
        _mapped_reviews()[0],
        active_symbol_codes=("cherry",),
    ).review
    unreadable = mark_symbol_cell_unreadable(review).review
    resolved = resolve_unreadable_symbol_cell_review(
        unreadable,
        target_symbol_code=None,
        active_symbol_codes=("cherry",),
    ).review

    assert unreadable.review_state is SymbolCellReviewState.PENDING
    assert unreadable.quality_issue is SymbolCellQualityIssue.UNREADABLE
    assert resolved.review_state is SymbolCellReviewState.APPROVED
    assert resolved.assigned_symbol_code is None
    assert resolved.quality_issue is SymbolCellQualityIssue.UNREADABLE
    assert resolved.crop_approval_state is SymbolCellCropApprovalState.CURRENT
    assert not is_symbol_cell_training_eligible(
        resolved,
        active_symbol_codes=("cherry",),
        is_current_owner=True,
        asset_checksum_verified=True,
    )


def test_unknown_label_completes_the_board_as_corrected() -> None:
    approved = [
        approve_symbol_cell_review(review, active_symbol_codes=("cherry",)).review
        for review in _mapped_reviews()
    ]
    approved[5] = resolve_unreadable_symbol_cell_review(
        mark_symbol_cell_unreadable(approved[5]).review,
        target_symbol_code=None,
        active_symbol_codes=("cherry",),
    ).review

    resolution = derive_symbol_cell_board_resolution(
        reviews=approved,
        active_symbol_codes=("cherry",),
    )

    assert resolution is not None
    assert resolution.action is ImageReviewAction.CORRECTED
    assert resolution.symbol_codes[5] is None


def test_training_requires_current_approved_crop_owner_and_verified_asset() -> None:
    approved = approve_symbol_cell_review(
        _mapped_reviews()[0],
        active_symbol_codes=("cherry",),
    ).review
    recropped = invalidate_symbol_cell_reviews_for_geometry(
        existing_reviews=(approved, *_mapped_reviews()[1:]),
        current_cells=_current_cells(checksum_offset=100),
        geometry_revision=1,
        cropper_version="board-cell-crops-v19",
    )[0]

    assert is_symbol_cell_training_eligible(
        approved,
        active_symbol_codes=("cherry",),
        is_current_owner=True,
        asset_checksum_verified=True,
    )
    assert not is_symbol_cell_training_eligible(
        recropped,
        active_symbol_codes=("cherry",),
        is_current_owner=True,
        asset_checksum_verified=True,
    )
    assert not is_symbol_cell_training_eligible(
        approved,
        active_symbol_codes=("cherry",),
        is_current_owner=False,
        asset_checksum_verified=True,
    )
