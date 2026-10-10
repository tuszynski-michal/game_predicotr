"""List, preview and revert the rejection of a deferred slot or a board (TASK-0970).

A *rejection* joins the corrections list of the Reviewer (``kind = rejection``):

* ``pending_slot``: ``image_board_geometry_pending`` in status ``rejected``
  (reason, note, actor and time live on the slot); the entry id is the slot id;
* ``review_item``: the latest resolution event of a review item whose action is
  ``rejected`` and whose item is still ``rejected``; the entry id is the event id.

Reverting restores the slot (or the item) to ``pending``. It is refused once a
live review item of another image owns the sequence number (the replacement
that TASK-0971 lets take the rejected owner's place): the unique pending owner
of a sequence would otherwise be violated. Locks follow the writers: sequences,
then the source image, then the slot or the item/board rows.

The slot lifecycle is its own idempotency record (the key is not stored with
the slot); the review item stores the key with the appended ``reopened`` event,
so its retry returns the stored result.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast
from uuid import UUID, uuid4

from sqlalchemy import null, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionEntry,
    GeometryCorrectionRevertPreview,
    GeometryCorrectionRevertResult,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
    GeometryCorrectionKind,
    RejectionRevertFacts,
    RejectionTarget,
    RevertBlockingReason,
    blocking_reason_message,
    decode_board_rejection_reason,
    evaluate_rejection_revert_eligibility,
    snapshot_checksum_sha256,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    canonical_image_review_bytes,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageBoardGeometryPendingEventModel,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_review_repository import (
    acquire_image_review_sequence_locks,
    acquire_image_sequence_locks,
    acquire_sequence_ownership_lock,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    RecognizedBoardModel,
    SourceImageModel,
)

_REJECTION_REVERT_SCHEMA: Final = "geometry-rejection-revert-command-v1"


def _live_elsewhere(*, sequence: str, source_image: str, excluded_item: str | None) -> str:
    """SQL predicate: a live review item of another image owns the sequence number."""

    exclusion = "" if excluded_item is None else f" AND other.id <> {excluded_item}"
    return f"""EXISTS (
  SELECT 1
  FROM image_review_items other
  JOIN recognized_boards other_board
    ON other_board.game_id = other.game_id AND other_board.id = other.recognized_board_id
  WHERE other.game_id = :game_id
    AND other.sequence_number = {sequence}
    AND other.status IN ('pending', 'accepted', 'corrected')
    AND other_board.source_image_id <> {source_image}{exclusion}
)"""


_SLOT_LATEST: Final = """NOT EXISTS (
  SELECT 1 FROM image_board_geometry_pending_events later
  WHERE later.game_id = e.game_id AND later.pending_geometry_id = e.pending_geometry_id
    AND (later.rejection_revision > e.rejection_revision
         OR (later.rejection_revision = e.rejection_revision
             AND later.action = 'rejection_reverted')))"""

# One entry per durable ``rejected`` event of a slot (its id is the entry id), so a
# revert addressed to an older rejection cannot be mistaken for the newest one.
_SLOT_SQL: Final = (
    """
SELECT e.id AS event_id, e.rejection_revision, e.pending_geometry_id, e.import_job_id,
  e.reason, e.note, e.actor, e.created_at,
  p.source_image_id, p.sequence_number, p.position_index, p.status AS slot_status,
  p.expected_geometry_revision, p.expected_review_resolution_revision,
  """
    + _SLOT_LATEST
    + """ AS latest,
  (EXISTS (
     SELECT 1 FROM image_board_geometry_pending q
     WHERE q.game_id = p.game_id AND q.id <> p.id AND q.import_job_id = p.import_job_id
       AND q.source_image_id = p.source_image_id AND q.position_index = p.position_index
       AND q.status = 'pending')
   OR EXISTS (
     SELECT 1 FROM recognized_boards b
     WHERE b.game_id = p.game_id AND b.source_image_id = p.source_image_id
       AND b.position_index = p.position_index)) AS position_taken,
  """
    + _live_elsewhere(
        sequence="p.sequence_number", source_image="p.source_image_id", excluded_item=None
    ).replace(":game_id", "p.game_id")
    + """ AS replaced
FROM image_board_geometry_pending_events e
JOIN image_board_geometry_pending p ON p.game_id = e.game_id AND p.id = e.pending_geometry_id
WHERE e.game_id = :game_id AND e.id = :entry_id AND e.action = 'rejected'
  AND e.import_job_id = :import_job_id
