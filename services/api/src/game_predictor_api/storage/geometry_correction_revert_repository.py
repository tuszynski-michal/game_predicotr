"""PostgreSQL persistence of the geometry correction revert (TASK-0945, plan D-538).

A correction is one ``geometry_saved`` event with its board geometry revision.
Case B (``pending_slot``): the save resolved a deferred slot. Its revert, in
the caller's single transaction and with the save's lock order (sequence
advisory lock -> source image -> deferred slot -> board and review item):

1. reads every fact again under lock and refuses with the first blocking rule
   (``domain.geometry_correction_reverts``) before any write;
2. snapshots every row it deletes (to ``jsonb``: UUIDs and timestamps as ISO
   text) in deletion order, plus the slot and source revision rows it updates;
3. removes the cells from the exact counters (and from ``cell_count`` when the
   save was qualified, mirroring ``_availability_snapshot``);
4. deletes in FK order: cell events -> cells -> board geometry events -> board
   geometry revision -> (slot detached) -> review item (its trigger and
   cascades remove the queue entry, search candidate and fast document) ->
   board (cascade: render manifest); every statement must hit exactly the
   snapshotted rows, otherwise the transaction fails;
5. reopens the slot, marks the correction's source revision ``reverted`` and
   re-points the neighbours the save had moved back to the previous revision
   (``apply_board_repoint`` with self-built decisions, then search sync);
6. reconciles the sequence's search document, recomputes the image gate
   (refusing when an admitted image would change status), sets the image
   ``waiting_for_review`` while it has open work, advances the catalog
   revision and the super game input version, and appends the audit row.

Case A (``board_revision``) is listed with its eligibility, but its revert
belongs to TASK-0946 and is refused with ``GEOMETRY_REVERT_NOT_SUPPORTED``.

"Transaction of the correction" is identified structurally: ``T`` is the
``created_at`` (server ``now()``) of the render manifest the save wrote for
its board geometry revision; cells, cell events and the source revision the
same save wrote carry the same ``now()``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionEntry,
    GeometryCorrectionRevertPreview,
    GeometryCorrectionRevertResult,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    GEOMETRY_CORRECTION_NOT_FOUND,
    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
    REVERTED_SOURCE_GEOMETRY_STATUS,
    SNAPSHOT_SCHEMA_VERSION,
    GeometryCorrectionKind,
    RevertBlockingReason,
    RevertEligibilityFacts,
    blocking_reason_message,
    evaluate_revert_eligibility,
    image_admission_blocks_revert,
    predicted_status_after_slot_revert,
    snapshot_checksum_sha256,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.geometry_correction_revert_models import (
    ImageGeometryCorrectionRevertModel,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    BoardRepointDecision,
    apply_board_repoint,
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    _apply_count_deltas,
    _CountedCellState,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewStateModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.super_game_input_version import record_super_game_input_change
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    selected_available_cell_count,
)

_RESOLVED_REVIEW_STATUSES: Final = frozenset({"accepted", "corrected", "rejected", "superseded"})

# Newest geometry saves of one import (the event is the unit of correction).
_LIST_SQL = """
SELECT r.id AS revision_id
FROM image_board_geometry_review_events e
JOIN image_review_items ri
  ON ri.game_id = e.game_id AND ri.id = e.review_item_id AND ri.import_job_id = :import_job_id
JOIN image_board_geometry_revisions r
  ON r.game_id = e.game_id AND r.recognized_board_id = e.recognized_board_id
  AND r.revision = e.geometry_revision
WHERE e.game_id = :game_id AND e.action = 'geometry_saved'
ORDER BY e.created_at DESC, e.id DESC
LIMIT :row_limit
"""

_CORRECTION_SQL = """
SELECT r.id AS revision_id, r.revision, r.recognized_board_id, r.review_item_id,
  r.source_geometry_revision_id, r.idempotency_key, r.corrected_by, r.created_at,
  b.geometry_revision AS board_geometry_revision, b.source_image_id, b.sequence_number,
  b.position_index, b.geometry_qualification IS NOT NULL AS qualified,
  ri.import_job_id, ri.status AS review_status, ri.resolution_revision,
  p.id AS pending_id,
  (SELECT m.created_at FROM board_render_manifests m
   WHERE m.game_id = r.game_id AND m.recognized_board_id = r.recognized_board_id
     AND m.geometry_revision = r.revision) AS transaction_at
FROM image_board_geometry_revisions r
JOIN recognized_boards b ON b.game_id = r.game_id AND b.id = r.recognized_board_id
JOIN image_review_items ri ON ri.game_id = r.game_id AND ri.id = r.review_item_id
LEFT JOIN image_board_geometry_pending p
  ON p.game_id = r.game_id AND p.recognized_board_id = r.recognized_board_id
  AND p.review_item_id = r.review_item_id AND p.status = 'resolved'
  AND p.resolved_geometry_revision = r.revision
