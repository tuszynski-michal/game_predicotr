"""Create one auditable pending owner for a game sequence (D-238, D-543)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_reviews import canonical_image_review_bytes
from game_predictor_api.domain.sequence_takeover import (
    ImportOrder,
    PendingOwnerFacts,
    SequenceClaim,
    decide_sequence_claim,
)
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageBoardGeometryPendingEventModel,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    lock_source_images,
    recompute_source_images,
)
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceAlternativeModel,
    ImageSequenceCanonicalModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)

_ACTOR: Final = "system:pending-sequence-owner"
_SLOT_SUPERSEDED_ACTION: Final = "superseded"

# Images whose geometry gate may change when the sequence gets a live owner on
# another image (D-543 cleanup, TASK-0971): an image with a rejected review
# item or a rejected deferred slot of the sequence, and every not-admitted
# image whose source revision range covers the sequence (a gap there becomes
# a ``superseded`` position). Recomputing an unchanged image is a no-op.
_TAKEOVER_GATE_CANDIDATES_SQL: Final = """
SELECT b.source_image_id
FROM image_review_items ri
JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
WHERE ri.game_id = :game_id AND ri.sequence_number = :sequence_number
  AND ri.status = 'rejected' AND b.source_image_id <> :source_image_id
UNION
SELECT slot.source_image_id
FROM image_board_geometry_pending slot
WHERE slot.game_id = :game_id AND slot.sequence_number = :sequence_number
  AND slot.status = 'rejected' AND slot.source_image_id <> :source_image_id
UNION
SELECT s.id
FROM source_images s
WHERE s.game_id = :game_id AND s.id <> :source_image_id
  AND s.geometry_completeness_status = 'geometry_incomplete'
  AND EXISTS (
    SELECT 1 FROM image_source_geometry_revisions r
    WHERE r.game_id = :game_id AND r.source_image_id = s.id AND r.status <> 'reverted'
      AND r.sequence_range_start <= :sequence_number
      AND r.sequence_range_end >= :sequence_number)
"""


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
    """Create a review item under the race-safe sequence ownership rule (D-543).

    Resolved canonical boards always win. A live ``pending`` item of another
    photo keeps the sequence: the incoming item is ``superseded`` and its
    source is recorded as a sequence alternative. Among imports of the same
    photo (same source checksum) the newest ``(created_at, id)`` still owns the
    sequence (D-238). A sequence without a live owner (none, or only rejected
    owners) is taken over; the rejected deferred slots of other images for the
    sequence are then closed as ``superseded`` and the gate of every image the
    new owner may complete is recomputed in this transaction (an image that
    becomes admitted is cut through the existing write-through). A second
    item is always retained as ``superseded`` audit history, never as another
    active pending.
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
    # Images whose gate the incoming item may change if it takes the sequence
    # over; read with the other facts, applied only after a takeover.
    gate_candidates = {
        row[0]
        for row in session.execute(
            text(_TAKEOVER_GATE_CANDIDATES_SQL),
            {
                "game_id": game_id,
                "sequence_number": sequence_number,
                "source_image_id": board.source_image_id,
            },
        ).all()
    }
    # The candidate source rows are locked now, in ascending id order and before
    # any slot, item or counters row: the global lock order of
    # ``storage.sequence_ownership_lock`` (TASK-0971, audit round 4).
    if gate_candidates:
        lock_source_images(session, game_id, gate_candidates)
    # Rejected deferred slots of other images for this sequence (rows, locked
    # after their source rows).
    rejected_slots = [
        row[0]
        for row in session.execute(
            select(ImageBoardGeometryPendingModel)
            .where(
                ImageBoardGeometryPendingModel.game_id == game_id,
                ImageBoardGeometryPendingModel.sequence_number == sequence_number,
                ImageBoardGeometryPendingModel.status == "rejected",
                ImageBoardGeometryPendingModel.source_image_id != board.source_image_id,
            )
            .order_by(ImageBoardGeometryPendingModel.id)
            .with_for_update()
        ).all()
    ]
    incumbents = session.execute(
        select(
            ImageReviewItemModel,
            RecognizedBoardModel,
            JobModel,
            SourceImageModel.checksum_sha256,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
        )
        .join(JobModel, JobModel.id == ImageReviewItemModel.import_job_id)
        .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
        .where(
            ImageReviewItemModel.game_id == game_id,
            ImageReviewItemModel.sequence_number == sequence_number,
            ImageReviewItemModel.status == "pending",
        )
        # Job identity and created_at are immutable after creation. Locking the
        # incumbent JobModel here creates a Job -> sequence -> source versus
        # sequence -> source -> Job cycle with a concurrently resumed worker.
        # Only the review item and its board are mutated by ownership changes.
        .with_for_update(of=(ImageReviewItemModel, RecognizedBoardModel))
    ).all()
    incumbent = max(
        incumbents,
        key=lambda value: (value[2].created_at, str(value[2].id)),
        default=None,
    )
    claim = decide_sequence_claim(
        canonical_exists=canonical is not None,
        incumbent=(
            None
            if incumbent is None
            else PendingOwnerFacts(
                source_checksum_sha256=str(incumbent[3]),
                import_order=ImportOrder(incumbent[2].created_at, str(incumbent[2].id)),
            )
        ),
        incoming_source_checksum_sha256=(
            None if incumbent is None else _source_checksum(session, board)
        ),
        incoming_order=ImportOrder(import_job.created_at, str(import_job.id)),
    )

    changed_ids: list[UUID] = []
    owner_review_item_id: UUID | None = None
    if canonical is not None:
        owner_review_item_id = canonical.review_item_id
    elif incumbent is not None and not claim.incoming_owns:
        owner_review_item_id = incumbent[0].id
    if claim.incumbent_reason is not None:
        for old_item, old_board, _old_job, _old_checksum in incumbents:
            _supersede(
                session,
                item=old_item,
                board=old_board,
                sequence_number=sequence_number,
                successor_review_item_id=item_id,
                reason=claim.incumbent_reason,
                resolved_at=created_at,
            )
            changed_ids.append(old_item.id)

    incoming_reason = claim.incoming_reason
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
    if claim.alternative_reason is not None:
        _add_sequence_alternative(
            session,
            board=board,
            game_id=game_id,
            import_job_id=import_job.id,
            sequence_number=sequence_number,
            reason=claim.alternative_reason,
        )
    changed_ids.append(item.id)
    if claim.incoming_owns:
        _clean_up_after_takeover(
            session,
            claim=claim,
            game_id=game_id,
            board=board,
            successor=item,
            rejected_slots=rejected_slots,
            gate_candidates=gate_candidates,
            changed_at=created_at,
        )
    return item, tuple(changed_ids)