"""
)

_SLOT_LIST_SQL: Final = (
    """
SELECT e.id FROM image_board_geometry_pending_events e
JOIN image_board_geometry_pending p ON p.game_id = e.game_id AND p.id = e.pending_geometry_id
WHERE e.game_id = :game_id AND e.import_job_id = :import_job_id AND e.action = 'rejected'
  AND p.status = 'rejected' AND """
    + _SLOT_LATEST
    + """
ORDER BY e.created_at DESC, e.id DESC
LIMIT :row_limit
"""
)

_BOARD_SQL: Final = """
SELECT e.id AS event_id, e.revision AS event_revision, e.created_at, e.resolved_by,
  e.resolved_value ->> 'reason' AS reason_text,
  ri.id AS review_item_id, ri.import_job_id, ri.status AS item_status,
  ri.resolution_revision, COALESCE(ri.sequence_number, b.sequence_number) AS sequence_number,
  b.id AS board_id, b.source_image_id, b.position_index, b.geometry_revision
FROM image_review_resolution_events e
JOIN image_review_items ri ON ri.game_id = e.game_id AND ri.id = e.review_item_id
JOIN recognized_boards b ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id
WHERE e.game_id = :game_id AND e.id = :entry_id AND e.action = 'rejected'
  AND ri.import_job_id = :import_job_id
"""

_BOARD_LIST_SQL: Final = """
SELECT e.id FROM image_review_resolution_events e
JOIN image_review_items ri ON ri.game_id = e.game_id AND ri.id = e.review_item_id
WHERE e.game_id = :game_id AND ri.import_job_id = :import_job_id AND e.action = 'rejected'
  AND ri.status = 'rejected' AND ri.resolution_revision = e.revision
