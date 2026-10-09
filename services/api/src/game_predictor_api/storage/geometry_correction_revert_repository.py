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

Case A (``board_revision``, TASK-0946): the save added revision ``N`` of an
existing board. Its revert, under the save's locks (review sequences ->
source image -> board -> review item -> cells), refuses with the first
blocking rule, then appends revision ``N + 1`` with the geometry of the
board's previous revision (``0`` = the import snapshot) and the stored render
specification of that revision (revision ``virtual_render_spec`` and a new
manifest row for ``N + 1``, with the pixel checksums the specs render today
through the preview's renderer), points it at the board's previous source
revision, restores the board projection (engine, approval time and actor
also through earlier reverts' audits) and every cell's render and decision
from the earliest cell event of the correction transaction (an approval only
on identical rendered pixels, D-462; an approval whose provenance is not
recorded refuses with ``HISTORY_INCOMPLETE``), writes ``geometry_reverted`` board and cell
events, marks the correction's source revision ``reverted`` and re-points
the neighbours back as case B, and recomputes counters, search, the gate and
the super game input version. Nothing is deleted.

"Transaction of the correction" is identified structurally: ``T`` is the
``created_at`` (server ``now()``) of the render manifest the save wrote for
its board geometry revision; cells, cell events and the source revision the
same save wrote carry the same ``now()`` (Z1, verified in TASK-0946). The
events of one transaction therefore share one timestamp; their order within
a cell is its cell revision.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionEntry,
    GeometryCorrectionRevertPreview,
    GeometryCorrectionRevertResult,
    RestoredRenderRequest,
    RestoredRenderVerifier,
)
from game_predictor_api.domain.board_render_manifests import (
    BoardRenderManifestError,
    revision_render_manifest,
    sha256_canonical_json,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_correction_reverts import (
    CORRECTION_TRANSACTION_CELL_ACTIONS,
    GEOMETRY_CORRECTION_NOT_FOUND,
    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
    GEOMETRY_REVERT_RENDER_FAILED,
    GEOMETRY_REVERT_RENDERER_UNAVAILABLE,
    GEOMETRY_REVERTED_ACTION,
    REVERTED_SOURCE_GEOMETRY_STATUS,
    SNAPSHOT_SCHEMA_VERSION,
    GeometryCorrectionKind,
    PreviousCellDecision,
    RevertBlockingReason,
    RevertEligibilityFacts,
    blocking_reason_message,
    canonical_snapshot_bytes,
    evaluate_revert_eligibility,
    image_admission_blocks_revert,
    predicted_status_after_slot_revert,
    restore_cell_decision,
    restored_approved_geometry_revision,
    snapshot_checksum_sha256,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    AdditiveVirtualGeometryContractError,
)
from game_predictor_api.storage.board_render_manifest_repository import add_board_render_manifest
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
from game_predictor_api.storage.image_review_repository import (
    acquire_image_review_sequence_locks,
    acquire_image_sequence_locks,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
    _append_symbol_cell_event,
    _apply_count_deltas,
    _CellPreviousState,
    _CountedCellState,
    _verification_v2,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
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
                   OR e.action = 'board_synchronized') AS ownership_events,
  count(*) FILTER (WHERE e.created_at = CAST(:transaction_at AS timestamptz)
                   AND e.action <> ALL (CAST(:transaction_actions AS text[])))
    AS foreign_transaction_events
FROM image_symbol_review_events e
WHERE e.game_id = :game_id AND e.review_item_id = :review_item_id
"""

# Case A: the corrected board, its review item's immutable import snapshot,
# the corrected revision's geometry and the approval the correction replaced.
_BOARD_REVISION_STATE_SQL = """
SELECT b.geometry_qualification IS NOT NULL AS board_qualified, b.asset_mode,
  b.grid_rows, b.grid_columns, ri.snapshot AS item_snapshot, r.geometry AS corrected_geometry,
  ARRAY(
    SELECT e.previous_approved_geometry_revision
    FROM image_board_geometry_review_events e
    WHERE e.game_id = b.game_id AND e.recognized_board_id = b.id
      AND e.geometry_revision = r.revision AND e.action = 'geometry_saved'
  ) AS previous_approved
FROM recognized_boards b
JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.id = :review_item_id
JOIN image_board_geometry_revisions r ON r.game_id = b.game_id AND r.id = :revision_id
WHERE b.game_id = :game_id AND b.id = :board_id
"""

_PREVIOUS_BOARD_REVISION_SQL = """
SELECT revision, corners, geometry, asset_mode, source_geometry_revision_id,
  virtual_render_spec, virtual_render_spec_checksum_sha256
FROM image_board_geometry_revisions
WHERE game_id = :game_id AND recognized_board_id = :board_id AND revision < :revision
ORDER BY revision DESC
LIMIT 1
"""

_SLOT_ENTRY_SQL = """
SELECT jsonb_path_query_first(board_geometries, '$[*] ? (@.positionIndex == $position)',
  jsonb_build_object('position', CAST(:position AS integer)))
FROM image_source_geometry_revisions
WHERE game_id = :game_id AND id = :id
"""

_RENDER_MANIFEST_SQL = """
SELECT source_geometry_revision_id, extractor_version, cells
FROM board_render_manifests
WHERE game_id = :game_id AND recognized_board_id = :board_id AND geometry_revision = :revision
"""

# The event that set the restored approval (the board's approval metadata).
_APPROVAL_EVENT_SQL = """
SELECT created_at, actor
FROM image_board_geometry_review_events
WHERE game_id = :game_id AND recognized_board_id = :board_id
  AND approved_geometry_revision = :approved
  AND action IN ('approved', 'geometry_saved', 'backfilled')
  AND geometry_revision < :revision
ORDER BY created_at DESC, id DESC
LIMIT 1
"""

# Case-A revert audits of the board: what an earlier revert restored (the
# board projection after it, with the approval time and actor it kept).
_BOARD_REVERT_AUDITS_SQL = """
SELECT restored_geometry_revision, created_at, snapshot -> 'board' -> 'after' AS board_after
FROM image_geometry_correction_reverts
WHERE game_id = :game_id AND recognized_board_id = :board_id AND kind = 'board_revision'
ORDER BY created_at DESC, id DESC
"""

_CELLS_OF_ITEM_SQL = """
SELECT id, cell_index, asset_mode, geometry_revision, approved_crop_sample_id,
  approved_crop_checksum_sha256, approved_geometry_revision, approved_asset_mode,
  approved_source_geometry_revision_id, approved_render_spec_checksum_sha256,
  approved_rendered_pixel_checksum_sha256
FROM image_symbol_review_cells
WHERE game_id = :game_id AND (review_item_id = :review_item_id OR recognized_board_id = :board_id)
ORDER BY cell_index, id
"""

# Case A pins (lead decision for D-538, TASK-0946 audit P1-1):
# - training cohorts and the symbol reference library: always;
# - bulk targets: by identity, when they expect the discarded revision
#   (``expected_geometry_revision >= N``);
# - prediction revisions: by identity, when a predicted cell names the
#   discarded render (manifest revision ``>= N``): its
#   ``virtualCell.renderSpecChecksumSha256`` (unique per revision, the spec
#   carries the revision), else its ``virtualCell.cropChecksumSha256`` when
#   that pixel checksum belongs to no render the board keeps (revision
#   ``< N``); a revision without either identity falls back to its time
#   (written at or after the correction).
# The import's prediction revision predicted the restored render and does not
# pin the revert.
_PINNED_BOARD_REVISION_SQL = """
WITH renders AS (
  SELECT m.geometry_revision >= :revision AS discarded,
    e ->> 'renderSpecChecksumSha256' AS spec,
    e ->> 'renderedPixelChecksumSha256' AS pixels
  FROM board_render_manifests m, jsonb_array_elements(m.cells -> 'cells') e
  WHERE m.game_id = :game_id AND m.recognized_board_id = :board_id
),
discarded_specs AS (SELECT spec FROM renders WHERE discarded),
discarded_pixels AS (
  SELECT pixels FROM renders WHERE discarded
  EXCEPT SELECT pixels FROM renders WHERE NOT discarded
),
predictions AS (
  SELECT x.created_at,
    CASE WHEN jsonb_typeof(x.predictions) = 'array' THEN x.predictions
         ELSE '[]'::jsonb END AS cells
  FROM image_symbol_prediction_revisions x
  WHERE x.game_id = :game_id
    AND (x.recognized_board_id = :board_id OR x.review_item_id = :review_item_id)
)
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
               AND (x.recognized_board_id = :board_id OR x.review_item_id = :review_item_id)
               AND x.expected_geometry_revision >= :revision)
  OR EXISTS (
    SELECT 1 FROM predictions p
    WHERE CASE
      WHEN EXISTS (
        SELECT 1 FROM jsonb_array_elements(p.cells) c
        WHERE jsonb_typeof(c -> 'virtualCell' -> 'renderSpecChecksumSha256') = 'string'
           OR jsonb_typeof(c -> 'virtualCell' -> 'cropChecksumSha256') = 'string')
      THEN EXISTS (
        SELECT 1 FROM jsonb_array_elements(p.cells) c
        WHERE c -> 'virtualCell' ->> 'renderSpecChecksumSha256'
                IN (SELECT spec FROM discarded_specs)
           OR (jsonb_typeof(c -> 'virtualCell' -> 'renderSpecChecksumSha256') IS DISTINCT
                 FROM 'string'
               AND c -> 'virtualCell' ->> 'cropChecksumSha256'
                 IN (SELECT pixels FROM discarded_pixels)))
      ELSE CAST(:transaction_at AS timestamptz) IS NULL
        OR p.created_at >= CAST(:transaction_at AS timestamptz)
    END)
"""

_MANUAL_ENGINE_NAME: Final = "manual_v1"
_MANUAL_ENGINE_VERSION: Final = "manual-source-geometry-v1"
_REVERT_COMMAND_SCHEMA: Final = "geometry-correction-revert-command-v1"

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
class _BoardRevisionPlan:
    """Everything a case-A revert writes, read (under lock for a revert).

    ``previous_revision`` is the board revision whose geometry comes back
    (``0`` = the imported geometry); ``render_spec`` is its stored render,
    reused verbatim by revision ``N + 1``. ``earliest_events`` maps each cell
    to the earliest event of the correction transaction (the lowest cell
    revision among the events sharing the transaction's ``now()``).
    """

    previous_revision: int
    restored_source: _SourceRevision
    board_geometry: dict[str, Any]
    corners: list[dict[str, float]]
    render_spec: dict[str, Any]
    render_spec_checksum_sha256: str
    extractor_version: str
    engine_name: str
    engine_version: str
    correction_previous_approved: int | None
    approved_geometry_revision: int | None
    approved_at: datetime | None
    approved_by: str | None
    manifest_cells: dict[int, Mapping[str, Any]]
    earliest_events: dict[UUID, ImageSymbolReviewEventModel]
    # Each cell's approval columns from before the correction (P0-2).
    histories: dict[UUID, ApprovalHistory]


@dataclass(frozen=True, slots=True)
class _Evaluation:
    facts: RevertEligibilityFacts
    reverted_source: _SourceRevision
    restored_source: _SourceRevision | None
    movable: tuple[BoardRepointDecision, ...]
    cell_count: int
    board_plan: _BoardRevisionPlan | None = None

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
        plan = evaluation.board_plan
        # Case A restores the board's own previous source revision.
        restored = evaluation.restored_source if plan is None else plan.restored_source
        return GeometryCorrectionRevertPreview(
            correction=self._entry(correction, evaluation.blocking_reason),
            removes_board=slot,
            removed_cell_count=evaluation.cell_count if slot else 0,
            repointed_board_count=len(evaluation.movable),
            restored_cell_decision_count=0 if plan is None else len(plan.earliest_events),
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
        render_verifier: RestoredRenderVerifier | None = None,
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
            return self._revert_board_revision(
                game_id=game_id,
                correction=correction,
                idempotency_key=idempotency_key,
                expected_geometry_revision=expected_geometry_revision,
                expected_resolution_revision=expected_resolution_revision,
                actor=actor,
                reverted_at=reverted_at,
                render_verifier=render_verifier,
            )
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

    def _revert_board_revision(
        self,
        *,
        game_id: UUID,
        correction: _Correction,
        idempotency_key: UUID,
        expected_geometry_revision: int,
        expected_resolution_revision: int,
        actor: str,
        reverted_at: datetime,
        render_verifier: RestoredRenderVerifier | None,
    ) -> GeometryCorrectionRevertResult:
        """Case A (TASK-0946): append revision ``N + 1`` = revision ``N - 1``.

        Nothing is deleted. The new revision copies the previous revision's
        geometry and reuses its stored render specification, points at the
        board's previous source revision, and the cells get their render and
        their decisions from before the correction back. The restored cells
        are rendered again (``render_verifier``, the preview's render): the
        new manifest records the pixels the specs produce today and D-462
        compares them with each approval (audit P0-3).
        """

        session = self._session
        # Lock order of the save: review sequences -> source -> board/item.
        acquire_image_review_sequence_locks(
            session,
            game_id=game_id,
            review_item_id=correction.review_item_id,
            requested_sequence_number=None,
        )
        session.execute(
            select(SourceImageModel.id)
            .where(SourceImageModel.id == correction.source_image_id)
            .with_for_update()
        )
        board = session.scalar(
            select(RecognizedBoardModel)
            .where(RecognizedBoardModel.id == correction.recognized_board_id)
            .with_for_update()
            .execution_options(populate_existing=True)
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
        if (
            board is None
            or locked is None
            or locked.kind is not GeometryCorrectionKind.BOARD_REVISION
        ):
            raise _blocked(RevertBlockingReason.NOT_LATEST)
        correction = locked
        state = session.get(ImageSymbolReviewStateModel, game_id, with_for_update=True)
        cells = tuple(
            session.scalars(
                select(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.review_item_id == correction.review_item_id,
                )
                .order_by(ImageSymbolReviewCellModel.cell_index, ImageSymbolReviewCellModel.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        evaluation = self._evaluate(
            game_id,
            correction,
            cas=(expected_geometry_revision, expected_resolution_revision),
        )
        reason = evaluation.blocking_reason
        if reason is not None:
            raise _blocked(reason)
        plan = evaluation.board_plan
        assert plan is not None
        if set(plan.earliest_events) != {cell.id for cell in cells}:
            raise _blocked(RevertBlockingReason.NOT_SUPPORTED)
        source = session.get(SourceImageModel, correction.source_image_id, populate_existing=True)
        assert source is not None
        status_before = _status(source.geometry_completeness_status)
        if render_verifier is None:
            raise ImageReviewConflictError(
                GEOMETRY_REVERT_RENDERER_UNAVAILABLE,
                "Cofnięcie korekty planszy wymaga renderera komórek.",
            )
        rendered = render_verifier.rendered_pixel_checksums(
            RestoredRenderRequest(
                review_item_id=correction.review_item_id,
                source_image_id=source.id,
                source_relative_path=source.relative_path,
                source_checksum_sha256=source.checksum_sha256,
                source_width=int(source.oriented_width or source.width),
                source_height=int(source.oriented_height or source.height),
                geometry_revision=correction.revision,
                resolution_revision=correction.resolution_revision,
                topology=BoardTopology(rows=board.grid_rows or 3, columns=board.grid_columns or 5),
                render_specs={
                    index: cast(Mapping[str, object], entry["renderSpec"])
                    for index, entry in plan.manifest_cells.items()
                },
            )
        )
        if set(rendered) != set(plan.manifest_cells):
            raise ImageReviewConflictError(
                GEOMETRY_REVERT_RENDER_FAILED,
                "Renderer nie zwrócił wszystkich przywracanych komórek.",
            )
        # The restored specification with the pixels it renders today.
        render_spec = _with_rendered_pixels(plan.render_spec, rendered)
        render_spec_checksum = sha256_canonical_json(render_spec)

        board_id = correction.recognized_board_id
        review_item_id = correction.review_item_id
        written_revision = correction.revision + 1
        parameters: dict[str, object] = {
            "game_id": game_id,
            "board_id": board_id,
            "cell_ids": [cell.id for cell in cells],
        }
        board_before = self._json_row(_BOARD_JSON_SQL, parameters)
        cells_before = self._json_rows(_CELLS_JSON_SQL, parameters)
        source_revision_before = self._json_row(
            "SELECT to_jsonb(t) FROM image_source_geometry_revisions t "
            "WHERE t.game_id = :game_id AND t.id = :id",
            {"game_id": game_id, "id": evaluation.reverted_source.id},
        )

        # Revision N + 1: the previous geometry and its stored render.
        restored_source = plan.restored_source
        record = ImageBoardGeometryRevisionModel(
            review_item_id=review_item_id,
            recognized_board_id=board_id,
            revision=written_revision,
            idempotency_key=idempotency_key,
            command_sha256=hashlib.sha256(
                canonical_snapshot_bytes(
                    {
                        "action": GEOMETRY_REVERTED_ACTION,
                        "revertedBoardGeometryRevisionId": str(correction.revision_id),
                        "restoredGeometryRevision": plan.previous_revision,
                        "schemaVersion": _REVERT_COMMAND_SCHEMA,
                    }
                )
            ).hexdigest(),
            corners=plan.corners,
            geometry=dict(plan.board_geometry),
            asset_mode="virtual_source",
            source_geometry_revision_id=restored_source.id,
            geometry_checksum_sha256=restored_source.geometry_checksum_sha256,
            virtual_render_spec=render_spec,
            virtual_render_spec_checksum_sha256=render_spec_checksum,
            board_relative_path=None,
            board_checksum_sha256=None,
            cropper_version=plan.extractor_version,
            crop_artifacts=None,
            corrected_by=actor,
            created_at=reverted_at,
        )
        session.add(record)
        try:
            manifest = revision_render_manifest(
                recognized_board_id=board_id,
                geometry_revision=written_revision,
                virtual_render_spec=render_spec,
                virtual_render_spec_checksum_sha256=render_spec_checksum,
            )
        except BoardRenderManifestError as error:
            raise ImageReviewConflictError(error.code, error.message) from error
        add_board_render_manifest(
            session,
            game_id=game_id,
            manifest=manifest,
            source_geometry_revision_id=restored_source.id,
            extractor_version=plan.extractor_version,
        )

        # The board projection of the restored geometry.
        approved_before = board.approved_geometry_revision
        board.geometry_revision = written_revision
        board.approved_geometry_revision = plan.approved_geometry_revision
        board.geometry_approved_at = plan.approved_at
        board.geometry_approved_by = plan.approved_by
        board.board_geometry = dict(plan.board_geometry)
        board.source_geometry_revision_id = restored_source.id
        board.geometry_checksum_sha256 = restored_source.geometry_checksum_sha256
        board.geometry_engine_name = plan.engine_name
        board.geometry_engine_version = plan.engine_version
        session.add(
            ImageBoardGeometryReviewEventModel(
                review_item_id=review_item_id,
                recognized_board_id=board_id,
                geometry_revision=written_revision,
                grid_rows=board.grid_rows or 3,
                grid_columns=board.grid_columns or 5,
                board_checksum_sha256=restored_source.geometry_checksum_sha256,
                action=GEOMETRY_REVERTED_ACTION,
                previous_approved_geometry_revision=approved_before,
                # NOT NULL column: a board restored without an approval
                # records the revision it wrote; the board row is the truth
                # and approval lookups never read ``geometry_reverted``.
                approved_geometry_revision=(
                    written_revision
                    if plan.approved_geometry_revision is None
                    else plan.approved_geometry_revision
                ),
                actor=actor,
                created_at=reverted_at,
            )
        )

        restored_approvals, suggestions = self._restore_cells(
            cells,
            plan=plan,
            rendered=rendered,
            state=state,
            written_revision=written_revision,
            actor=actor,
            reverted_at=reverted_at,
        )
        session.flush()
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
        moved = apply_board_repoint(session, game_id, evaluation.movable)
        session.flush()
        projection = SqlAlchemyBoardSearchProjectionRepository(session)
        projection.sync_review_items(
            (
                review_item_id,
                *(
                    decision.review_item_id
                    for decision in moved
                    if decision.review_item_id is not None
                ),
            )
        )
        projection.reconcile_sequence(game_id, correction.sequence_number)

        recompute = recompute_source_image_geometry_completeness(
            session, game_id, correction.source_image_id, actor=actor, now=reverted_at
        )
        if image_admission_blocks_revert(status_before, recompute.status):
            raise _blocked(RevertBlockingReason.IMAGE_ADMITTED)

        # The cells' symbols are input of the super game series again.
        record_super_game_input_change(session, game_id, source="geometry_correction_revert")
        SymbolCellReviewWriteThroughCoordinator(session).synchronize_after_cell_mutation(
            game_id=game_id
        )
        session.flush()

        snapshot: dict[str, object] = {
            "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
            "kind": GeometryCorrectionKind.BOARD_REVISION.value,
            "revertedGeometryRevision": correction.revision,
            "restoredFromGeometryRevision": plan.previous_revision,
            "writtenGeometryRevision": written_revision,
            "board": {
                "before": board_before,
                "after": self._json_row(_BOARD_JSON_SQL, parameters),
            },
            "cells": {
                "before": cells_before,
                "after": self._json_rows(_CELLS_JSON_SQL, parameters),
            },
            "updated": {"image_source_geometry_revisions": source_revision_before},
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
            "removedCellCount": 0,
            "restoredCellDecisionCount": len(cells),
            "restoredApprovalCount": restored_approvals,
            "pendingSuggestionCount": suggestions,
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
            kind=GeometryCorrectionKind.BOARD_REVISION.value,
            pending_geometry_id=None,
            recognized_board_id=board_id,
            review_item_id=review_item_id,
            reverted_geometry_revision=correction.revision,
            reverted_board_geometry_revision_id=correction.revision_id,
            reverted_source_geometry_revision_id=evaluation.reverted_source.id,
            restored_source_geometry_revision_id=restored_source.id,
            restored_geometry_revision=written_revision,
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

    def _restore_cells(
        self,
        cells: Sequence[ImageSymbolReviewCellModel],
        *,
        plan: _BoardRevisionPlan,
        rendered: Mapping[int, str],
        state: ImageSymbolReviewStateModel | None,
        written_revision: int,
        actor: str,
        reverted_at: datetime,
    ) -> tuple[int, int]:
        """Give every cell the restored render and its decision from before the correction.

        Returns the number of approvals that came back and of approvals that
        came back as pending suggestions (other pixels, D-462).
        """

        count_before = tuple(_CountedCellState.from_model(cell) for cell in cells)
        restored_approvals = 0
        suggestions = 0
        for cell in cells:
            event = plan.earliest_events[cell.id]
            entry = plan.manifest_cells[int(cell.cell_index)]
            previous_state = _CellPreviousState.from_model(cell)
            history = plan.histories[cell.id]
            # D-462 on the pixels the restored specification renders today.
            restored_pixels = rendered[int(cell.cell_index)]
            approved_pixels = history[6]
            decision = restore_cell_decision(
                PreviousCellDecision(
                    assigned_symbol_id=event.previous_assigned_symbol_id,
                    review_state=event.previous_review_state,
                    quality_issue=event.previous_quality_issue,
                    assignment_source=event.previous_assignment_source,
                    verification_outcome=event.previous_verification_outcome,
                    verified_symbol_id_v2=event.previous_verified_symbol_id_v2,
                ),
                approval_pixels_identical=approved_pixels == restored_pixels,
            )
            # The restored render (the previous revision's manifest entry).
            cell.asset_mode = "virtual_source"
            cell.source_geometry_revision_id = plan.restored_source.id
            cell.logical_cell_key = str(entry["logicalCellKeySha256"])
            cell.logical_cell_key_v2 = _optional_text(entry.get("logicalCellKeyV2Sha256"))
            cell.render_identity_v2_sha256 = _optional_text(entry.get("renderIdentityV2Sha256"))
            cell.render_spec_checksum_sha256 = str(entry["renderSpecChecksumSha256"])
            cell.rendered_pixel_checksum_sha256 = restored_pixels
            cell.extractor_version = plan.extractor_version
            cell.crop_sample_id = str(entry["cropSampleId"])
            cell.crop_relative_path = None
            cell.crop_checksum_sha256 = restored_pixels
            cell.geometry_revision = written_revision
            cell.cropper_version = plan.extractor_version
            # The decision from before the correction.
            cell.assigned_symbol_id = decision.assigned_symbol_id
            cell.review_state = decision.review_state
            cell.quality_issue = decision.quality_issue
            cell.assignment_source = decision.assignment_source
            if decision.approval_restored:
                restored_approvals += 1
                cell.approved_crop_sample_id = cell.crop_sample_id
                cell.approved_crop_checksum_sha256 = cell.crop_checksum_sha256
                cell.approved_geometry_revision = cell.geometry_revision
                cell.approved_asset_mode = cell.asset_mode
                cell.approved_source_geometry_revision_id = cell.source_geometry_revision_id
                cell.approved_render_spec_checksum_sha256 = cell.render_spec_checksum_sha256
                cell.approved_rendered_pixel_checksum_sha256 = cell.rendered_pixel_checksum_sha256
            else:
                if event.previous_review_state == "approved":
                    suggestions += 1
                (
                    cell.approved_crop_sample_id,
                    cell.approved_crop_checksum_sha256,
                    cell.approved_geometry_revision,
                    cell.approved_asset_mode,
                    cell.approved_source_geometry_revision_id,
                    cell.approved_render_spec_checksum_sha256,
                    cell.approved_rendered_pixel_checksum_sha256,
                ) = history
            if decision.verification_outcome is not None:
                cell.verification_outcome = decision.verification_outcome
                cell.verified_symbol_id_v2 = decision.verified_symbol_id_v2
            else:
                try:
                    verification = _verification_v2(
                        review_state=cell.review_state,
                        quality_issue=cell.quality_issue,
                        assigned_symbol_id=cell.assigned_symbol_id,
                        prediction_symbol_code=cell.prediction_symbol_code,
                        assignment_source=cell.assignment_source,
                    )
                except AdditiveVirtualGeometryContractError as error:
                    raise ImageReviewConflictError(error.code, str(error)) from error
                cell.verification_outcome = verification.outcome
                cell.verified_symbol_id_v2 = verification.verified_symbol_id
            cell.revision += 1
            cell.last_reviewed_by = actor
            cell.last_reviewed_at = reverted_at
            _append_symbol_cell_event(
                self._session,
                cell=cell,
                previous=previous_state,
                action=GEOMETRY_REVERTED_ACTION,
                actor=actor,
            )
        if state is not None and cells:
            _apply_count_deltas(
                state,
                before=count_before,
                after=tuple(_CountedCellState.from_model(cell) for cell in cells),
            )
        return restored_approvals, suggestions

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
                "transaction_actions": sorted(CORRECTION_TRANSACTION_CELL_ACTIONS),
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
        cells_changed = int(cell_facts.changed_cells) > 0 or int(event_facts.later_events) > 0
        pin_parameters = {
            "game_id": game_id,
            "board_id": board_id,
            "review_item_id": review_item_id,
        }
        board_plan: _BoardRevisionPlan | None = None
        plan_refusal: RevertBlockingReason | None = None
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
            pinned = bool(self._scalar(_PINNED_SQL, pin_parameters))
        else:
            # Case A (TASK-0946): the board, its item and its cells existed
            # before the correction. Its own transaction writes only the
            # geometry invalidation and the D-488 symbols; any other cell
            # event sharing its ``now()`` is a change this revert cannot undo.
            review_resolved = correction.review_status in _RESOLVED_REVIEW_STATUSES or bool(
                resolution.resolved_since
            )
            ownership = False
            cells_changed = cells_changed or int(event_facts.foreign_transaction_events) > 0
            # The board keeps its source image and slot: the gate status of
            # the image cannot change by the revert (checked again on write).
            image_after = image_status
            pinned = bool(
                self._scalar(
                    _PINNED_BOARD_REVISION_SQL,
                    {
                        **pin_parameters,
                        "transaction_at": transaction_at,
                        "revision": correction.revision,
                    },
                )
            )
            plan_result = self._board_revision_plan(game_id, correction, revisions)
            if isinstance(plan_result, _BoardRevisionPlan):
                board_plan = plan_result
            else:
                plan_refusal = plan_result
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
            cells_changed_after_correction=cells_changed,
            review_resolved=review_resolved,
            sequence_ownership_changed=ownership,
            image_status_before=image_status,
            image_status_after=image_after,
            pinned=pinned,
            reopened_resolution=(not slot and bool(resolution.reopened)),
            history_complete=plan_refusal is not RevertBlockingReason.HISTORY_INCOMPLETE,
            revert_supported=plan_refusal is not RevertBlockingReason.NOT_SUPPORTED,
        )
        return _Evaluation(
            facts=facts,
            reverted_source=reverted,
            restored_source=restored,
            movable=tuple(movable),
            cell_count=int(cell_facts.cell_count),
            board_plan=board_plan,
        )

    def _board_revision_plan(
        self,
        game_id: UUID,
        correction: _Correction,
        revisions: Sequence[_SourceRevision],
    ) -> _BoardRevisionPlan | RevertBlockingReason:
        """What a case-A revert restores, or why it cannot.

        Fail-closed, ``NOT_SUPPORTED``: a qualified (partial) geometry on
        either side, a previous revision without a stored virtual render, a
        cell without an event of the correction transaction or whose
        pre-correction render is not the restored one.
        ``HISTORY_INCOMPLETE``: the provenance of a cell approval or the time
        and actor of the restored board approval are not recorded; nothing
        is reconstructed from another render.
        """

        transaction_at = correction.transaction_at
        if transaction_at is None:
            return RevertBlockingReason.NOT_SUPPORTED
        board_id = correction.recognized_board_id
        state = self._read(
            _BOARD_REVISION_STATE_SQL,
            {
                "game_id": game_id,
                "board_id": board_id,
                "review_item_id": correction.review_item_id,
                "revision_id": correction.revision_id,
            },
        ).one_or_none()
        if (
            state is None
            or bool(state.board_qualified)
            or state.asset_mode != "virtual_source"
            or not isinstance(state.corrected_geometry, dict)
            or state.corrected_geometry.get("geometryQualification") is not None
            or len(state.previous_approved) != 1
        ):
            return RevertBlockingReason.NOT_SUPPORTED
        cell_count = int(state.grid_rows or 3) * int(state.grid_columns or 5)
        previous = self._read(
            _PREVIOUS_BOARD_REVISION_SQL,
            {"game_id": game_id, "board_id": board_id, "revision": correction.revision},
        ).one_or_none()
        snapshot = state.item_snapshot if isinstance(state.item_snapshot, dict) else {}
        if previous is None:
            # The imported geometry: the review item's immutable import
            # snapshot holds the board projection the correction replaced.
            previous_revision = 0
            geometry = snapshot.get("geometry")
            engine_name = snapshot.get("geometryEngineName")
            engine_version = snapshot.get("geometryEngineVersion")
            if (
                snapshot.get("assetMode") != "virtual_source"
                or not isinstance(geometry, dict)
                or not isinstance(engine_name, str)
                or not isinstance(engine_version, str)
                or not engine_name.strip()
                or not engine_version.strip()
            ):
                return RevertBlockingReason.NOT_SUPPORTED
            # Decided from the restored source slot below.
            corners_value: object = None
            render_spec_value: object = None
            expected_source_id: UUID | None = None
        else:
            previous_revision = int(previous.revision)
            geometry = previous.geometry
            # A revision written by a save or a legacy conversion carries the
            # manual engine; one written by an earlier revert carries the
            # engine of the geometry it restored (its audit, P0-5).
            engine_name, engine_version = self._revision_engine(
                game_id, board_id, previous_revision
            )
            corners_value = previous.corners
            render_spec_value = previous.virtual_render_spec
            expected_source_id = previous.source_geometry_revision_id
            if (
                previous.asset_mode != "virtual_source"
                or expected_source_id is None
                or not isinstance(geometry, dict)
            ):
                return RevertBlockingReason.NOT_SUPPORTED
        if not isinstance(geometry, dict) or geometry.get("geometryQualification") is not None:
            return RevertBlockingReason.NOT_SUPPORTED
        manifest = self._read(
            _RENDER_MANIFEST_SQL,
            {"game_id": game_id, "board_id": board_id, "revision": previous_revision},
        ).one_or_none()
        if manifest is None or not isinstance(manifest.cells, dict):
            return RevertBlockingReason.NOT_SUPPORTED
        if render_spec_value is None:
            render_spec_value = manifest.cells
        if not isinstance(render_spec_value, dict):
            return RevertBlockingReason.NOT_SUPPORTED
        render_spec = dict(render_spec_value)
        manifest_cells = _manifest_cells_by_index(render_spec)
        if (
            manifest_cells is None
            or set(manifest_cells) != set(range(cell_count))
            or render_spec != manifest.cells
            or (
                expected_source_id is not None
                and manifest.source_geometry_revision_id != expected_source_id
            )
        ):
            return RevertBlockingReason.NOT_SUPPORTED
        restored_source = next(
            (value for value in revisions if value.id == manifest.source_geometry_revision_id),
            None,
        )
        if restored_source is None or restored_source.status == REVERTED_SOURCE_GEOMETRY_STATUS:
            return RevertBlockingReason.NOT_SUPPORTED
        if corners_value is None:
            # The imported revision has no corners row: the quad the reviewer
            # proposes for it (its source slot, else the board projection).
            slot_entry = self._scalar(
                _SLOT_ENTRY_SQL,
                {
                    "game_id": game_id,
                    "id": restored_source.id,
                    "position": correction.position_index,
                },
            )
            corners_value = next(
                (
                    candidate[key]
                    for candidate in (
                        slot_entry if isinstance(slot_entry, dict) else {},
                        geometry,
                    )
                    for key in ("symbolGridQuad", "finalQuad", "sourceQuad", "quad")
                    if _valid_corners(candidate.get(key))
                ),
                None,
            )
        if not _valid_corners(corners_value):
            return RevertBlockingReason.NOT_SUPPORTED

        earliest = self._earliest_transaction_events(correction.review_item_id, transaction_at)
        cells = self._read(
            _CELLS_OF_ITEM_SQL,
            {
                "game_id": game_id,
                "review_item_id": correction.review_item_id,
                "board_id": board_id,
            },
        ).all()
        if cells:
            if [int(cell.cell_index) for cell in cells] != list(range(cell_count)):
                return RevertBlockingReason.NOT_SUPPORTED
            for cell in cells:
                event = earliest.get(cell.id)
                entry = manifest_cells[int(cell.cell_index)]
                if (
                    cell.asset_mode != "virtual_source"
                    or int(cell.geometry_revision) != correction.revision
                    or event is None
                    or event.action != "geometry_invalidated"
                    or event.geometry_revision != correction.revision
                    or event.previous_asset_mode != "virtual_source"
                    or event.previous_source_geometry_revision_id != restored_source.id
                    or event.previous_render_spec_checksum_sha256
                    != entry.get("renderSpecChecksumSha256")
                ):
                    return RevertBlockingReason.NOT_SUPPORTED
        if set(earliest) - {cell.id for cell in cells}:
            return RevertBlockingReason.NOT_SUPPORTED

        histories: dict[UUID, ApprovalHistory] = {}
        if cells:
            cell_events = self._cell_events_until(correction.review_item_id, transaction_at)
            for cell in cells:
                history = _approval_history(earliest[cell.id], cell, cell_events.get(cell.id, ()))
                if history is None:
                    return RevertBlockingReason.HISTORY_INCOMPLETE
                histories[cell.id] = history

        [correction_previous_approved] = state.previous_approved
        approved = restored_approved_geometry_revision(
            correction_previous_approved,
            restored_from_revision=previous_revision,
            written_revision=correction.revision + 1,
        )
        approved_at: datetime | None = None
        approved_by: str | None = None
        if correction_previous_approved is not None:
            metadata = self._approval_metadata(
                game_id, board_id, correction_previous_approved, correction.revision
            )
            if metadata is None:
                # When and by whom the restored approval was given is not
                # recorded: the board could not be restored exactly.
                return RevertBlockingReason.HISTORY_INCOMPLETE
            approved_at, approved_by = metadata
        return _BoardRevisionPlan(
            previous_revision=previous_revision,
            restored_source=restored_source,
            board_geometry=dict(geometry),
            corners=[
                {"x": float(point["x"]), "y": float(point["y"])}
                for point in cast(list[dict[str, Any]], corners_value)
            ],
            render_spec=render_spec,
            render_spec_checksum_sha256=sha256_canonical_json(render_spec),
            extractor_version=str(manifest.extractor_version),
            engine_name=str(engine_name),
            engine_version=str(engine_version),
            correction_previous_approved=correction_previous_approved,
            approved_geometry_revision=approved,
            approved_at=approved_at,
            approved_by=approved_by,
            manifest_cells=manifest_cells,
            earliest_events=earliest,
            histories=histories,
        )

    def _revision_engine(self, game_id: UUID, board_id: UUID, revision: int) -> tuple[str, str]:
        """Engine of the board projection a revision ``>= 1`` was written with."""

        for row in self._read(_BOARD_REVERT_AUDITS_SQL, {"game_id": game_id, "board_id": board_id}):
            after = row.board_after
            if row.restored_geometry_revision == revision and isinstance(after, dict):
                name = after.get("geometry_engine_name")
                version = after.get("geometry_engine_version")
                if isinstance(name, str) and isinstance(version, str):
                    return name, version
        return _MANUAL_ENGINE_NAME, _MANUAL_ENGINE_VERSION

    def _approval_metadata(
        self, game_id: UUID, board_id: UUID, approved: int, before_revision: int
    ) -> tuple[datetime, str] | None:
        """When and by whom the board approval ``approved`` was given.

        Sources, the newest record wins: an approving board geometry event
        (``approved``/``geometry_saved``/``backfilled``), or an earlier
        case-A revert whose restored board kept that approval with its
        original time and actor (its audit snapshot, P0-1). A revert's own
        time and actor are never an approval.
        """

        candidates: list[tuple[datetime, datetime, str]] = []
        event = self._read(
            _APPROVAL_EVENT_SQL,
            {
                "game_id": game_id,
                "board_id": board_id,
                "approved": approved,
                "revision": before_revision,
            },
        ).one_or_none()
        if event is not None:
            candidates.append((event.created_at, event.created_at, str(event.actor)))
        for row in self._read(_BOARD_REVERT_AUDITS_SQL, {"game_id": game_id, "board_id": board_id}):
            after = row.board_after
            if (
                row.restored_geometry_revision is None
                or int(row.restored_geometry_revision) >= before_revision
                or not isinstance(after, dict)
                or after.get("approved_geometry_revision") != approved
                or not isinstance(after.get("geometry_approved_at"), str)
                or not isinstance(after.get("geometry_approved_by"), str)
            ):
                continue
            candidates.append(
                (
                    row.created_at,
                    datetime.fromisoformat(str(after["geometry_approved_at"])),
                    str(after["geometry_approved_by"]),
                )
            )
        if not candidates:
            return None
        _recorded, approved_at, approved_by = max(candidates, key=lambda value: value[0])
        return approved_at, approved_by

    def _cell_events_until(
        self, review_item_id: UUID, transaction_at: datetime
    ) -> dict[UUID, tuple[ImageSymbolReviewEventModel, ...]]:
        """Every cell event of the item up to the correction, newest first."""

        events = self._session.scalars(
            select(ImageSymbolReviewEventModel)
            .where(
                ImageSymbolReviewEventModel.review_item_id == review_item_id,
                ImageSymbolReviewEventModel.created_at <= transaction_at,
            )
            .order_by(
                ImageSymbolReviewEventModel.created_at.desc(),
                ImageSymbolReviewEventModel.cell_revision.desc(),
                ImageSymbolReviewEventModel.id,
            )
        )
        by_cell: dict[UUID, list[ImageSymbolReviewEventModel]] = {}
        for event in events:
            by_cell.setdefault(event.cell_review_id, []).append(event)
        return {cell: tuple(values) for cell, values in by_cell.items()}

    def _earliest_transaction_events(
        self, review_item_id: UUID, transaction_at: datetime
    ) -> dict[UUID, ImageSymbolReviewEventModel]:
        """The first event of each cell inside the correction transaction.

        Z1 (verified, TASK-0946): every cell event of one transaction carries
        the same ``created_at`` (server ``now()``), so the timestamp selects
        the transaction but cannot order its events; the cell revision does
        (each event of a cell increments it).
        """

        events = self._session.scalars(
            select(ImageSymbolReviewEventModel)
            .where(
                # The session is bound to the game's store (no mapped game_id).
                ImageSymbolReviewEventModel.review_item_id == review_item_id,
                ImageSymbolReviewEventModel.created_at == transaction_at,
            )
            .order_by(
                ImageSymbolReviewEventModel.cell_review_id,
                ImageSymbolReviewEventModel.cell_revision,
                ImageSymbolReviewEventModel.id,
            )
        )
        earliest: dict[UUID, ImageSymbolReviewEventModel] = {}
        for event in events:
            earliest.setdefault(event.cell_review_id, event)
        return earliest

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


_BOARD_JSON_SQL: Final = (
    "SELECT to_jsonb(t) FROM recognized_boards t WHERE t.game_id = :game_id AND t.id = :board_id"
)
_CELLS_JSON_SQL: Final = (
    "SELECT to_jsonb(t) FROM image_symbol_review_cells t "
    "WHERE t.game_id = :game_id AND t.id = ANY (CAST(:cell_ids AS uuid[])) "
    "ORDER BY t.cell_index, t.id"
)
_MANIFEST_CELL_TEXT_KEYS: Final = (
    "cropSampleId",
    "logicalCellKeySha256",
    "renderSpecChecksumSha256",
    "renderedPixelChecksumSha256",
)

ApprovalHistory = tuple[
    str | None, str | None, int | None, str | None, UUID | None, str | None, str | None
]


def _manifest_cells_by_index(document: Mapping[str, Any]) -> dict[int, Mapping[str, Any]] | None:
    """Render manifest entries by cell index; ``None`` when one cannot restore a cell."""

    raw = document.get("cells")
    if not isinstance(raw, list):
        return None
    cells: dict[int, Mapping[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, Mapping):
            return None
        index = entry.get("cellIndex")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index in cells
            or not all(isinstance(entry.get(key), str) for key in _MANIFEST_CELL_TEXT_KEYS)
        ):
            return None
        cells[index] = entry
    return cells


def _valid_corners(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(point, Mapping)
            and all(
                isinstance(point.get(axis), int | float) and not isinstance(point.get(axis), bool)
                for axis in ("x", "y")
            )
            for point in value
        )
    )


def _with_rendered_pixels(
    document: Mapping[str, Any], rendered: Mapping[int, str]
) -> dict[str, Any]:
    """The render manifest document with each cell's current pixel checksum."""

    copy = dict(document)
    copy["cells"] = [
        {**entry, "renderedPixelChecksumSha256": rendered[int(entry["cellIndex"])]}
        for entry in document["cells"]
    ]
    return copy


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


_APPROVAL_COLUMNS: Final = (
    "approved_crop_sample_id",
    "approved_crop_checksum_sha256",
    "approved_geometry_revision",
    "approved_asset_mode",
    "approved_source_geometry_revision_id",
    "approved_render_spec_checksum_sha256",
    "approved_rendered_pixel_checksum_sha256",
)


def _complete(values: ApprovalHistory) -> bool:
    return all(value is not None for value in values)


def _approval_of(source: object, *, prefix: str = "") -> ApprovalHistory:
    return cast(
        ApprovalHistory,
        tuple(getattr(source, f"{prefix}{column}") for column in _APPROVAL_COLUMNS),
    )


def _approval_history(
    event: ImageSymbolReviewEventModel,
    cell: object,
    cell_events: Sequence[ImageSymbolReviewEventModel],
) -> ApprovalHistory | None:
    """The cell's approval columns from before the correction, or ``None``.

    The earliest correction event names the approval (sample, checksum,
    revision). Its full provenance comes, in this order, from that event
    (written since TASK-0946), from the cell itself while it still carries
    that approval, or from the newest earlier event that recorded the same
    approval with full provenance. Nothing is combined with the provenance of
    another render (audit P0-2): without such a record it is ``None``.
    """

    target = _approval_of(event, prefix="previous_")
    if target[0] is None:
        return (None, None, None, None, None, None, None)
    if _complete(target):
        return target
    identity = target[:3]
    current = _approval_of(cell)
    if current[:3] == identity and _complete(current):
        return current
    for candidate in cell_events:
        for recorded in (_approval_of(candidate), _approval_of(candidate, prefix="previous_")):
            if recorded[:3] == identity and _complete(recorded):
                return recorded
    return None


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
        restored_geometry_revision=audit.restored_geometry_revision,
        restored_cell_decision_count=int(snapshot.get("restoredCellDecisionCount", 0)),
    )


__all__ = ["SqlAlchemyGeometryCorrectionRevertRepository"]
