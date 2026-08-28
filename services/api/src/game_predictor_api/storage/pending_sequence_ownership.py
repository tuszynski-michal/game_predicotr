"""Create one auditable pending owner for a game sequence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_reviews import canonical_image_review_bytes
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.models import (
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceCanonicalModel,
    JobModel,
    RecognizedBoardModel,
)

_ACTOR = "system:pending-sequence-owner"


def create_owned_pending_review_item(
    session: Session,
    *,
    board: RecognizedBoardModel,
    game_id: UUID,
    import_job: JobModel,
    snapshot: Mapping[str, object],
    created_at: datetime,
    resolution_revision: int = 0,
) -> tuple[ImageReviewItemModel, tuple[UUID, ...]]:
    """Create a review item while newest-import-wins remains race safe.

    Resolved canonical boards always win. Among unresolved imports, the job
    with the newest ``(created_at, id)`` owns the sequence. A second item is
    retained as ``superseded`` audit history, never as another active pending.
    """

    sequence_number = board.sequence_number
    if sequence_number is None:
        item = ImageReviewItemModel(
            game_id=game_id,
            import_job_id=import_job.id,
            sequence_number=None,
            recognized_board_id=board.id,
            status="pending",
            snapshot=dict(snapshot),
            resolution_revision=resolution_revision,
            created_at=created_at,
        )
        session.add(item)
        session.flush()
        return item, (item.id,)

    acquire_image_sequence_locks(
        session,
        game_id=game_id,
        sequence_numbers={sequence_number},
    )
    item_id = uuid4()
    canonical = session.scalar(
        select(ImageSequenceCanonicalModel).where(
            ImageSequenceCanonicalModel.game_id == game_id,
            ImageSequenceCanonicalModel.sequence_number == sequence_number,
        )
    )
    incumbents = session.execute(
        select(ImageReviewItemModel, RecognizedBoardModel, JobModel)
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(JobModel, JobModel.id == ImageReviewItemModel.import_job_id)
        .where(
            ImageReviewItemModel.game_id == game_id,
            ImageReviewItemModel.sequence_number == sequence_number,
            ImageReviewItemModel.status == "pending",
        )
        .with_for_update()
    ).all()
    incoming_order = (import_job.created_at, str(import_job.id))
    incumbent = max(
        incumbents,
        key=lambda value: (value[2].created_at, str(value[2].id)),
        default=None,
    )

    changed_ids: list[UUID] = []
    incoming_reason: str | None = None
    owner_review_item_id: UUID | None = None
    if canonical is not None:
        incoming_reason = "canonical_sequence_already_resolved"
        owner_review_item_id = canonical.review_item_id
    elif incumbent is not None:
        incumbent_order = (incumbent[2].created_at, str(incumbent[2].id))
        if incoming_order <= incumbent_order:
            incoming_reason = "pending_sequence_owned_by_newer_import"
            owner_review_item_id = incumbent[0].id
        else:
            for old_item, old_board, _old_job in incumbents:
                _supersede(
                    session,
                    item=old_item,
                    board=old_board,
                    sequence_number=sequence_number,
                    successor_review_item_id=item_id,
                    reason="pending_sequence_replaced_by_newer_import",
                    resolved_at=created_at,
                )
                changed_ids.append(old_item.id)

    item = ImageReviewItemModel(
        id=item_id,
        game_id=game_id,
        import_job_id=import_job.id,
        sequence_number=sequence_number,
        recognized_board_id=board.id,
        status="pending" if incoming_reason is None else "superseded",
        snapshot=dict(snapshot),
        resolved_by=None,
        resolution_revision=resolution_revision,
        resolved_at=None,
        created_at=created_at,
    )
    if incoming_reason is not None:
        resolved_value = {
            "action": "superseded",
            "ownerReviewItemId": str(owner_review_item_id),
            "reason": incoming_reason,
            "sequenceNumber": sequence_number,
        }
        item.resolved_value = resolved_value
        item.resolved_by = _ACTOR
        item.resolution_revision = max(1, resolution_revision + 1)
        item.resolved_at = created_at
        board.status = "rejected"
    session.add(item)
    session.flush()
    if incoming_reason is not None:
        _add_superseded_event(session, item=item, resolved_at=created_at)
    changed_ids.append(item.id)
    return item, tuple(changed_ids)


def _supersede(
    session: Session,
    *,
    item: ImageReviewItemModel,
    board: RecognizedBoardModel,
    sequence_number: int,
    successor_review_item_id: UUID,
    reason: str,
    resolved_at: datetime,
) -> None:
    item.status = "superseded"
    item.resolved_value = {
        "action": "superseded",
        "ownerReviewItemId": str(successor_review_item_id),
        "reason": reason,
        "sequenceNumber": sequence_number,
    }
    item.resolved_by = _ACTOR
    item.resolution_revision += 1
    item.resolved_at = resolved_at
    board.status = "rejected"
    session.execute(
        delete(ImageLayoutStagingRowModel).where(
            ImageLayoutStagingRowModel.review_item_id == item.id
        )
    )
    _add_superseded_event(session, item=item, resolved_at=resolved_at)


def _add_superseded_event(
    session: Session,
    *,
    item: ImageReviewItemModel,
    resolved_at: datetime,
) -> None:
    assert item.resolved_value is not None
    command = canonical_image_review_bytes(
        {
            "action": "superseded",
            "resolvedBy": _ACTOR,
            "resolvedValue": item.resolved_value,
        }
    )
    session.add(
        ImageReviewResolutionEventModel(
            review_item_id=item.id,
            revision=item.resolution_revision,
            idempotency_key=uuid5(
                NAMESPACE_URL,
                f"pending-sequence-owner:{item.id}:{item.resolution_revision}",
            ),
            action="superseded",
            command_sha256=hashlib.sha256(command).hexdigest(),
            resolved_value=dict(item.resolved_value),
            resolved_by=_ACTOR,
            created_at=resolved_at,
        )
    )


__all__ = ["create_owned_pending_review_item"]