ORDER BY e.created_at DESC, e.id DESC
LIMIT :row_limit
"""

_BOARD_REPLACED_SQL: Final = "SELECT " + _live_elsewhere(
    sequence=":sequence_number", source_image=":source_image_id", excluded_item=":excluded_item_id"
)

# Every resolution event of the game that carries the key, whatever its item and
# action: the rejection of the same board (``rejected``) is a use of the key too.
_KEY_RESOLUTION_EVENTS_SQL: Final = """
SELECT e.id, e.review_item_id, e.action, e.created_at, e.command_sha256
FROM image_review_resolution_events e
WHERE e.game_id = :game_id AND e.idempotency_key = :idempotency_key
"""


@dataclass(frozen=True, slots=True)
class KeyUses:
    """Where an idempotency key already stands in the revert-related stores.

    The key of a revert is unique within a game across the geometry-correction
    audit, the slot rejection events and the resolution events of review items
    (TASK-0970, P0-7). The audit table is checked by the caller.
    """

    pending_event: ImageBoardGeometryPendingEventModel | None
    resolution_events: tuple[Any, ...]

    @property
    def any(self) -> bool:
        return self.pending_event is not None or bool(self.resolution_events)


def _key_conflict() -> ImageReviewConflictError:
    return ImageReviewConflictError(
        GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
        "Ten klucz idempotencji należy już do innego polecenia.",
    )


@dataclass(frozen=True, slots=True)
class _Rejection:
    target: RejectionTarget
    entry_id: UUID
    import_job_id: UUID
    source_image_id: UUID
    sequence_number: int | None
    position_index: int
    created_at: datetime
    actor: str
    geometry_revision: int
    resolution_revision: int
    reason: str | None
    note: str | None
    still_rejected: bool
    position_free: bool
    # Slot: ``replaced`` is read in the same statement. Board: filled by ``_replaced``.
    replaced: bool
    pending_id: UUID | None = None
    review_item_id: UUID | None = None
    recognized_board_id: UUID | None = None
    event_revision: int | None = None


def _blocked(reason: RevertBlockingReason) -> ImageReviewConflictError:
    return ImageReviewConflictError(reason.value, blocking_reason_message(reason))


class GeometryRejectionRevertOperations:
    """The rejection side of the corrections list, preview and revert."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # -- reads -------------------------------------------------------------

    def list_recent(
        self, *, game_id: UUID, import_job_id: UUID, limit: int
    ) -> tuple[GeometryCorrectionEntry, ...]:
        """Newest rejections of the import (slots and boards), at most ``limit``."""

        parameters = {"game_id": game_id, "import_job_id": import_job_id, "row_limit": limit}
        entries: list[GeometryCorrectionEntry] = []
        for row in self._read(_SLOT_LIST_SQL, parameters):
            rejection = self._slot(game_id, import_job_id, row[0])
            if rejection is not None:
                entries.append(self._entry(rejection, self._reason(rejection, cas=None)))
        for row in self._read(_BOARD_LIST_SQL, parameters):
            rejection = self._board(game_id, import_job_id, row[0])
            if rejection is not None and rejection.sequence_number is not None:
                entries.append(self._entry(rejection, self._reason(rejection, cas=None)))
        entries.sort(key=lambda entry: (entry.created_at, entry.board_geometry_revision_id))
        entries.reverse()
        return tuple(entries[:limit])

    def key_uses(self, game_id: UUID, idempotency_key: UUID) -> KeyUses:
        """The slot events and the resolution events that already carry the key."""

        return KeyUses(
            pending_event=self._event_by_key(game_id, idempotency_key),
            resolution_events=tuple(
                self._read(
                    _KEY_RESOLUTION_EVENTS_SQL,
                    {"game_id": game_id, "idempotency_key": idempotency_key},
                )
            ),
        )

    def find(self, *, game_id: UUID, import_job_id: UUID, entry_id: UUID) -> _Rejection | None:
        """The rejection with this id in the import, whatever its current state."""

        return self._slot(game_id, import_job_id, entry_id) or self._board(
            game_id, import_job_id, entry_id
        )

    def preview(self, rejection: _Rejection) -> GeometryCorrectionRevertPreview:
        reason = self._reason(rejection, cas=None)
        if reason is RevertBlockingReason.NOT_LATEST:
            # The rejection was reverted (e.g. in another tab) or the slot moved
            # on: the list is stale, a preview of it is a controlled refusal.
            raise _blocked(reason)
        return GeometryCorrectionRevertPreview(
            correction=self._entry(rejection, reason),
            removes_board=False,
            removed_cell_count=0,
            repointed_board_count=0,
            restored_cell_decision_count=0,
            reverted_source_geometry_revision_id=None,
            restored_source_geometry_revision_id=None,
            restored_source_engine_kind=None,
            restored_source_status=None,
        )

    # -- revert ------------------------------------------------------------

    def revert(
        self,
        *,
        game_id: UUID,
        rejection: _Rejection,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        actor: str,
        reverted_at: datetime,
        uses: KeyUses,
    ) -> GeometryCorrectionRevertResult:
        if rejection.target is RejectionTarget.PENDING_SLOT:
            return self._revert_slot(
                game_id=game_id,
                rejection=rejection,
                idempotency_key=idempotency_key,
                uses=uses,
                expected=(expected_geometry_revision, expected_resolution_revision),
                actor=actor,
                reverted_at=reverted_at,
            )
        return self._revert_item(
            game_id=game_id,
            rejection=rejection,
            idempotency_key=idempotency_key,
            uses=uses,
            expected=(expected_geometry_revision, expected_resolution_revision),
            actor=actor,
            reverted_at=reverted_at,
        )

    def _revert_slot(
        self,
        *,
        game_id: UUID,
        rejection: _Rejection,
        idempotency_key: UUID,
        uses: KeyUses,
        expected: tuple[int, int],
        actor: str,
        reverted_at: datetime,
    ) -> GeometryCorrectionRevertResult:
        session = self._session
        pending_id = rejection.pending_id
        assert pending_id is not None and rejection.event_revision is not None
        command = {
            "action": "rejection_reverted",
            "rejectionEventId": str(rejection.entry_id),
            "rejectionRevision": rejection.event_revision,
        }
        command_sha256 = hashlib.sha256(canonical_image_review_bytes(command)).hexdigest()
        if uses.resolution_events:
            # The key belongs to a resolution command of a review item.
            raise _key_conflict()
        if uses.pending_event is not None:
            return self._replayed_slot_revert(
                game_id, rejection, uses.pending_event, command_sha256=command_sha256
            )
        # Lock order of the rejection and the manual resolution:
        # ownership -> sequence -> source -> slot.
        acquire_sequence_ownership_lock(session, game_id=game_id)
        if rejection.sequence_number is not None:
            acquire_image_sequence_locks(
                session, game_id=game_id, sequence_numbers={rejection.sequence_number}
            )
        session.execute(
            select(SourceImageModel.id)
            .where(SourceImageModel.id == rejection.source_image_id)
            .with_for_update()
        )
        pending = session.scalar(
            select(ImageBoardGeometryPendingModel)
            .where(ImageBoardGeometryPendingModel.id == pending_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        # Another request with the same key may have committed while this one
        # waited for the locks.
        prior = self._event_by_key(game_id, idempotency_key)
        if prior is not None:
            return self._replayed_slot_revert(
                game_id, rejection, prior, command_sha256=command_sha256
            )
        locked = self._slot(game_id, rejection.import_job_id, rejection.entry_id)
        if pending is None or locked is None:
            raise _blocked(RevertBlockingReason.NOT_LATEST)
        reason = self._reason(locked, cas=expected)
        if reason is not None:
            raise _blocked(reason)
        event = ImageBoardGeometryPendingEventModel(
            id=uuid4(),
            game_id=game_id,
            import_job_id=rejection.import_job_id,
            pending_geometry_id=pending_id,
            rejection_revision=rejection.event_revision,
            action="rejection_reverted",
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
            actor=actor,
            created_at=reverted_at,
        )
        session.add(event)
        pending.status = "pending"
        pending.rejection_reason = None
        pending.rejection_note = None
        pending.rejected_at = None
        pending.rejected_by = None
        pending.updated_at = reverted_at
        session.flush()
        recompute = recompute_source_image_geometry_completeness(
            session, game_id, rejection.source_image_id, actor=actor, now=reverted_at
        )
        # The slot is open work again.
        source = session.get(SourceImageModel, rejection.source_image_id, populate_existing=True)
        if source is not None and source.status in {"accepted", "rejected"}:
            source.status = "waiting_for_review"
            session.flush()
        return self._result(
            rejection,
            revert_id=event.id,
            created=True,
            created_at=reverted_at,
            status=recompute.status,
            command=command,
        )

    def _replayed_slot_revert(
        self,
        game_id: UUID,
        rejection: _Rejection,
        prior: ImageBoardGeometryPendingEventModel,
        *,
        command_sha256: str,
    ) -> GeometryCorrectionRevertResult:
        """The stored result of a revert request replayed with its key."""

        if (
            prior.action != "rejection_reverted"
            or prior.pending_geometry_id != rejection.pending_id
            or prior.command_sha256 != command_sha256
        ):
            raise ImageReviewConflictError(
                GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
                "Ten klucz idempotencji należy już do innego polecenia.",
            )
        source = self._session.get(SourceImageModel, rejection.source_image_id)
        return self._result(
            rejection,
            revert_id=prior.id,
            created=False,
            created_at=prior.created_at,
            status=None if source is None else _status(source.geometry_completeness_status),
            command={
                "action": "rejection_reverted",
                "rejectionEventId": str(rejection.entry_id),
                "rejectionRevision": prior.rejection_revision,
            },
        )

    def _event_by_key(
        self, game_id: UUID, idempotency_key: UUID
    ) -> ImageBoardGeometryPendingEventModel | None:
        return self._session.scalar(
            select(ImageBoardGeometryPendingEventModel).where(
                ImageBoardGeometryPendingEventModel.game_id == game_id,
                ImageBoardGeometryPendingEventModel.idempotency_key == idempotency_key,
            )
        )

    def _revert_item(
        self,
        *,
        game_id: UUID,
        rejection: _Rejection,
        idempotency_key: UUID,
        uses: KeyUses,
        expected: tuple[int, int],
        actor: str,
        reverted_at: datetime,
    ) -> GeometryCorrectionRevertResult:
        session = self._session
        item_id = rejection.review_item_id
        board_id = rejection.recognized_board_id
        assert item_id is not None and board_id is not None
        # The command this request stands for: one rejection event of this item.
        command = {
            "action": "reopened",
            "rejectionEventId": str(rejection.entry_id),
            "reason": "rejection_reverted",
            "schemaVersion": _REJECTION_REVERT_SCHEMA,
        }
        command_sha256 = hashlib.sha256(canonical_image_review_bytes(command)).hexdigest()
        # The key must be free, or already stand for exactly this command; any other
        # use (another item, another action such as the board's own ``rejected``
        # event, a slot event) conflicts before anything is written.
        replay = None
        if uses.pending_event is not None:
            raise _key_conflict()
        if uses.resolution_events:
            matching = [
                event
                for event in uses.resolution_events
                if event.review_item_id == item_id
                and event.action == "reopened"
                and event.command_sha256 == command_sha256
            ]
            if len(uses.resolution_events) != 1 or not matching:
                raise _key_conflict()
            replay = matching[0]
        acquire_image_review_sequence_locks(
            session, game_id=game_id, review_item_id=item_id, requested_sequence_number=None
        )
        source = session.get(
            SourceImageModel,
            rejection.source_image_id,
            with_for_update=True,
            populate_existing=True,
        )
        item = session.get(
            ImageReviewItemModel, item_id, with_for_update=True, populate_existing=True
        )
        board = session.get(
            RecognizedBoardModel, board_id, with_for_update=True, populate_existing=True
        )
        if source is None or item is None or board is None:
            raise _blocked(RevertBlockingReason.NOT_LATEST)
        if replay is not None:
            return self._result(
                rejection,
                revert_id=replay.id,
                created=False,
                created_at=replay.created_at,
                status=_status(source.geometry_completeness_status),
                command={"entryId": str(rejection.entry_id), "target": rejection.target.value},
            )
        locked = self._board(game_id, rejection.import_job_id, rejection.entry_id)
        if locked is None:
            raise _blocked(RevertBlockingReason.NOT_LATEST)
        reason = self._reason(locked, cas=expected)
        if reason is not None:
            raise _blocked(reason)
        revision = item.resolution_revision + 1
        event = ImageReviewResolutionEventModel(
            review_item_id=item.id,
            revision=revision,
            idempotency_key=idempotency_key,
            action="reopened",
            command_sha256=command_sha256,
            resolved_value={
                "action": "reopened",
                "geometryRevision": board.geometry_revision,
                "previousStatus": "rejected",
                "reason": "rejection_reverted",
                "rejectionEventId": str(rejection.entry_id),
                "sequenceNumber": rejection.sequence_number,
            },
            resolved_by=actor,
            created_at=reverted_at,
        )
        session.add(event)
        item.status = "pending"
        item.resolved_value = cast(Any, null())
        item.resolved_by = None
        item.resolved_at = None
        item.resolution_revision = revision
        board.status = "pending_review"
        source.status = "waiting_for_review"
        source.processed_at = reverted_at
        session.flush()
        recompute = recompute_source_image_geometry_completeness(
            session, game_id, rejection.source_image_id, actor=actor, now=reverted_at
        )
        projection = SqlAlchemyBoardSearchProjectionRepository(session)
        projection.sync_review_item(item.id)
        if rejection.sequence_number is not None:
            projection.sync_sequence_candidates(game_id, rejection.sequence_number)
        coordinator = SymbolCellReviewWriteThroughCoordinator(session)
        # The cells left the exact counters with the rejection (TASK-0970).
        coordinator.restore_cells_of_reopened_board(game_id=game_id, review_item_id=item.id)
        coordinator.synchronize_after_board_resolution(
            game_id=game_id, review_item_id=item.id, actor=actor
        )
        coordinator.synchronize_after_projection_change(game_id=game_id)
        return self._result(
            rejection,
            revert_id=event.id,
            created=True,
            created_at=reverted_at,
            status=recompute.status,
            command={"entryId": str(rejection.entry_id), "target": rejection.target.value},
        )

    # -- facts -------------------------------------------------------------

    def _slot(self, game_id: UUID, import_job_id: UUID, entry_id: UUID) -> _Rejection | None:
        row = self._read(
            _SLOT_SQL,
            {"game_id": game_id, "entry_id": entry_id, "import_job_id": import_job_id},
        ).first()
        if row is None:
            return None
        return _Rejection(
            target=RejectionTarget.PENDING_SLOT,
            entry_id=row.event_id,
            import_job_id=row.import_job_id,
            source_image_id=row.source_image_id,
            sequence_number=int(row.sequence_number),
            position_index=int(row.position_index),
            # Built from the durable event, so a rejection that was reverted since
            # still has its time and actor (never a null ``created_at``).
            created_at=row.created_at,
            actor=str(row.actor),
            geometry_revision=int(row.expected_geometry_revision),
            resolution_revision=int(row.expected_review_resolution_revision),
            reason=row.reason,
            note=row.note,
            still_rejected=row.slot_status == "rejected" and bool(row.latest),
            position_free=not bool(row.position_taken),
            replaced=bool(row.replaced),
            pending_id=row.pending_geometry_id,
            event_revision=int(row.rejection_revision),
        )

    def _board(self, game_id: UUID, import_job_id: UUID, entry_id: UUID) -> _Rejection | None:
        row = self._read(
            _BOARD_SQL,
            {"game_id": game_id, "entry_id": entry_id, "import_job_id": import_job_id},
        ).first()
        if row is None:
            return None
        reason, note = decode_board_rejection_reason(row.reason_text)
        sequence = None if row.sequence_number is None else int(row.sequence_number)
        replaced = sequence is not None and bool(
            self._scalar(
                _BOARD_REPLACED_SQL,
                {
                    "game_id": game_id,
                    "sequence_number": sequence,
                    "source_image_id": row.source_image_id,
                    "excluded_item_id": row.review_item_id,
                },
            )
        )
        return _Rejection(
            target=RejectionTarget.REVIEW_ITEM,
            entry_id=row.event_id,
            import_job_id=row.import_job_id,
            source_image_id=row.source_image_id,
            sequence_number=sequence,
            position_index=int(row.position_index),
            created_at=row.created_at,
            actor=str(row.resolved_by),
            geometry_revision=int(row.geometry_revision),
            resolution_revision=int(row.resolution_revision),
            reason=reason,
            note=note,
            still_rejected=row.item_status == "rejected"
            and int(row.resolution_revision) == int(row.event_revision),
            position_free=True,
            replaced=replaced,
            review_item_id=row.review_item_id,
            recognized_board_id=row.board_id,
            event_revision=int(row.event_revision),
        )

    @staticmethod
    def _reason(
        rejection: _Rejection, *, cas: tuple[int, int] | None
    ) -> RevertBlockingReason | None:
        return evaluate_rejection_revert_eligibility(
            RejectionRevertFacts(
                still_rejected=rejection.still_rejected,
                cas_matches=(
                    None
                    if cas is None
                    else cas == (rejection.geometry_revision, rejection.resolution_revision)
                ),
                position_free=rejection.position_free,
                replaced=rejection.replaced,
            )
        )

    @staticmethod
    def _entry(
        rejection: _Rejection, reason: RevertBlockingReason | None
    ) -> GeometryCorrectionEntry:
        return GeometryCorrectionEntry(
            board_geometry_revision_id=rejection.entry_id,
            kind=GeometryCorrectionKind.REJECTION,
            recognized_board_id=rejection.recognized_board_id,
            review_item_id=rejection.review_item_id,
            pending_geometry_id=rejection.pending_id,
            source_image_id=rejection.source_image_id,
            sequence_number=rejection.sequence_number or 1,
            position_index=rejection.position_index,
            created_at=rejection.created_at,
            actor=rejection.actor,
            geometry_revision=rejection.geometry_revision,
            resolution_revision=rejection.resolution_revision,
            blocking_reason=reason,
            rejection_target=rejection.target,
            rejection_reason=rejection.reason,
            rejection_note=rejection.note,
        )

    @staticmethod
    def _result(
        rejection: _Rejection,
        *,
        revert_id: UUID,
        created: bool,
        created_at: datetime,
        status: SourceImageGeometryStatus | None,
        command: Mapping[str, object],
    ) -> GeometryCorrectionRevertResult:
        return GeometryCorrectionRevertResult(
            revert_id=revert_id,
            created=created,
            kind=GeometryCorrectionKind.REJECTION,
            board_geometry_revision_id=rejection.entry_id,
            pending_geometry_id=rejection.pending_id,
            recognized_board_id=rejection.recognized_board_id,
            review_item_id=rejection.review_item_id,
            reverted_source_geometry_revision_id=None,
            restored_source_geometry_revision_id=None,
            repointed_board_ids=(),
            removed_cell_count=0,
            source_image_geometry_status=status,
            snapshot_checksum_sha256=snapshot_checksum_sha256(
                {"kind": "rejection", **command, "revertId": str(revert_id)}
            ),
            created_at=created_at,
        )

    def _read(self, sql: str, parameters: Mapping[str, object]) -> Any:
        # Connection-level execution keeps the read route of a read-only
        # transaction (see ``image_geometry_completeness_state_repository``).
        return self._session.connection().execute(text(sql), dict(parameters))

    def _scalar(self, sql: str, parameters: Mapping[str, object]) -> Any:
        return self._read(sql, parameters).scalar()


def _status(value: str | None) -> SourceImageGeometryStatus | None:
    return None if value is None else SourceImageGeometryStatus(value)


__all__ = ["GeometryRejectionRevertOperations"]