WHERE r.game_id = :game_id AND r.id = :revision_id
"""

_SOURCE_REVISIONS_SQL = """
SELECT id, revision, status, engine_kind, created_by, created_at, geometry_checksum_sha256
FROM image_source_geometry_revisions
WHERE game_id = :game_id AND source_image_id = :source_image_id
ORDER BY revision
"""

# Boards the save re-pointed to its source revision and whether each can move
# back unchanged (the mirror of ``_REPOINT_PLAN_SQL``).
_NEIGHBOURS_SQL = """
SELECT b.id, b.position_index, b.geometry_revision, b.status,
  b.geometry_checksum_sha256 = p.geometry_checksum_sha256 AS checksum_current,
  ri.id AS review_item_id,
  b.position_index = ANY (n.active_board_slots) AS in_slots,
  (p.topology_rules_version_id = n.topology_rules_version_id
   AND p.source_checksum_sha256 = n.source_checksum_sha256
   AND p.normalized_pixel_checksum_sha256 = n.normalized_pixel_checksum_sha256) AS same_source,
  jsonb_path_query_first(p.board_geometries, '$[*] ? (@.positionIndex == $position)',
    jsonb_build_object('position', b.position_index)) AS reverted_entry,
  jsonb_path_query_first(n.board_geometries, '$[*] ? (@.positionIndex == $position)',
    jsonb_build_object('position', b.position_index)) AS restored_entry,
  EXISTS (
    SELECT 1 FROM board_render_manifests m
    WHERE m.game_id = :game_id AND m.recognized_board_id = b.id
      AND m.geometry_revision = b.geometry_revision AND m.source_geometry_revision_id <> p.id
  ) AS manifest_drift,
  ri.id IS NOT NULL AND EXISTS (
    SELECT 1 FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id AND c.review_item_id = ri.id AND c.recognized_board_id = b.id
      AND c.source_geometry_revision_id IS DISTINCT FROM p.id
  ) AS cell_drift,
  EXISTS (
    SELECT 1 FROM verified_training_cohort_cells vc
    WHERE vc.game_id = :game_id AND vc.recognized_board_id = b.id
  ) AS cohort_pinned
FROM recognized_boards b
JOIN image_source_geometry_revisions p ON p.game_id = :game_id AND p.id = :reverted_id
JOIN image_source_geometry_revisions n ON n.game_id = :game_id AND n.id = :restored_id
LEFT JOIN image_review_items ri ON ri.game_id = :game_id AND ri.recognized_board_id = b.id
WHERE b.game_id = :game_id AND b.source_geometry_revision_id = :reverted_id
  AND b.id <> :board_id
ORDER BY b.position_index, b.id
"""

# References to the correction's source revision outside the reverted board
# and the neighbours that move back with it.
_OTHER_REFERENCES_SQL = """
SELECT
  EXISTS (
    SELECT 1 FROM image_board_geometry_revisions r
    WHERE r.game_id = :game_id AND r.source_geometry_revision_id = :reverted_id
      AND r.recognized_board_id <> :board_id
  ) OR EXISTS (
    SELECT 1 FROM board_render_manifests m
    WHERE m.game_id = :game_id AND m.source_geometry_revision_id = :reverted_id
      AND m.recognized_board_id <> :board_id
      AND NOT (m.recognized_board_id = ANY (CAST(:movable_ids AS uuid[]))
               AND m.geometry_revision = 0)
  ) OR EXISTS (
    SELECT 1 FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id
      AND (c.source_geometry_revision_id = :reverted_id
           OR c.approved_source_geometry_revision_id = :reverted_id)
      AND c.recognized_board_id <> :board_id
      AND NOT (c.recognized_board_id = ANY (CAST(:movable_ids AS uuid[])))
  ) OR EXISTS (
    SELECT 1 FROM verified_training_cohort_cells vc
    WHERE vc.game_id = :game_id AND vc.source_geometry_revision_id = :reverted_id
      -- The reverted board's own cohort cells are a pin (PINNED), not a share.
      AND vc.recognized_board_id <> :board_id
  )
"""

_LATER_GEOMETRY_EVENTS_SQL = """
SELECT EXISTS (
  SELECT 1 FROM image_board_geometry_review_events e
  WHERE e.game_id = :game_id AND e.recognized_board_id = :board_id
    AND (e.geometry_revision > :revision
         OR (e.geometry_revision = :revision AND e.action <> 'geometry_saved'))
)
"""

_CELL_FACTS_SQL = """
SELECT count(*) AS cell_count,
  count(*) FILTER (WHERE CAST(:transaction_at AS timestamptz) IS NULL
                   OR c.created_at > CAST(:transaction_at AS timestamptz)
                   OR c.updated_at > CAST(:transaction_at AS timestamptz)) AS changed_cells,
  count(*) FILTER (WHERE c.created_at < CAST(:transaction_at AS timestamptz)
                   OR c.review_item_id IS DISTINCT FROM :review_item_id) AS foreign_cells
FROM image_symbol_review_cells c
WHERE c.game_id = :game_id
  AND (c.review_item_id = :review_item_id OR c.recognized_board_id = :board_id)
"""

_CELL_EVENT_FACTS_SQL = """
SELECT
  count(*) FILTER (WHERE CAST(:transaction_at AS timestamptz) IS NULL
                   OR e.created_at > CAST(:transaction_at AS timestamptz)) AS later_events,
  count(*) FILTER (WHERE e.created_at < CAST(:transaction_at AS timestamptz)
                   OR e.action = 'board_synchronized') AS ownership_events
