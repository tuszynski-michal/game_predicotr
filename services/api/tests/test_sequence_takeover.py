"""D-543 (TASK-0971): the pure sequence ownership rule shared by API and worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from game_predictor_api.domain.sequence_takeover import (
    CANONICAL_OWNER_KEPT_REASON,
    EXISTING_OWNER_KEPT_REASON,
    NEWER_SAME_SOURCE_OWNER_KEPT_REASON,
    OLDER_SAME_SOURCE_OWNER_REPLACED_REASON,
    ImportOrder,
    PendingOwnerFacts,
    SequenceClaimOutcome,
    decide_sequence_claim,
)

_NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
_OLD = ImportOrder(_NOW, "00000000-0000-0000-0000-000000000001")
_NEW = ImportOrder(_NOW + timedelta(seconds=1), "00000000-0000-0000-0000-000000000002")


def _owner(checksum: str, order: ImportOrder = _OLD) -> PendingOwnerFacts:
    return PendingOwnerFacts(source_checksum_sha256=checksum, import_order=order)


def test_a_sequence_without_a_live_owner_is_taken_over() -> None:
    claim = decide_sequence_claim(
        canonical_exists=False,
        incumbent=None,
        incoming_source_checksum_sha256=None,
        incoming_order=_NEW,
    )
    assert claim.outcome is SequenceClaimOutcome.TAKE_OVER
    assert claim.incoming_owns
    assert claim.incoming_reason is None and claim.alternative_reason is None


@pytest.mark.parametrize("incumbent", [None, _owner("a" * 64)])
def test_a_canonical_owner_always_wins(incumbent: PendingOwnerFacts | None) -> None:
    claim = decide_sequence_claim(
        canonical_exists=True,
        incumbent=incumbent,
        incoming_source_checksum_sha256="a" * 64,
        incoming_order=_NEW,
    )
    assert claim.outcome is SequenceClaimOutcome.KEEP_CANONICAL
    assert not claim.incoming_owns
    assert claim.incoming_reason == CANONICAL_OWNER_KEPT_REASON
    assert claim.incumbent_reason is None and claim.alternative_reason is None


@pytest.mark.parametrize("order", [_OLD, _NEW], ids=["older", "newer"])
def test_a_live_owner_of_another_photo_is_kept_whatever_the_import_order(
    order: ImportOrder,
) -> None:
    claim = decide_sequence_claim(
        canonical_exists=False,
        incumbent=_owner("a" * 64, _OLD if order is _NEW else _NEW),
        incoming_source_checksum_sha256="b" * 64,
        incoming_order=order,
    )
    assert claim.outcome is SequenceClaimOutcome.KEEP_EXISTING_OWNER
    assert not claim.incoming_owns
    assert claim.incoming_reason == EXISTING_OWNER_KEPT_REASON
    assert claim.alternative_reason == EXISTING_OWNER_KEPT_REASON
    assert claim.incumbent_reason is None


def test_an_unknown_incoming_checksum_never_counts_as_the_same_photo() -> None:
    claim = decide_sequence_claim(
        canonical_exists=False,
        incumbent=_owner("a" * 64),
        incoming_source_checksum_sha256=None,
        incoming_order=_NEW,
    )
    assert claim.outcome is SequenceClaimOutcome.KEEP_EXISTING_OWNER


def test_the_same_photo_keeps_the_newest_import_order() -> None:
    newer = decide_sequence_claim(
        canonical_exists=False,
        incumbent=_owner("a" * 64, _OLD),
        incoming_source_checksum_sha256="a" * 64,
        incoming_order=_NEW,
    )
    assert newer.outcome is SequenceClaimOutcome.REPLACE_SAME_SOURCE
    assert newer.incoming_owns
    assert newer.incumbent_reason == OLDER_SAME_SOURCE_OWNER_REPLACED_REASON
    assert newer.incoming_reason is None and newer.alternative_reason is None

    for incoming in (_OLD, ImportOrder(_OLD.created_at, _OLD.job_id)):
        older = decide_sequence_claim(
            canonical_exists=False,
            incumbent=_owner("a" * 64, _NEW if incoming is _OLD else _OLD),
            incoming_source_checksum_sha256="a" * 64,
            incoming_order=incoming,
        )
        assert older.outcome is SequenceClaimOutcome.KEEP_NEWER_SAME_SOURCE
        assert older.incoming_reason == NEWER_SAME_SOURCE_OWNER_KEPT_REASON
        assert not older.incoming_owns


def test_a_replacement_board_recrops_the_cells_of_a_rejected_board_of_revision_zero() -> None:
    """The handoff does not require the new board to continue the old revision."""

    from game_predictor_api.domain.image_symbol_reviews import (
        SymbolCellAssignmentSource,
        SymbolCellReviewError,
        SymbolCellReviewState,
        approve_symbol_cell_review,
        invalidate_symbol_cell_reviews_for_geometry,
    )
    from test_image_symbol_reviews_domain import _current_cells, _mapped_reviews

    approved = tuple(
        approve_symbol_cell_review(review, active_symbol_codes=("cherry",)).review
        for review in _mapped_reviews()
    )
    with pytest.raises(SymbolCellReviewError) as error:
        invalidate_symbol_cell_reviews_for_geometry(
            existing_reviews=approved,
            current_cells=_current_cells(checksum_offset=100),
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
        )
    assert error.value.code == "SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID"

    moved = invalidate_symbol_cell_reviews_for_geometry(
        existing_reviews=approved,
        current_cells=_current_cells(checksum_offset=100),
        geometry_revision=0,
        cropper_version="board-cell-crops-v19",
        handoff_from_rejected_board=True,
    )
    # Every other recrop rule applies: new pixels need a new check.
    assert len(moved) == 15
    assert all(
        review.review_state is SymbolCellReviewState.PENDING
        and review.assignment_source is SymbolCellAssignmentSource.HUMAN
        and review.crop.geometry_revision == 0
        for review in moved
    )


def test_a_handoff_accepts_the_incomplete_history_of_a_rejected_partial_board() -> None:
    from game_predictor_api.domain.image_symbol_reviews import (
        SymbolCellReviewError,
        invalidate_symbol_cell_reviews_for_geometry,
    )
    from test_image_symbol_reviews_domain import _current_cells, _mapped_reviews

    history = _mapped_reviews()[2:]
    with pytest.raises(SymbolCellReviewError) as error:
        invalidate_symbol_cell_reviews_for_geometry(
            existing_reviews=history,
            current_cells=_current_cells(checksum_offset=100),
            geometry_revision=1,
            cropper_version="board-cell-crops-v19",
        )
    assert error.value.code == "SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE"

    moved = invalidate_symbol_cell_reviews_for_geometry(
        existing_reviews=history,
        current_cells=_current_cells(checksum_offset=100),
        geometry_revision=0,
        cropper_version="board-cell-crops-v19",
        handoff_from_rejected_board=True,
    )
    assert [review.cell_index for review in moved] == list(range(15))
    # The new board's cells must still be complete.
    with pytest.raises(SymbolCellReviewError):
        invalidate_symbol_cell_reviews_for_geometry(
            existing_reviews=history,
            current_cells=_current_cells(checksum_offset=100)[:-1],
            geometry_revision=0,
            cropper_version="board-cell-crops-v19",
            handoff_from_rejected_board=True,
        )
