from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellApprovedCropIdentity,
    SymbolCellAssignmentSource,
    SymbolCellCropApprovalState,
    SymbolCellCropIdentity,
    SymbolCellReview,
    SymbolCellReviewAction,
    SymbolCellReviewCursorDirection,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewState,
    SymbolCellWithoutImageIdentity,
    approve_symbol_cell_review,
    decode_symbol_cell_review_cursor,
    encode_symbol_cell_review_cursor,
    is_symbol_cell_training_eligible,
    mark_symbol_cell_blurry,
    mark_symbol_cell_unreadable,
    reassign_symbol_cell_review,
)
from game_predictor_api.schemas.image_symbol_reviews import (
    SymbolCellReviewBulkOperationRequest,
    to_symbol_cell_review_bulk_request,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
    _symbol_cell_review_from_model,
)
from game_predictor_api.storage.models import ImageSymbolReviewCellModel


def outside() -> SymbolCellReview:
    return SymbolCellReview(
        crop=SymbolCellWithoutImageIdentity(
            cell_index=4, geometry_revision=3, cropper_version="v19"
        ),
        predicted_symbol_code=None,
        assigned_symbol_code=None,
        review_state=SymbolCellReviewState.PENDING,
        has_grid_issue=False,
        assignment_source=SymbolCellAssignmentSource.GEOMETRY_PARTIAL,
        revision=1,
        source_visibility="outside",
    )


def test_outside_manual_assignment_has_no_approved_pixels_and_retry_is_noop() -> None:
    changed = reassign_symbol_cell_review(
        outside(), target_symbol_code="a", active_symbol_codes=("a", "b")
    )
    assert changed.changed
    assert changed.review.review_state is SymbolCellReviewState.APPROVED
    assert changed.review.approved_crop is None
    assert changed.review.crop.crop_sample_id is None
    assert changed.review.crop_approval_state is SymbolCellCropApprovalState.UNVERIFIED
    assert not reassign_symbol_cell_review(
        changed.review, target_symbol_code="a", active_symbol_codes=("a", "b")
    ).changed
    second = reassign_symbol_cell_review(
        changed.review, target_symbol_code="b", active_symbol_codes=("a", "b")
    )
    assert second.review.assigned_symbol_code == "b"
    assert second.review.source_visibility == "outside"
    assert not is_symbol_cell_training_eligible(
        second.review,
        active_symbol_codes=("a", "b"),
        is_current_owner=True,
        asset_checksum_verified=True,
    )
    unreadable = mark_symbol_cell_unreadable(second.review)
    assert unreadable.review.assigned_symbol_code == "b"
    assert unreadable.review.review_state is SymbolCellReviewState.PENDING
    assert unreadable.review.source_visibility == "outside"


@pytest.mark.parametrize("action", [approve_symbol_cell_review, mark_symbol_cell_blurry])
def test_outside_image_actions_have_a_stable_error(action) -> None:
    with pytest.raises(SymbolCellReviewError, match="requires an image") as error:
        action(outside(), active_symbol_codes=("a",))
    assert error.value.code == "SYMBOL_CELL_REVIEW_IMAGE_ACTION_UNAVAILABLE"


def test_null_identity_retains_revision_and_geometry_compare_and_swap() -> None:
    cell = ImageSymbolReviewCellModel(
        revision=1, geometry_revision=3, crop_sample_id=None, crop_checksum_sha256=None
    )
    command = SymbolCellReviewMutationCommand(
        game_id=UUID(int=1),
        cell_review_id=UUID(int=2),
        action=SymbolCellReviewAction.REASSIGN,
        expected_revision=1,
        expected_geometry_revision=3,
        expected_crop_sample_id=None,
        expected_crop_checksum_sha256=None,
        target_symbol_id=UUID(int=3),
        actor="operator",
    )
    SqlAlchemySymbolCellReviewMutationRepository._require_expected_identity(cell, command)
    for stale in [
        replace(command, expected_revision=0),
        replace(command, expected_geometry_revision=2),
        replace(command, expected_crop_sample_id="a" * 64, expected_crop_checksum_sha256="b" * 64),
    ]:
        with pytest.raises(SymbolCellReviewError):
            SqlAlchemySymbolCellReviewMutationRepository._require_expected_identity(cell, stale)
    with pytest.raises(SymbolCellReviewError):
        replace(command, expected_crop_sample_id="a" * 64)


def test_outside_cursor_and_bulk_snapshot_are_separate_from_unknown() -> None:
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ALL,
        outside_only=True,
        min_confidence=0.4,
    )
    assert review_filter.min_confidence is None
    cursor = encode_symbol_cell_review_cursor(
        review_filter=review_filter,
        direction=SymbolCellReviewCursorDirection.AFTER,
        key=(4, 3, UUID(int=2)),
    )
    with pytest.raises(SymbolCellReviewError):
        decode_symbol_cell_review_cursor(
            cursor,
            review_filter=replace(review_filter, outside_only=False),
            direction=SymbolCellReviewCursorDirection.AFTER,
        )

    def request(scope):
        return to_symbol_cell_review_bulk_request(
            SymbolCellReviewBulkOperationRequest.model_validate(
                {
                    "action": "mark_unreadable",
                    "selection": {
                        "kind": "filter",
                        "symbolId": scope,
                        "catalogRevision": 8,
                        "minConfidence": 0.8,
                    },
                }
            ),
            actor="operator",
        )

    assert request("outside").filter_selection.outside_only
    assert request("outside").filter_selection.min_confidence is None
    assert len({request(scope).command_sha256 for scope in ("outside", "unknown", "all")}) == 3


def test_model_conversion_uses_no_asset_variant_and_preserves_legacy_full() -> None:
    cell = ImageSymbolReviewCellModel(
        cell_index=4,
        geometry_revision=3,
        cropper_version="v19",
        asset_mode="none",
        source_visibility="outside",
        crop_sample_id=None,
        crop_checksum_sha256=None,
        assigned_symbol_id=UUID(int=3),
        review_state="approved",
        assignment_source="human",
        revision=2,
    )
    review = _symbol_cell_review_from_model(cell, symbol_code_by_id={UUID(int=3): "a"})
    assert isinstance(review.crop, SymbolCellWithoutImageIdentity)
    assert review.approved_crop is None
    assert review.source_visibility == "outside"
    cell.source_visibility = None
    with pytest.raises(SymbolCellReviewError):
        _symbol_cell_review_from_model(cell, symbol_code_by_id={UUID(int=3): "a"})


def test_partial_visibility_excludes_training_even_without_a_quality_flag() -> None:
    crop = SymbolCellCropIdentity(
        cell_index=4,
        geometry_revision=3,
        cropper_version="structured-v0.10",
        crop_sample_id="a" * 64,
        crop_checksum_sha256="b" * 64,
        crop_relative_path=None,
    )
    review = replace(
        outside(),
        crop=crop,
        source_visibility="partial",
        assigned_symbol_code="a",
        review_state=SymbolCellReviewState.APPROVED,
        approved_crop=SymbolCellApprovedCropIdentity.from_crop(crop),
    )
    assert review.quality_issue is None
    assert not is_symbol_cell_training_eligible(
        review, active_symbol_codes=("a",), is_current_owner=True, asset_checksum_verified=True
    )