FROM image_symbol_review_events e
WHERE e.game_id = :game_id AND e.review_item_id = :review_item_id
"""

_RESOLUTION_FACTS_SQL = """
SELECT
  EXISTS (
    SELECT 1 FROM image_review_resolution_events re
    WHERE re.game_id = :game_id AND re.review_item_id = :review_item_id
  ) AS own_events,
  EXISTS (
    SELECT 1 FROM image_review_resolution_events re
    WHERE re.game_id = :game_id AND re.action = 'superseded'
      AND re.review_item_id <> :review_item_id
      AND re.resolved_value ->> 'ownerReviewItemId' = CAST(:review_item_id AS text)
  ) AS superseded_others,
  EXISTS (
    SELECT 1 FROM image_review_resolution_events re
    WHERE re.game_id = :game_id AND re.review_item_id = :review_item_id
      AND re.action = 'reopened' AND re.idempotency_key = :idempotency_key
  ) AS reopened,
  EXISTS (
    SELECT 1 FROM image_review_resolution_events re
    WHERE re.game_id = :game_id AND re.review_item_id = :review_item_id
      AND re.created_at >= :correction_at AND re.action <> 'reopened'
  ) AS resolved_since
"""

_PINNED_SQL = """
SELECT
  EXISTS (SELECT 1 FROM verified_training_cohort_cells x
          WHERE x.game_id = :game_id
            AND (x.recognized_board_id = :board_id OR x.review_item_id = :review_item_id))
  OR EXISTS (SELECT 1 FROM verified_training_cohort_items x
             WHERE x.game_id = :game_id
               AND (x.recognized_board_id = :board_id OR x.review_item_id = :review_item_id))
  OR EXISTS (SELECT 1 FROM symbol_reference_images x
             WHERE x.game_id = :game_id
               AND (x.source_recognized_board_id = :board_id
                    OR x.source_review_item_id = :review_item_id))
  OR EXISTS (SELECT 1 FROM image_symbol_review_bulk_targets x
             WHERE x.game_id = :game_id
               AND (x.recognized_board_id = :board_id OR x.review_item_id = :review_item_id))
  OR EXISTS (SELECT 1 FROM image_symbol_prediction_revisions x
             WHERE x.game_id = :game_id
               AND (x.recognized_board_id = :board_id OR x.review_item_id = :review_item_id))
