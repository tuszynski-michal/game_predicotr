"""Opt-in per-sequence protection of human work during v4 reprocessing."""

from collections.abc import Iterable, Mapping
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .image_review_repository import acquire_image_sequence_locks
from .models import (
    ImageReviewItemModel,
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
    if isinstance(rollout, Mapping) and rollout.get("lateralPartialGeometry") is not None:
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
    if not isinstance(rollout, Mapping) or rollout.get("lateralPartialGeometry") is None:
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
    for review, board in rows:
        if (
            board.approved_geometry_revision is not None
            or board.geometry_engine_name == "manual_v1"
            or board.geometry_qualification is not None
            or board.completeness_status == "pending_partial"
            or review.resolution_revision > 0
            or _has_human_symbols(session, review.id)
        ):
            return True
    return False


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
