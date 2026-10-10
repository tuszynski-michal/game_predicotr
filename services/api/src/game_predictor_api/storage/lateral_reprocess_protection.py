"""Opt-in per-sequence protection of human work during v4 reprocessing."""

from collections.abc import Iterable, Mapping
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.neural_crop_policy import (
    NEURAL_AUTO_CROP_PAYLOAD_KEY,
    NEURAL_AUTO_CROP_POLICY,
)

from .image_review_repository import acquire_image_sequence_locks
from .models import (
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)


def lock_lateral_sequences(
    session: Session, *, job: JobModel, sequence_numbers: Iterable[int]
) -> None:
    """Reserve every sequence before locking source rows, as the editor does."""
    rollout = job.input_payload.get("image_geometry_rollout")
    if (
        isinstance(rollout, Mapping) and rollout.get("lateralPartialGeometry") is not None
    ) or job.input_payload.get(NEURAL_AUTO_CROP_PAYLOAD_KEY) == NEURAL_AUTO_CROP_POLICY:
        assert job.game_id is not None
        acquire_image_sequence_locks(
            session, game_id=job.game_id, sequence_numbers=set(sequence_numbers)
        )


def lock_projection_sequences(
    session: Session, *, job: JobModel, sequence_numbers: Iterable[int]
) -> None:
    """Every import projection reserves all its sequences before the source row.

    TASK-0950: the global lock order is ownership -> sequences -> sources; the
    import writer used to take a board's sequence lock only after its source
    row (except for the lateral rollout, which reserved them here already).
    """

    assert job.game_id is not None
    acquire_image_sequence_locks(
        session, game_id=job.game_id, sequence_numbers=set(sequence_numbers)
    )


def has_protected_lateral_owner(
    session: Session,
    *,
    job: JobModel,
    sequence_number: int,
    source_checksum_sha256: str,
) -> bool:
    rollout = job.input_payload.get("image_geometry_rollout")
    if (
        not isinstance(rollout, Mapping) or rollout.get("lateralPartialGeometry") is None
    ) and job.input_payload.get(NEURAL_AUTO_CROP_PAYLOAD_KEY) != NEURAL_AUTO_CROP_POLICY:
        return False
    assert job.game_id is not None
    acquire_image_sequence_locks(session, game_id=job.game_id, sequence_numbers={sequence_number})
    rows = session.execute(
        select(ImageReviewItemModel, RecognizedBoardModel)
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .where(
            ImageReviewItemModel.game_id == job.game_id,
            ImageReviewItemModel.sequence_number == sequence_number,
            or_(
                ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
                (ImageReviewItemModel.status == "rejected")
                & (SourceImageModel.checksum_sha256 == source_checksum_sha256),
            ),
        )
        .with_for_update()
    ).all()
    return any(_is_protected(session, review, board) for review, board in rows)


def _is_protected(
    session: Session, review: ImageReviewItemModel, board: RecognizedBoardModel
) -> bool:
    return (
        board.approved_geometry_revision is not None
        or board.geometry_engine_name == "manual_v1"
        or board.geometry_qualification is not None
        or board.completeness_status == "pending_partial"
        or review.resolution_revision > 0
        or _has_human_symbols(session, review.id)
    )


def protected_owner_is_another_photo(
    session: Session,
    *,
    job: JobModel,
    sequence_number: int,
    source_checksum_sha256: str,
) -> bool:
    """D-539 (TASK-0950): the protection comes only from a live owner of another photo.

    Called after ``has_protected_lateral_owner`` returned true, under the same
    sequence lock. True when no protected row has the incoming photo's checksum
    and the owner the shared ownership rule keeps is certain: a canonical row
    exists or every protected row is a live ``pending`` item. The worker then
    records the incoming board as ``superseded`` with a sequence alternative
    (the owner stays untouched) instead of skipping it silently. Protection of
    the same photo (reprocessing) keeps the old skip.
    """

    assert job.game_id is not None
    items = session.scalars(
        select(ImageReviewItemModel)
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .where(
            ImageReviewItemModel.game_id == job.game_id,
            ImageReviewItemModel.sequence_number == sequence_number,
            or_(
                ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
                (ImageReviewItemModel.status == "rejected")
                & (SourceImageModel.checksum_sha256 == source_checksum_sha256),
            ),
        )
    ).all()
    protected: list[tuple[ImageReviewItemModel, str]] = []
    for review in items:
        board = session.get(RecognizedBoardModel, review.recognized_board_id)
        source = None if board is None else session.get(SourceImageModel, board.source_image_id)
        if board is not None and source is not None and _is_protected(session, review, board):
            protected.append((review, source.checksum_sha256))
    if not protected or any(checksum == source_checksum_sha256 for _, checksum in protected):
        return False
    canonical = session.scalar(
        select(ImageSequenceCanonicalModel.review_item_id).where(
            ImageSequenceCanonicalModel.game_id == job.game_id,
            ImageSequenceCanonicalModel.sequence_number == sequence_number,
        )
    )
    return canonical is not None or all(review.status == "pending" for review, _ in protected)


def _has_human_symbols(session: Session, review_id: UUID) -> bool:
    return (
        session.scalar(
            select(ImageSymbolReviewCellModel.id)
            .where(
                ImageSymbolReviewCellModel.review_item_id == review_id,
                or_(
                    ImageSymbolReviewCellModel.assignment_source.in_(("human", "board_decision")),
                    ImageSymbolReviewCellModel.review_state == "approved",
                    ImageSymbolReviewCellModel.quality_issue.is_not(None),
                ),
            )
            .limit(1)
        )
        is not None
    )