"""

_OPEN_WORK_SQL = """
SELECT EXISTS (
  SELECT 1 FROM image_board_geometry_pending p
  WHERE p.game_id = :game_id AND p.source_image_id = :source_image_id AND p.status = 'pending'
) OR EXISTS (
  SELECT 1 FROM recognized_boards b
  JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
  WHERE b.game_id = :game_id AND b.source_image_id = :source_image_id AND ri.status = 'pending'
)
"""

# Rows a slot revert deletes, in deletion order; cascades and the queue
# trigger included so the snapshot holds every removed row.
_SNAPSHOT_QUERIES: Final[tuple[tuple[str, str], ...]] = (
    (
        "image_symbol_review_events",
        "SELECT to_jsonb(t) FROM image_symbol_review_events t "
        "WHERE t.game_id = :game_id AND t.cell_review_id = ANY (CAST(:cell_ids AS uuid[])) "
        "ORDER BY t.id",
    ),
    (
        "image_symbol_review_cells",
        "SELECT to_jsonb(t) FROM image_symbol_review_cells t "
        "WHERE t.game_id = :game_id AND t.id = ANY (CAST(:cell_ids AS uuid[])) "
        "ORDER BY t.cell_index, t.id",
    ),
    (
        "image_board_geometry_review_events",
        "SELECT to_jsonb(t) FROM image_board_geometry_review_events t "
        "WHERE t.game_id = :game_id AND t.recognized_board_id = :board_id ORDER BY t.id",
    ),
    (
        "image_board_geometry_revisions",
        "SELECT to_jsonb(t) FROM image_board_geometry_revisions t "
        "WHERE t.game_id = :game_id AND t.recognized_board_id = :board_id ORDER BY t.revision",
    ),
    (
        "image_review_queue_items",
        "SELECT to_jsonb(t) FROM image_review_queue_items t "
        "WHERE t.game_id = :game_id AND t.review_item_id = :review_item_id",
    ),
    (
        "image_board_search_fast_documents",
        "SELECT to_jsonb(t) FROM image_board_search_fast_documents t "
        "WHERE t.game_id = :game_id AND t.review_item_id = :review_item_id",
    ),
    (
        "image_board_search_candidates",
        "SELECT to_jsonb(t) FROM image_board_search_candidates t "
        "WHERE t.game_id = :game_id AND t.review_item_id = :review_item_id",
    ),
    (
        "image_review_items",
        "SELECT to_jsonb(t) FROM image_review_items t "
        "WHERE t.game_id = :game_id AND t.id = :review_item_id",
    ),
    (
        "board_render_manifests",
        "SELECT to_jsonb(t) FROM board_render_manifests t "
        "WHERE t.game_id = :game_id AND t.recognized_board_id = :board_id "
        "ORDER BY t.geometry_revision",
    ),
    (
        "recognized_boards",
        "SELECT to_jsonb(t) FROM recognized_boards t "
        "WHERE t.game_id = :game_id AND t.id = :board_id",
    ),
)


@dataclass(frozen=True, slots=True)
class _Correction:
    revision_id: UUID
    revision: int
    recognized_board_id: UUID
    review_item_id: UUID
    # NULL for a historical ``legacy_file`` correction (before D-467).
    source_geometry_revision_id: UUID | None
    idempotency_key: UUID
    corrected_by: str
    created_at: datetime
    board_geometry_revision: int
    source_image_id: UUID
    sequence_number: int
    position_index: int
    qualified: bool
    import_job_id: UUID
    review_status: str
    resolution_revision: int
    pending_id: UUID | None
    transaction_at: datetime | None

    @property
    def kind(self) -> GeometryCorrectionKind:
        return (
            GeometryCorrectionKind.PENDING_SLOT
            if self.pending_id is not None
            else GeometryCorrectionKind.BOARD_REVISION
        )


@dataclass(frozen=True, slots=True)
class _SourceRevision:
    id: UUID
    revision: int
    status: str
    engine_kind: str
    created_by: str
    created_at: datetime
    geometry_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class _Evaluation:
    facts: RevertEligibilityFacts
    reverted_source: _SourceRevision
    restored_source: _SourceRevision | None
    movable: tuple[BoardRepointDecision, ...]
    cell_count: int

    @property
    def blocking_reason(self) -> RevertBlockingReason | None:
        return evaluate_revert_eligibility(self.facts)


def _idempotency_lock_key(game_id: UUID, idempotency_key: UUID) -> int:
    """Transaction advisory lock key of one revert request (signed 64-bit)."""

    digest = hashlib.sha256(
        f"geometry-correction-revert:{game_id}:{idempotency_key}".encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _status(value: str | None) -> SourceImageGeometryStatus | None:
    return None if value is None else SourceImageGeometryStatus(value)


def _blocked(reason: RevertBlockingReason) -> ImageReviewConflictError:
    return ImageReviewConflictError(reason.value, blocking_reason_message(reason))


class SqlAlchemyGeometryCorrectionRevertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- reads -------------------------------------------------------------

    def list_recent(
        self, *, game_id: UUID, import_job_id: UUID, limit: int
    ) -> tuple[GeometryCorrectionEntry, ...]:
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        revision_ids = [
            row[0]
            for row in self._read(
                _LIST_SQL,
                {"game_id": game_id, "import_job_id": import_job_id, "row_limit": limit},
            )
        ]
        entries: list[GeometryCorrectionEntry] = []
        for revision_id in revision_ids:
            # READ COMMITTED: a revert committed after the id query removes
            # the correction; the list simply no longer shows it.
            correction = self._correction(game_id, revision_id)
            if correction is None:
                continue
            if correction.source_geometry_revision_id is None:
                # A historical ``legacy_file`` correction has no source
                # revision to fall back to; it is listed, never revertable.
                entries.append(self._entry(correction, RevertBlockingReason.NOT_SUPPORTED))
                continue
            evaluation = self._evaluate(game_id, correction, cas=None)
            entries.append(self._entry(correction, evaluation.blocking_reason))
        return tuple(entries)

    def preview(
        self, *, game_id: UUID, import_job_id: UUID, board_geometry_revision_id: UUID
    ) -> GeometryCorrectionRevertPreview:
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        correction = self._require_correction(game_id, import_job_id, board_geometry_revision_id)
        evaluation = self._evaluate(game_id, correction, cas=None)
        slot = correction.kind is GeometryCorrectionKind.PENDING_SLOT
        restored = evaluation.restored_source
        return GeometryCorrectionRevertPreview(
            correction=self._entry(correction, evaluation.blocking_reason),
            removes_board=slot,
            removed_cell_count=evaluation.cell_count if slot else 0,
            repointed_board_count=len(evaluation.movable),
            restored_cell_decision_count=0,
            reverted_source_geometry_revision_id=evaluation.reverted_source.id,
            restored_source_geometry_revision_id=None if restored is None else restored.id,
            restored_source_engine_kind=None if restored is None else restored.engine_kind,
            restored_source_status=None if restored is None else restored.status,
        )

    # -- revert --------------------------------------------------------------

    def revert(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        board_geometry_revision_id: UUID,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        actor: str,
        reverted_at: datetime,
    ) -> GeometryCorrectionRevertResult:
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.WRITE)
        # Requests with one idempotency key run one after another: a retry that
        # arrives while the first one commits waits here and then reads its
        # stored result, instead of finding the correction already gone.
        self._session.execute(
            select(func.pg_advisory_xact_lock(_idempotency_lock_key(game_id, idempotency_key)))
        )
        prior = self._audit_by_key(game_id, idempotency_key)
        if prior is not None:
            if (
                prior.reverted_board_geometry_revision_id != board_geometry_revision_id
                or prior.import_job_id != import_job_id
            ):
                raise ImageReviewConflictError(
                    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
                    "Ten klucz idempotencji należy już do cofnięcia innej korekty.",
                )
            return _result_from_audit(prior, created=False)
        correction = self._require_correction(game_id, import_job_id, board_geometry_revision_id)
        if correction.kind is GeometryCorrectionKind.BOARD_REVISION:
            raise _blocked(RevertBlockingReason.NOT_SUPPORTED)
        return self._revert_pending_slot(
            game_id=game_id,
            correction=correction,
            idempotency_key=idempotency_key,
            expected_geometry_revision=expected_geometry_revision,
            expected_resolution_revision=expected_resolution_revision,
            actor=actor,
            reverted_at=reverted_at,
        )

    def _revert_pending_slot(
        self,
        *,
        game_id: UUID,
        correction: _Correction,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        actor: str,
        reverted_at: datetime,
    ) -> GeometryCorrectionRevertResult:
        session = self._session
        pending_id = correction.pending_id
        assert pending_id is not None
        # Lock order of the save: sequence -> source -> slot -> board/item.
        acquire_image_sequence_locks(
            session, game_id=game_id, sequence_numbers={correction.sequence_number}
        )
        session.execute(
            select(SourceImageModel.id)
            .where(SourceImageModel.id == correction.source_image_id)
            .with_for_update()
        )
        pending = session.scalar(
            select(ImageBoardGeometryPendingModel)
            .where(ImageBoardGeometryPendingModel.id == pending_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        session.execute(
            select(RecognizedBoardModel.id)
            .where(RecognizedBoardModel.id == correction.recognized_board_id)
            .with_for_update()
        )
        session.execute(
            select(ImageReviewItemModel.id)
            .where(ImageReviewItemModel.id == correction.review_item_id)
            .with_for_update()
        )
        concurrent = self._audit_by_key(game_id, idempotency_key)
        if concurrent is not None:
            # The same request committed while this one waited for the locks.
            if concurrent.reverted_board_geometry_revision_id != correction.revision_id:
                raise ImageReviewConflictError(
                    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
                    "Ten klucz idempotencji należy już do cofnięcia innej korekty.",
                )
            return _result_from_audit(concurrent, created=False)
        locked = self._correction(game_id, correction.revision_id)
        if pending is None or locked is None or locked.pending_id != pending_id:
            # Changed between the unlocked read and the locks (another revert).
            raise _blocked(RevertBlockingReason.NOT_LATEST)
        correction = locked
        state = session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        evaluation = self._evaluate(
            game_id,
            correction,
            cas=(expected_geometry_revision, expected_resolution_revision),
        )
        reason = evaluation.blocking_reason
        if reason is not None:
            raise _blocked(reason)
        restored = evaluation.restored_source
        assert restored is not None
        source = session.get(SourceImageModel, correction.source_image_id, populate_existing=True)
        assert source is not None
        status_before = _status(source.geometry_completeness_status)

        board_id = correction.recognized_board_id
        review_item_id = correction.review_item_id
        cells = tuple(
            session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_item_id == review_item_id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index, ImageSymbolReviewCellModel.id)
                .execution_options(populate_existing=True)
            )
        )
        cell_ids = [cell.id for cell in cells]
        parameters: dict[str, object] = {
            "game_id": game_id,
            "board_id": board_id,
            "review_item_id": review_item_id,
            "cell_ids": cell_ids,
        }
        deleted = [
            {"table": table, "rows": self._json_rows(sql, parameters)}
            for table, sql in _SNAPSHOT_QUERIES
        ]
        rows_by_table = {str(part["table"]): part["rows"] for part in deleted}
        pending_before = self._json_row(
            "SELECT to_jsonb(t) FROM image_board_geometry_pending t "
            "WHERE t.game_id = :game_id AND t.id = :id",
            {"game_id": game_id, "id": pending_id},
        )
        source_revision_before = self._json_row(
            "SELECT to_jsonb(t) FROM image_source_geometry_revisions t "
            "WHERE t.game_id = :game_id AND t.id = :id",
            {"game_id": game_id, "id": evaluation.reverted_source.id},
        )

        # Exact counters: the cells leave every scope they were counted in.
        if state is not None:
            _apply_count_deltas(
                state, before=tuple(_CountedCellState.from_model(cell) for cell in cells)
            )
        available_before = (
            selected_available_cell_count(session, game_id, (correction.sequence_number,))
            if state is not None and correction.qualified
            else None
        )

        for cell in cells:
            session.expunge(cell)
        self._delete(
            "DELETE FROM image_symbol_review_events "
            "WHERE game_id = :game_id AND cell_review_id = ANY (CAST(:cell_ids AS uuid[]))",
            parameters,
            expected=len(rows_by_table["image_symbol_review_events"]),
        )
        self._delete(
            "DELETE FROM image_symbol_review_cells "
            "WHERE game_id = :game_id AND id = ANY (CAST(:cell_ids AS uuid[]))",
            parameters,
            expected=len(cells),
        )
        self._delete(
            "DELETE FROM image_board_geometry_review_events "
            "WHERE game_id = :game_id AND recognized_board_id = :board_id",
            parameters,
            expected=len(rows_by_table["image_board_geometry_review_events"]),
        )
        self._delete(
            "DELETE FROM image_board_geometry_revisions "
            "WHERE game_id = :game_id AND recognized_board_id = :board_id",
            parameters,
            expected=len(rows_by_table["image_board_geometry_revisions"]),
        )
        self._delete(
            """UPDATE image_board_geometry_pending
            SET status = 'pending', recognized_board_id = NULL, review_item_id = NULL,
                resolved_geometry_revision = NULL, resolved_at = NULL, superseded_at = NULL,
                updated_at = :reverted_at
            WHERE game_id = :game_id AND id = :pending_id AND status = 'resolved'
              AND recognized_board_id = :board_id AND review_item_id = :review_item_id""",
            {**parameters, "pending_id": pending_id, "reverted_at": reverted_at},
            expected=1,
        )
        self._delete(
            "DELETE FROM image_review_items WHERE game_id = :game_id AND id = :review_item_id",
            parameters,
            expected=1,
        )
        self._delete(
            "DELETE FROM recognized_boards WHERE game_id = :game_id AND id = :board_id",
            parameters,
            expected=1,
        )
        self._delete(
            "UPDATE image_source_geometry_revisions SET status = :reverted "
            "WHERE game_id = :game_id AND id = :id AND status = :status",
            {
                "game_id": game_id,
                "id": evaluation.reverted_source.id,
                "status": evaluation.reverted_source.status,
                "reverted": REVERTED_SOURCE_GEOMETRY_STATUS,
            },
            expected=1,
        )
        self._forget(board_id=board_id, review_item_id=review_item_id, pending=pending)

        moved = apply_board_repoint(session, game_id, evaluation.movable)
        projection = SqlAlchemyBoardSearchProjectionRepository(session)
        moved_items = tuple(
            decision.review_item_id for decision in moved if decision.review_item_id is not None
        )
        if moved_items:
            projection.sync_review_items(moved_items)
        projection.reconcile_sequence(game_id, correction.sequence_number)
        if available_before is not None and state is not None:
            session.flush()
            state.cell_count += (
                selected_available_cell_count(session, game_id, (correction.sequence_number,))
                - available_before
            )

        recompute = recompute_source_image_geometry_completeness(
            session, game_id, correction.source_image_id, actor=actor, now=reverted_at
        )
        if image_admission_blocks_revert(status_before, recompute.status):
            raise _blocked(RevertBlockingReason.IMAGE_ADMITTED)
        source = session.get(SourceImageModel, correction.source_image_id)
        assert source is not None
        if self._scalar(
            _OPEN_WORK_SQL, {"game_id": game_id, "source_image_id": correction.source_image_id}
        ):
            source.status = "waiting_for_review"

        # The cells left the derivation input of the super game series.
        record_super_game_input_change(session, game_id, source="geometry_correction_revert")
        SymbolCellReviewWriteThroughCoordinator(session).synchronize_after_cell_mutation(
            game_id=game_id
        )

        snapshot: dict[str, object] = {
            "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
            "kind": GeometryCorrectionKind.PENDING_SLOT.value,
            "deleted": deleted,
            "updated": {
                "image_board_geometry_pending": pending_before,
                "image_source_geometry_revisions": source_revision_before,
            },
            "repointedBoards": [
                {
                    "recognizedBoardId": str(decision.recognized_board_id),
                    "reviewItemId": (
                        None if decision.review_item_id is None else str(decision.review_item_id)
                    ),
                    "fromSourceGeometryRevisionId": str(decision.from_revision_id),
                    "toSourceGeometryRevisionId": str(decision.to_revision_id),
                }
                for decision in moved
            ],
            "removedCellCount": len(cells),
            "imageGeometryStatusBefore": None if status_before is None else status_before.value,
            "imageGeometryStatusAfter": (
                None if recompute.status is None else recompute.status.value
            ),
        }
        audit = ImageGeometryCorrectionRevertModel(
            id=uuid4(),
            game_id=game_id,
            import_job_id=correction.import_job_id,
            source_image_id=correction.source_image_id,
            sequence_number=correction.sequence_number,
            position_index=correction.position_index,
            kind=GeometryCorrectionKind.PENDING_SLOT.value,
            pending_geometry_id=pending_id,
            recognized_board_id=board_id,
            review_item_id=review_item_id,
            reverted_geometry_revision=correction.revision,
            reverted_board_geometry_revision_id=correction.revision_id,
            reverted_source_geometry_revision_id=evaluation.reverted_source.id,
            restored_source_geometry_revision_id=restored.id,
            restored_geometry_revision=None,
            reverted_idempotency_key=correction.idempotency_key,
            idempotency_key=idempotency_key,
            snapshot=snapshot,
            snapshot_checksum_sha256=snapshot_checksum_sha256(snapshot),
            actor=actor,
            created_at=reverted_at,
        )
        session.add(audit)
        session.flush()
        return _result_from_audit(audit, created=True)

    # -- facts -----------------------------------------------------------------

    def _evaluate(
        self,
        game_id: UUID,
        correction: _Correction,
        *,
        cas: tuple[int, int] | None,
    ) -> _Evaluation:
        revisions = [
            _SourceRevision(*row)
            for row in self._read(
                _SOURCE_REVISIONS_SQL,
                {"game_id": game_id, "source_image_id": correction.source_image_id},
            )
        ]
        live = [value for value in revisions if value.status != REVERTED_SOURCE_GEOMETRY_STATUS]
        reverted = next(
            (value for value in revisions if value.id == correction.source_geometry_revision_id),
            None,
        )
        if reverted is None:  # pragma: no cover - FK guarantees the row
            raise ImageReviewNotFoundError(
                GEOMETRY_CORRECTION_NOT_FOUND, "Nie znaleziono rewizji źródła tej korekty."
            )
        restored = max(
            (value for value in live if value.revision < reverted.revision),
            key=lambda value: value.revision,
            default=None,
        )
        newest_live = max(live, key=lambda value: value.revision, default=None)
        slot = correction.kind is GeometryCorrectionKind.PENDING_SLOT
        board_id = correction.recognized_board_id
        review_item_id = correction.review_item_id
        transaction_at = correction.transaction_at

        latest = (
            correction.board_geometry_revision == correction.revision
            and not self._scalar(
                _LATER_GEOMETRY_EVENTS_SQL,
                {"game_id": game_id, "board_id": board_id, "revision": correction.revision},
            )
            and self._audit_by_revision(game_id, correction.revision_id) is None
        )
        # The save must have created the revision itself; a deduplicated
        # (pre-existing) revision is shared with an earlier write.
        created_by_correction = (
            reverted.created_at == transaction_at
            if transaction_at is not None
            else reverted.engine_kind == "manual_v1"
            and reverted.created_by == correction.corrected_by
        )
        movable: list[BoardRepointDecision] = []
        shared = restored is None or not created_by_correction
        if not shared and restored is not None:
            for row in self._read(
                _NEIGHBOURS_SQL,
                {
                    "game_id": game_id,
                    "reverted_id": reverted.id,
                    "restored_id": restored.id,
                    "board_id": board_id,
                },
            ):
                movable_now = (
                    int(row.geometry_revision) == 0
                    and row.status != "rejected"
                    and bool(row.checksum_current)
                    and bool(row.in_slots)
                    and bool(row.same_source)
                    and row.reverted_entry is not None
                    and row.reverted_entry == row.restored_entry
                    and not row.manifest_drift
                    and not row.cell_drift
                    and not row.cohort_pinned
                )
                if not movable_now:
                    shared = True
                    continue
                movable.append(
                    BoardRepointDecision(
                        recognized_board_id=row.id,
                        source_image_id=correction.source_image_id,
                        review_item_id=row.review_item_id,
                        position_index=int(row.position_index),
                        from_revision_id=reverted.id,
                        from_revision=reverted.revision,
                        to_revision_id=restored.id,
                        to_revision=restored.revision,
                        to_revision_status=restored.status,
                        to_geometry_checksum_sha256=restored.geometry_checksum_sha256,
                        reason_code=None,
                    )
                )
            if not shared:
                shared = bool(
                    self._scalar(
                        _OTHER_REFERENCES_SQL,
                        {
                            "game_id": game_id,
                            "reverted_id": reverted.id,
                            "board_id": board_id,
                            "movable_ids": [value.recognized_board_id for value in movable],
                        },
                    )
                )

        cell_facts = self._read(
            _CELL_FACTS_SQL,
            {
                "game_id": game_id,
                "review_item_id": review_item_id,
                "board_id": board_id,
                "transaction_at": transaction_at,
            },
        ).one()
        event_facts = self._read(
            _CELL_EVENT_FACTS_SQL,
            {
                "game_id": game_id,
                "review_item_id": review_item_id,
                "transaction_at": transaction_at,
            },
        ).one()
        resolution = self._read(
            _RESOLUTION_FACTS_SQL,
            {
                "game_id": game_id,
                "review_item_id": review_item_id,
                "idempotency_key": correction.idempotency_key,
                "correction_at": correction.created_at,
            },
        ).one()
        source_status = self._scalar(
            "SELECT geometry_completeness_status FROM source_images "
            "WHERE game_id = :game_id AND id = :source_image_id",
            {"game_id": game_id, "source_image_id": correction.source_image_id},
        )
        image_status = _status(source_status)
        if slot:
            # Every row of the slot's board was written by the correction:
            # any resolution event or a foreign cell or event is a later change.
            review_resolved = correction.review_status != "pending" or bool(resolution.own_events)
            ownership = (
                bool(resolution.superseded_others)
                or int(cell_facts.foreign_cells) > 0
                or int(event_facts.ownership_events) > 0
            )
            image_after = predicted_status_after_slot_revert(image_status)
        else:
            # TASK-0946 finalizes the case-A facts; the list shows them only.
            review_resolved = correction.review_status in _RESOLVED_REVIEW_STATUSES or bool(
                resolution.resolved_since
            )
            ownership = False
            image_after = image_status
        facts = RevertEligibilityFacts(
            kind=correction.kind,
            latest_board_revision=latest,
            cas_matches=(
                None
                if cas is None
                else (correction.board_geometry_revision, correction.resolution_revision) == cas
            ),
            source_revision_newest_live=(
                newest_live is not None
                and newest_live.id == reverted.id
                and reverted.status != REVERTED_SOURCE_GEOMETRY_STATUS
            ),
            source_revision_shared=shared,
            cells_changed_after_correction=(
                int(cell_facts.changed_cells) > 0 or int(event_facts.later_events) > 0
            ),
            review_resolved=review_resolved,
            sequence_ownership_changed=ownership,
            image_status_before=image_status,
            image_status_after=image_after,
            pinned=bool(
                self._scalar(
                    _PINNED_SQL,
                    {"game_id": game_id, "board_id": board_id, "review_item_id": review_item_id},
                )
            ),
            reopened_resolution=(not slot and bool(resolution.reopened)),
            revert_supported=slot,
        )
        return _Evaluation(
            facts=facts,
            reverted_source=reverted,
            restored_source=restored,
            movable=tuple(movable),
            cell_count=int(cell_facts.cell_count),
        )

    # -- helpers -----------------------------------------------------------

    def _correction(self, game_id: UUID, revision_id: UUID) -> _Correction | None:
        row = self._read(_CORRECTION_SQL, {"game_id": game_id, "revision_id": revision_id}).first()
        if row is None:
            return None
        return _Correction(
            revision_id=row.revision_id,
            revision=int(row.revision),
            recognized_board_id=row.recognized_board_id,
            review_item_id=row.review_item_id,
            source_geometry_revision_id=row.source_geometry_revision_id,
            idempotency_key=row.idempotency_key,
            corrected_by=str(row.corrected_by),
            created_at=row.created_at,
            board_geometry_revision=int(row.board_geometry_revision),
            source_image_id=row.source_image_id,
            sequence_number=int(row.sequence_number),
            position_index=int(row.position_index),
            qualified=bool(row.qualified),
            import_job_id=row.import_job_id,
            review_status=str(row.review_status),
            resolution_revision=int(row.resolution_revision),
            pending_id=row.pending_id,
            transaction_at=row.transaction_at,
        )

    def _require_correction(
        self, game_id: UUID, import_job_id: UUID, revision_id: UUID
    ) -> _Correction:
        correction = self._correction(game_id, revision_id)
        if correction is not None and correction.import_job_id == import_job_id:
            if correction.source_geometry_revision_id is None:
                raise _blocked(RevertBlockingReason.NOT_SUPPORTED)
            return correction
        reverted = self._audit_by_revision(game_id, revision_id)
        if reverted is not None and reverted.import_job_id == import_job_id:
            raise _blocked(RevertBlockingReason.NOT_LATEST)
        raise ImageReviewNotFoundError(
            GEOMETRY_CORRECTION_NOT_FOUND, "Nie znaleziono tej korekty w tym imporcie."
        )

    def _entry(
        self, correction: _Correction, reason: RevertBlockingReason | None
    ) -> GeometryCorrectionEntry:
        return GeometryCorrectionEntry(
            board_geometry_revision_id=correction.revision_id,
            kind=correction.kind,
            recognized_board_id=correction.recognized_board_id,
            review_item_id=correction.review_item_id,
            pending_geometry_id=correction.pending_id,
            source_image_id=correction.source_image_id,
            sequence_number=correction.sequence_number,
            position_index=correction.position_index,
            created_at=correction.created_at,
            actor=correction.corrected_by,
            geometry_revision=correction.revision,
            resolution_revision=correction.resolution_revision,
            blocking_reason=reason,
        )

    def _audit_by_key(
        self, game_id: UUID, idempotency_key: UUID
    ) -> ImageGeometryCorrectionRevertModel | None:
        return self._session.scalar(
            select(ImageGeometryCorrectionRevertModel).where(
                ImageGeometryCorrectionRevertModel.game_id == game_id,
                ImageGeometryCorrectionRevertModel.idempotency_key == idempotency_key,
            )
        )

    def _audit_by_revision(
        self, game_id: UUID, revision_id: UUID
    ) -> ImageGeometryCorrectionRevertModel | None:
        return self._session.scalar(
            select(ImageGeometryCorrectionRevertModel).where(
                ImageGeometryCorrectionRevertModel.game_id == game_id,
                ImageGeometryCorrectionRevertModel.reverted_board_geometry_revision_id
                == revision_id,
            )
        )

    def _read(self, sql: str, parameters: Mapping[str, object]) -> Any:
        # Connection-level execution keeps the read route of a read-only
        # transaction (see ``image_geometry_completeness_state_repository``).
        return self._session.connection().execute(text(sql), dict(parameters))

    def _scalar(self, sql: str, parameters: Mapping[str, object]) -> Any:
        return self._read(sql, parameters).scalar()

    def _json_rows(self, sql: str, parameters: Mapping[str, object]) -> list[object]:
        return [row[0] for row in self._read(sql, parameters)]

    def _json_row(self, sql: str, parameters: Mapping[str, object]) -> object:
        rows = self._json_rows(sql, parameters)
        if len(rows) != 1:
            raise RuntimeError("GEOMETRY_REVERT_SNAPSHOT_ROW_MISSING")
        return rows[0]

    def _delete(self, sql: str, parameters: Mapping[str, object], *, expected: int) -> None:
        result: Any = self._session.execute(text(sql), dict(parameters))
        if result.rowcount != expected:
            # Never mask a concurrent or unexpected change: the caller's
            # transaction rolls back as a whole.
            raise ImageReviewConflictError(
                "GEOMETRY_REVERT_WRITE_CONFLICT",
                "Stan korekty zmienił się w trakcie cofania; nic nie zostało zmienione.",
                details={"expectedRows": expected, "actualRows": int(result.rowcount)},
            )

    def _forget(
        self,
        *,
        board_id: UUID,
        review_item_id: UUID,
        pending: ImageBoardGeometryPendingModel,
    ) -> None:
        """Drop identity-map copies of deleted rows; refresh the updated slot."""

        for instance in list(self._session.identity_map.values()):
            if (
                (isinstance(instance, RecognizedBoardModel) and instance.id == board_id)
                or (isinstance(instance, ImageReviewItemModel) and instance.id == review_item_id)
                or (
                    isinstance(instance, ImageBoardGeometryRevisionModel)
                    and instance.recognized_board_id == board_id
                )
            ):
                self._session.expunge(instance)
        self._session.expire(pending)


def _result_from_audit(
    audit: ImageGeometryCorrectionRevertModel, *, created: bool
) -> GeometryCorrectionRevertResult:
    snapshot: Mapping[str, Any] = audit.snapshot
    repointed: Sequence[Mapping[str, Any]] = snapshot.get("repointedBoards", ())
    status_after = snapshot.get("imageGeometryStatusAfter")
    return GeometryCorrectionRevertResult(
        revert_id=audit.id,
        created=created,
        kind=GeometryCorrectionKind(audit.kind),
        board_geometry_revision_id=audit.reverted_board_geometry_revision_id,
        pending_geometry_id=audit.pending_geometry_id,
        recognized_board_id=audit.recognized_board_id,
        review_item_id=audit.review_item_id,
        reverted_source_geometry_revision_id=audit.reverted_source_geometry_revision_id,
        restored_source_geometry_revision_id=audit.restored_source_geometry_revision_id,
        repointed_board_ids=tuple(UUID(str(value["recognizedBoardId"])) for value in repointed),
        removed_cell_count=int(snapshot.get("removedCellCount", 0)),
        source_image_geometry_status=(
            None if status_after is None else SourceImageGeometryStatus(str(status_after))
        ),
        snapshot_checksum_sha256=audit.snapshot_checksum_sha256,
        created_at=audit.created_at,
    )


__all__ = ["SqlAlchemyGeometryCorrectionRevertRepository"]