def _source_checksum(session: Session, board: RecognizedBoardModel) -> str | None:
    value = session.scalar(
        select(SourceImageModel.checksum_sha256).where(SourceImageModel.id == board.source_image_id)
    )
    return None if value is None else str(value)


def _add_sequence_alternative(
    session: Session,
    *,
    board: RecognizedBoardModel,
    game_id: UUID,
    import_job_id: UUID,
    sequence_number: int,
    reason: str,
) -> None:
    """Record the skipped source of a superseded incoming board (idempotent)."""

    source = session.get(SourceImageModel, board.source_image_id)
    if source is None:
        return
    exists = session.scalar(
        select(ImageSequenceAlternativeModel.id).where(
            ImageSequenceAlternativeModel.game_id == game_id,
            ImageSequenceAlternativeModel.sequence_number == sequence_number,
            ImageSequenceAlternativeModel.import_job_id == import_job_id,
            ImageSequenceAlternativeModel.source_checksum_sha256 == source.checksum_sha256,
        )
    )
    if exists is not None:
        return
    session.add(
        ImageSequenceAlternativeModel(
            game_id=game_id,
            sequence_number=sequence_number,
            import_job_id=import_job_id,
            source_checksum_sha256=source.checksum_sha256,
            source_relative_path=source.relative_path,
            reason=reason,
        )
    )
    session.flush()


def _clean_up_after_takeover(
    session: Session,
    *,
    claim: SequenceClaim,
    game_id: UUID,
    board: RecognizedBoardModel,
    successor: ImageReviewItemModel,
    rejected_slots: list[ImageBoardGeometryPendingModel],
    gate_candidates: set[UUID],
    changed_at: datetime,
) -> None:
    """Close the rejected owners' slots and recompute the gates (D-543 decision 6).

    A rejected review item stays ``rejected``: its cells left the exact counters
    when it was rejected and the successor's write-through does not subtract
    them again (TASK-0970), so nothing is counted twice. Nothing is deleted.
    """

    assert claim.incoming_owns
    sequence_number = board.sequence_number
    assert sequence_number is not None
    for slot in rejected_slots:
        revision = session.scalar(
            select(func.max(ImageBoardGeometryPendingEventModel.rejection_revision)).where(
                ImageBoardGeometryPendingEventModel.game_id == game_id,
                ImageBoardGeometryPendingEventModel.pending_geometry_id == slot.id,
                ImageBoardGeometryPendingEventModel.action == "rejected",
            )
        )
        rejection_revision = int(revision or 1)
        command = canonical_image_review_bytes(
            {
                "action": _SLOT_SUPERSEDED_ACTION,
                "pendingGeometryId": str(slot.id),
                "rejectionRevision": rejection_revision,
                "sequenceNumber": sequence_number,
                "successorReviewItemId": str(successor.id),
            }
        )
        session.add(
            ImageBoardGeometryPendingEventModel(
                id=uuid4(),
                game_id=game_id,
                import_job_id=slot.import_job_id,
                pending_geometry_id=slot.id,
                rejection_revision=rejection_revision,
                action=_SLOT_SUPERSEDED_ACTION,
                idempotency_key=uuid5(
                    NAMESPACE_URL,
                    f"pending-slot-superseded:{slot.id}:{rejection_revision}:{successor.id}",
                ),
                command_sha256=hashlib.sha256(command).hexdigest(),
                reason=None,
                note=None,
                actor=_ACTOR,
                successor_review_item_id=successor.id,
                created_at=changed_at,
            )
        )
        # The lifecycle CHECK keeps the rejection fields as history.
        slot.status = "superseded"
        slot.superseded_at = changed_at
        slot.updated_at = changed_at
    session.flush()
    # All candidate source rows are locked in ascending id order before any
    # of them is recomputed or cut (global lock order, TASK-0971 P0-7).
    recompute_source_images(
        session,
        game_id,
        {slot.source_image_id for slot in rejected_slots} | gate_candidates,
        actor=_ACTOR,
        now=changed_at,
        exclude_source_image_id=board.source_image_id,
    )


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
