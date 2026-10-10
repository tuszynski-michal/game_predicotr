"""Read-only SQLAlchemy repository of the D-484 geometry completeness report.

Since TASK-0807 the report also carries the persisted gate state of each image
(``source_images.geometry_completeness_status`` and the operator exception),
written by ``storage.image_geometry_completeness_state_repository``; the list
can select the gate queue by that persisted status.

The unit is the source image. Its expected boards are the
``active_board_slots`` of the newest ``image_source_geometry_revisions`` row
that is not ``reverted`` (the *current* revision, TASK-0966); the state of each
expected position comes from the ``recognized_boards`` row at that position and
the revision that board points to (see ``domain.image_geometry_completeness``
for the rules). Counters are aggregated in SQL per image; the position-level
query, which feeds the pure classifier, only runs for one page of at most 100
images.

Nothing here writes: every statement is a ``SELECT`` (plus a transaction-local
``SET`` of the statement timeout for the low-quality signal).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_geometry_completeness import (
    INCOMPLETE_IMAGE_STATES,
    MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    REAL_GAP_IMAGE_STATES,
    SOURCE_IMAGE_GEOMETRY_INCOMPLETE,
    GeometryImageCursor,
    GeometryImageState,
    GeometryPositionFacts,
    GeometryPositionState,
    LowQualityThresholds,
    Quad,
    SourceImageGeometryStatus,
    classify_image,
    classify_position,
    expected_sequence_number,
    extract_position_quad,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.sequence_takeover import SKIPPED_OWNER_REASONS
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import GameModel, JobModel

LOW_QUALITY_STATEMENT_TIMEOUT_MS = 10_000
_QUERY_CANCELED_SQLSTATE = "57014"


def _sequence_live_elsewhere(sequence_number: str, image_id: str) -> str:
    """SQL predicate: the sequence number has a live review item on another image."""

    return f"""EXISTS (
      SELECT 1
      FROM image_review_items ri
      JOIN recognized_boards rb ON rb.game_id = ri.game_id AND rb.id = ri.recognized_board_id
      WHERE ri.game_id = :game_id
        AND ri.sequence_number = {sequence_number}
        AND ri.status IN ('pending', 'accepted', 'corrected')
        AND rb.source_image_id <> {image_id}
    )"""


# Shared prefix of every statement: the images in scope, their current source
# revision and per-image board counts over the *expected* positions only (a
# board outside the current revision's slots never counts).
#
# Only *live* boards count (``status <> 'rejected'``): a rejected board is no
# evidence of a correct grid (TASK-0808). A complete board is ``uncertain``
# unless a human approved its current geometry
# (``approved_geometry_revision = geometry_revision``) or the source revision
# it points to is ``accepted``.
#
# An expected position without a live board is a *gap*. A gap is
# ``superseded`` when its sequence number (``sequence_range_start`` + position)
# has a live review item on another image of the game; the lookup runs only for
# the gaps of images that miss boards, through the
# ``(game_id, sequence_number, status)`` index. A gap that is not superseded and
# has an open ``image_board_geometry_pending`` row is deferred
# (``_DEFERRED_BY_REASON_SQL`` splits it out), otherwise missing.
#
# An image is ``superseded`` when it has a source revision and all its expected
# positions are superseded gaps, or when it has no live board and another image
# of the game with the same ``checksum_sha256`` has live boards; it is
# ``import_failed`` when it has no live board and its import file failed (rules
# in ``domain.image_geometry_completeness.classify_image``).
_IMAGE_STATES_CTE = f"""
WITH images AS (
  SELECT s.id, s.import_job_id, s.relative_path, s.status, s.oriented_width, s.oriented_height,
    s.checksum_sha256, s.file_execution_key, s.geometry_completeness_status,
    s.geometry_completeness_evaluated_at, s.geometry_exception_reason, s.geometry_exception_by,
    s.geometry_exception_at
  FROM source_images s
  WHERE s.game_id = :game_id{{import_filter}}
), current_revision AS (
  SELECT DISTINCT ON (r.source_image_id)
    r.source_image_id, r.id, r.revision, r.sequence_range_start, r.sequence_range_end,
    r.active_board_slots, r.oriented_width, r.oriented_height
  FROM image_source_geometry_revisions r
  JOIN images i ON i.id = r.source_image_id
  WHERE r.game_id = :game_id AND r.status <> 'reverted'
  ORDER BY r.source_image_id, r.revision DESC
), board_counts AS (
  SELECT b.source_image_id,
    count(*) AS n_live,
    count(*) FILTER (WHERE b.position_index = ANY (c.active_board_slots)) AS n_boards,
    count(*) FILTER (
      WHERE b.position_index = ANY (c.active_board_slots)
        AND b.completeness_status = 'pending_partial'
    ) AS n_partial,
    count(*) FILTER (
      WHERE b.position_index = ANY (c.active_board_slots)
        AND b.completeness_status = 'complete'
        AND NOT (b.approved_geometry_revision IS NOT NULL
                 AND b.approved_geometry_revision = b.geometry_revision)
        AND p.status IS DISTINCT FROM 'accepted'
    ) AS n_uncertain
  FROM recognized_boards b
  JOIN images i ON i.id = b.source_image_id
  LEFT JOIN current_revision c ON c.source_image_id = b.source_image_id
  LEFT JOIN image_source_geometry_revisions p
    ON p.game_id = b.game_id AND p.id = b.source_geometry_revision_id
  WHERE b.game_id = :game_id AND b.status <> 'rejected'
  GROUP BY b.source_image_id
), gaps AS (
  SELECT c.source_image_id, slot.position_index,
    c.sequence_range_start + slot.position_index AS sequence_number
  FROM current_revision c
  LEFT JOIN board_counts bc ON bc.source_image_id = c.source_image_id
  CROSS JOIN LATERAL unnest(c.active_board_slots) AS slot(position_index)
  WHERE cardinality(c.active_board_slots) > COALESCE(bc.n_boards, 0)
    AND NOT EXISTS (
      SELECT 1 FROM recognized_boards b
      WHERE b.game_id = :game_id
        AND b.source_image_id = c.source_image_id
        AND b.position_index = slot.position_index
        AND b.status <> 'rejected'
    )
), gap_states AS (
  SELECT g.source_image_id, g.position_index,
    {_sequence_live_elsewhere("g.sequence_number", "g.source_image_id")} AS superseded
  FROM gaps g
), gap_counts AS (
  SELECT source_image_id, count(*) FILTER (WHERE superseded) AS n_superseded
  FROM gap_states
  GROUP BY source_image_id
), checksum_twins AS (
  SELECT DISTINCT i.id AS source_image_id
  FROM images i
  JOIN source_images t
    ON t.game_id = :game_id AND t.checksum_sha256 = i.checksum_sha256 AND t.id <> i.id
  WHERE NOT EXISTS (SELECT 1 FROM board_counts bc WHERE bc.source_image_id = i.id)
    AND EXISTS (
      SELECT 1 FROM recognized_boards b
      WHERE b.game_id = :game_id AND b.source_image_id = t.id AND b.status <> 'rejected'
    )
), failed_files AS (
  SELECT f.job_id, f.file_execution_key, f.error_code
  FROM image_import_job_files f
  WHERE f.game_id = :game_id AND f.workflow_status = 'failed'
), image_states AS (
  SELECT i.id, i.import_job_id, i.relative_path, i.status AS source_status,
    c.revision AS source_revision,
    c.sequence_range_start, c.sequence_range_end,
    cardinality(c.active_board_slots) AS expected_boards,
    COALESCE(c.oriented_width, i.oriented_width) AS oriented_width,
    COALESCE(c.oriented_height, i.oriented_height) AS oriented_height,
    COALESCE(bc.n_boards, 0) AS n_boards,
    COALESCE(bc.n_partial, 0) AS n_partial,
    COALESCE(bc.n_uncertain, 0) AS n_uncertain,
    COALESCE(gc.n_superseded, 0) AS n_superseded,
    ff.error_code AS import_error_code,
    i.geometry_completeness_status AS persisted_status,
    i.geometry_completeness_evaluated_at, i.geometry_exception_reason, i.geometry_exception_by,
    i.geometry_exception_at,
    CASE
      WHEN c.source_image_id IS NOT NULL
        AND COALESCE(gc.n_superseded, 0) = cardinality(c.active_board_slots) THEN 'superseded'
      WHEN bc.source_image_id IS NULL AND tw.source_image_id IS NOT NULL THEN 'superseded'
      WHEN bc.source_image_id IS NULL AND ff.error_code IS NOT NULL THEN 'import_failed'
      WHEN c.source_image_id IS NULL THEN 'no_source_geometry'
      WHEN cardinality(c.active_board_slots)
           > COALESCE(bc.n_boards, 0) + COALESCE(gc.n_superseded, 0) THEN 'incomplete_missing'
      WHEN bc.n_partial > 0 THEN 'incomplete_partial'
      WHEN bc.n_uncertain > 0 THEN 'incomplete_uncertain'
      ELSE 'complete'
    END AS image_state
  FROM images i
  LEFT JOIN current_revision c ON c.source_image_id = i.id
  LEFT JOIN board_counts bc ON bc.source_image_id = i.id
  LEFT JOIN gap_counts gc ON gc.source_image_id = i.id
  LEFT JOIN checksum_twins tw ON tw.source_image_id = i.id
  LEFT JOIN failed_files ff
    ON ff.job_id = i.import_job_id AND ff.file_execution_key = i.file_execution_key
)
"""

_REPORT_SQL = (
    _IMAGE_STATES_CTE
    + """
SELECT image_state, source_status,
  count(*) AS images,
  COALESCE(sum(expected_boards), 0) AS expected_positions,
  COALESCE(sum(n_boards), 0) AS board_positions,
  COALESCE(sum(n_partial), 0) AS partial_positions,
  COALESCE(sum(n_uncertain), 0) AS uncertain_positions,
  COALESCE(sum(n_superseded), 0) AS superseded_positions
FROM image_states
GROUP BY image_state, source_status
ORDER BY image_state, source_status
"""
)

_DEFERRED_SEQUENCE_LIVE_ELSEWHERE_SQL = _sequence_live_elsewhere(
    "c.sequence_range_start + g.position_index", "g.source_image_id"
)

# Open pending rows are few, so deferred positions are counted straight from
# them instead of through the per-image board aggregation of the shared prefix.
_DEFERRED_BY_REASON_SQL = f"""
SELECT g.reason_code, count(*) AS positions
FROM image_board_geometry_pending g
JOIN source_images s ON s.game_id = :game_id AND s.id = g.source_image_id{{import_filter}}
JOIN LATERAL (
  SELECT r.sequence_range_start, r.active_board_slots
  FROM image_source_geometry_revisions r
  WHERE r.game_id = :game_id AND r.source_image_id = g.source_image_id
    AND r.status <> 'reverted'
  ORDER BY r.revision DESC
  LIMIT 1
) c ON g.position_index = ANY (c.active_board_slots)
WHERE g.game_id = :game_id
  AND g.status = 'pending'
  AND NOT EXISTS (
    SELECT 1 FROM recognized_boards b
    WHERE b.game_id = g.game_id
      AND b.source_image_id = g.source_image_id
      AND b.position_index = g.position_index
      AND b.status <> 'rejected'
  )
  AND NOT {_DEFERRED_SEQUENCE_LIVE_ELSEWHERE_SQL}
GROUP BY g.reason_code
ORDER BY g.reason_code
"""

_LIST_SQL = (
    _IMAGE_STATES_CTE
    + """
SELECT id, import_job_id, relative_path, source_status, image_state, source_revision,
  sequence_range_start, sequence_range_end, expected_boards, oriented_width, oriented_height,
  import_error_code, persisted_status, geometry_completeness_evaluated_at,
  geometry_exception_reason, geometry_exception_by, geometry_exception_at
FROM image_states
WHERE {state_filter}{cursor_filter}
ORDER BY relative_path, id
LIMIT :row_limit
"""
)

_POSITION_SEQUENCE_LIVE_ELSEWHERE_SQL = _sequence_live_elsewhere(
    "c.sequence_range_start + slot.position_index", "c.source_image_id"
)

# Positions of the images on one page. ``geometry_entry`` is the entry of the
# revision the board was cut from (the grid the pipeline used), or of the
# current revision when the position has no live board. A rejected board is
# not a board here (TASK-0808).
_POSITIONS_SQL = f"""
WITH current_revision AS (
  SELECT DISTINCT ON (r.source_image_id)
    r.source_image_id, r.sequence_range_start, r.active_board_slots, r.board_geometries
  FROM image_source_geometry_revisions r
  WHERE r.game_id = :game_id AND r.source_image_id = ANY (:image_ids)
    AND r.status <> 'reverted'
  ORDER BY r.source_image_id, r.revision DESC
), pending AS (
  SELECT g.source_image_id, g.position_index, min(g.reason_code) AS reason_code
  FROM image_board_geometry_pending g
  WHERE g.game_id = :game_id AND g.status = 'pending' AND g.source_image_id = ANY (:image_ids)
  GROUP BY g.source_image_id, g.position_index
)
SELECT c.source_image_id, slot.position_index,
  b.id AS recognized_board_id,
  b.completeness_status,
  (b.approved_geometry_revision IS NOT NULL
   AND b.approved_geometry_revision = b.geometry_revision) AS geometry_approved,
  COALESCE(p.status = 'accepted', false) AS source_revision_accepted,
  g.reason_code AS deferred_reason_code,
  COALESCE(
    jsonb_path_query_first(
      p.board_geometries, '$[*] ? (@.positionIndex == $position)',
      jsonb_build_object('position', slot.position_index)),
    jsonb_path_query_first(
      c.board_geometries, '$[*] ? (@.positionIndex == $position)',
      jsonb_build_object('position', slot.position_index))
  ) AS geometry_entry,
  c.sequence_range_start,
  b.id IS NULL AND {_POSITION_SEQUENCE_LIVE_ELSEWHERE_SQL} AS sequence_live_elsewhere
FROM current_revision c
CROSS JOIN LATERAL unnest(c.active_board_slots) AS slot(position_index)
LEFT JOIN recognized_boards b
  ON b.game_id = :game_id AND b.source_image_id = c.source_image_id
  AND b.position_index = slot.position_index AND b.status <> 'rejected'
LEFT JOIN image_source_geometry_revisions p
  ON p.game_id = :game_id AND p.id = b.source_geometry_revision_id
LEFT JOIN pending g
  ON g.source_image_id = c.source_image_id AND g.position_index = slot.position_index
ORDER BY c.source_image_id, slot.position_index
"""

# Image-level facts of ``classify_image`` for a batch of images (TASK-0807).
# The checksum twin is looked up only for images without a live board, with
# one hash join per batch instead of one game-wide scan per image.
_IMAGE_FACTS_SQL = """
WITH batch AS (
  SELECT s.id, s.checksum_sha256, s.import_job_id, s.file_execution_key,
    EXISTS (
      SELECT 1 FROM image_source_geometry_revisions r
      WHERE r.game_id = :game_id AND r.source_image_id = s.id AND r.status <> 'reverted'
    ) AS has_source_geometry,
    EXISTS (
      SELECT 1 FROM recognized_boards b
      WHERE b.game_id = :game_id AND b.source_image_id = s.id AND b.status <> 'rejected'
    ) AS has_live_boards
  FROM source_images s
  WHERE s.game_id = :game_id AND s.id = ANY (:image_ids)
), twins AS (
  SELECT DISTINCT i.id
  FROM batch i
  JOIN source_images t
    ON t.game_id = :game_id AND t.checksum_sha256 = i.checksum_sha256 AND t.id <> i.id
  WHERE NOT i.has_live_boards
    AND EXISTS (
      SELECT 1 FROM recognized_boards b
      WHERE b.game_id = :game_id AND b.source_image_id = t.id AND b.status <> 'rejected'
    )
)
SELECT i.id, i.has_source_geometry, i.has_live_boards,
  tw.id IS NOT NULL AS checksum_twin_has_live_boards,
  NOT i.has_live_boards AND EXISTS (
    SELECT 1 FROM image_import_job_files f
    WHERE f.game_id = :game_id AND f.job_id = i.import_job_id
      AND f.file_execution_key = i.file_execution_key AND f.workflow_status = 'failed'
  ) AS import_file_failed
FROM batch i
LEFT JOIN twins tw ON tw.id = i.id
"""

# Persisted gate state (TASK-0807): images per status, evaluated or not.
_GATE_COUNTS_SQL = """
SELECT s.geometry_completeness_status, s.geometry_completeness_evaluated_at IS NOT NULL,
  count(*)
FROM source_images s
WHERE s.game_id = :game_id{import_filter}
GROUP BY 1, 2
"""

# Boards the gate withholds: live boards with an active review item and no
# symbol cell, on images that are incomplete or admitted by an exception (an
# admitted board of an exception image is cut when the exception is set).
_GATE_WITHHELD_BOARDS_SQL = """
SELECT count(*)
FROM source_images s
JOIN recognized_boards b
  ON b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected'
JOIN image_review_items ri
  ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
  AND ri.status IN ('pending', 'accepted', 'corrected')
WHERE s.game_id = :game_id{import_filter}
  AND s.geometry_completeness_status IN ('geometry_incomplete', 'geometry_exception')
  AND NOT EXISTS (
    SELECT 1 FROM image_symbol_review_cells c
    WHERE c.game_id = :game_id AND c.review_item_id = ri.id
  )
"""

_LOW_QUALITY_SQL = """
WITH low AS (
  SELECT c.recognized_board_id,
    count(*) AS low_cells,
    min(c.prediction_confidence) AS min_confidence
  FROM image_symbol_review_cells c
  WHERE c.game_id = :game_id{import_filter}
    AND c.review_state = 'pending'
    AND (c.source_available OR c.source_visibility = 'outside')
    AND c.prediction_confidence <= :max_confidence
  GROUP BY c.recognized_board_id
  HAVING count(*) >= :min_cells
)
SELECT low.recognized_board_id, low.low_cells, low.min_confidence,
  b.source_image_id, b.position_index, b.sequence_number,
  s.import_job_id, s.relative_path,
  count(*) OVER () AS total_boards
FROM low
JOIN recognized_boards b ON b.game_id = :game_id AND b.id = low.recognized_board_id
JOIN source_images s ON s.game_id = :game_id AND s.id = b.source_image_id
ORDER BY low.low_cells DESC, low.min_confidence, s.relative_path, b.position_index
LIMIT :row_limit
"""


MAX_IMPORT_SEQUENCE_NUMBERS: Final = 500

# D-543 (TASK-0971): sequences of one import that replaced a rejected owner of
# another image, and sequences this import skipped because another photo owns
# them (a live pending board kept, or a canonical owner - first save wins).
# Every relation is filtered by the constant ``:game_id`` so the plan prunes to
# the game's partitions (per-game isolation).
_REPLACED_SEQUENCES_SQL: Final = """
SELECT DISTINCT ri.sequence_number
FROM image_review_items ri
JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
WHERE ri.game_id = :game_id AND ri.import_job_id = :import_job_id
  AND ri.sequence_number IS NOT NULL
  AND ri.status IN ('pending', 'accepted', 'corrected')
  AND (
    EXISTS (
      SELECT 1
      FROM image_review_items old
      JOIN recognized_boards old_board
        ON old_board.game_id = :game_id AND old_board.id = old.recognized_board_id
      WHERE old.game_id = :game_id AND old.sequence_number = ri.sequence_number
        AND old.status = 'rejected' AND old_board.source_image_id <> b.source_image_id)
    OR EXISTS (
      SELECT 1
      FROM image_board_geometry_pending slot
      WHERE slot.game_id = :game_id AND slot.sequence_number = ri.sequence_number
        AND slot.rejected_at IS NOT NULL AND slot.status IN ('rejected', 'superseded')
        AND slot.source_image_id <> b.source_image_id))
ORDER BY ri.sequence_number
"""

_SKIPPED_SEQUENCES_SQL: Final = """
SELECT DISTINCT a.sequence_number
FROM image_sequence_alternatives a
WHERE a.game_id = :game_id AND a.import_job_id = :import_job_id
  AND a.reason = ANY (CAST(:reasons AS text[]))
ORDER BY a.sequence_number
"""


@dataclass(frozen=True, slots=True)
class GeometryImageCounts:
    total: int
    complete: int
    incomplete_missing: int
    incomplete_partial: int
    incomplete_uncertain: int
    no_source_geometry: int
    import_failed: int
    superseded: int

    @property
    def incomplete(self) -> int:
        # ``superseded`` images are covered by a newer import: not a gap.
        return self.total - self.complete - self.superseded


@dataclass(frozen=True, slots=True)
class GeometryImageSourceStatusCount:
    image_state: GeometryImageState
    source_status: str
    count: int


@dataclass(frozen=True, slots=True)
class GeometryPositionCount:
    state: GeometryPositionState
    reason_code: str | None
    count: int


@dataclass(frozen=True, slots=True)
class GeometryGateCounts:
    """Persisted gate state of the images in scope (TASK-0807).

    ``outside_gate`` images were evaluated and have no live board to cut
    (superseded, failed import, no source geometry); ``not_evaluated`` images
    still wait for the backfill. ``withheld_boards`` are not cut with the
    reason ``SOURCE_IMAGE_GEOMETRY_INCOMPLETE``.
    """

    geometry_complete: int
    geometry_incomplete: int
    geometry_exception: int
    outside_gate: int
    not_evaluated: int
    withheld_boards: int
    withheld_reason_code: str = SOURCE_IMAGE_GEOMETRY_INCOMPLETE


@dataclass(frozen=True, slots=True)
class ImportSequenceOwnership:
    """Sequence ownership outcome of one import (D-543, TASK-0971).

    ``replaced``: sequences whose live owner is a board of this import and
    that another image had rejected (a rejected review item or a rejected,
    later superseded, deferred slot) - the import replaced the rejected board.
    ``skipped``: sequences of this import recorded as alternatives because
    another photo owns them (a live pending board is kept, D-543, or a
    canonical owner wins, first save wins). The number lists
    are sorted and capped at ``MAX_IMPORT_SEQUENCE_NUMBERS``; the counts are
    exact.
    """

    replaced_count: int
    replaced_sequence_numbers: tuple[int, ...]
    skipped_count: int
    skipped_sequence_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class GeometryCompletenessReport:
    game_id: UUID
    import_job_id: UUID | None
    images: GeometryImageCounts
    expected_board_count: int
    positions: tuple[GeometryPositionCount, ...]
    source_statuses: tuple[GeometryImageSourceStatusCount, ...]
    computed_at: datetime
    gate: GeometryGateCounts | None = None
    # Only for the report of one import (``import_job_id`` set).
    sequence_ownership: ImportSequenceOwnership | None = None


@dataclass(frozen=True, slots=True)
class GeometryImagePosition:
    position_index: int
    sequence_number: int
    state: GeometryPositionState
    reason_code: str | None
    recognized_board_id: UUID | None
    quad: Quad | None
    # A human approved the board's current geometry (``approved_geometry_revision
    # == geometry_revision``); ``False`` without a live board (TASK-0961). A
    # ``partial`` position keeps its state after a manual qualification (D-449),
    # so this flag is the only sign that it was already handled.
    human_approved: bool = False


@dataclass(frozen=True, slots=True)
class IncompleteGeometryImage:
    source_image_id: UUID
    import_job_id: UUID
    relative_path: str
    source_status: str
    image_state: GeometryImageState
    source_revision: int | None
    sequence_range_start: int | None
    sequence_range_end: int | None
    expected_board_count: int | None
    oriented_width: int | None
    oriented_height: int | None
    # Error code of the failed import file of the image, if its file failed.
    import_error_code: str | None
    positions: tuple[GeometryImagePosition, ...]
    # Persisted gate state (TASK-0807); ``None`` = not evaluated / outside.
    completeness_status: SourceImageGeometryStatus | None = None
    completeness_evaluated_at: datetime | None = None
    exception_reason: str | None = None
    exception_by: str | None = None
    exception_at: datetime | None = None

    @property
    def gate_reason_code(self) -> str | None:
        if self.completeness_status is SourceImageGeometryStatus.GEOMETRY_INCOMPLETE:
            return SOURCE_IMAGE_GEOMETRY_INCOMPLETE
        return None


@dataclass(frozen=True, slots=True)
class IncompleteGeometryImagePage:
    game_id: UUID
    import_job_id: UUID | None
    image_state: GeometryImageState | None
    images: tuple[IncompleteGeometryImage, ...]
    next_cursor: GeometryImageCursor | None
    completeness_status: SourceImageGeometryStatus | None = None
    # The page lists only ``REAL_GAP_IMAGE_STATES`` (TASK-0961).
    gaps_only: bool = False


@dataclass(frozen=True, slots=True)
class GeometrySourceImageAsset:
    """Stored path and checksum of one source image (the file is served elsewhere)."""

    source_image_id: UUID
    relative_path: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class LowQualityBoard:
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    relative_path: str
    position_index: int
    sequence_number: int | None
    low_cell_count: int
    min_confidence: float


@dataclass(frozen=True, slots=True)
class LowQualityBoardsReport:
    game_id: UUID
    import_job_id: UUID | None
    max_confidence: float
    min_cells: int
    total_boards: int
    boards: tuple[LowQualityBoard, ...]
    computed_at: datetime


class SqlAlchemyImageGeometryCompletenessRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def completeness_report(
        self, game_id: UUID, *, import_job_id: UUID | None = None
    ) -> GeometryCompletenessReport | None:
        if not self._bind(game_id, import_job_id):
            return None
        params = self._scope_params(game_id, import_job_id)
        import_filter = self._import_filter(import_job_id)
        rows = self._session.execute(
            text(_REPORT_SQL.format(import_filter=import_filter)), params
        ).all()
        deferred_rows = self._session.execute(
            text(_DEFERRED_BY_REASON_SQL.format(import_filter=import_filter)), params
        ).all()

        image_counter: Counter[GeometryImageState] = Counter()
        source_statuses: list[GeometryImageSourceStatusCount] = []
        expected = board_positions = partial = uncertain = superseded = 0
        for (
            state,
            source_status,
            images,
            expected_positions,
            boards,
            n_partial,
            n_uncertain,
            n_superseded,
        ) in rows:
            image_state = GeometryImageState(state)
            image_counter[image_state] += int(images)
            source_statuses.append(
                GeometryImageSourceStatusCount(image_state, str(source_status), int(images))
            )
            expected += int(expected_positions)
            board_positions += int(boards)
            partial += int(n_partial)
            uncertain += int(n_uncertain)
            superseded += int(n_superseded)

        deferred_by_reason = [(str(reason), int(count)) for reason, count in deferred_rows]
        deferred_total = sum(count for _, count in deferred_by_reason)
        positions = [
            GeometryPositionCount(
                GeometryPositionState.OK, None, board_positions - partial - uncertain
            ),
            GeometryPositionCount(GeometryPositionState.UNCERTAIN, None, uncertain),
            GeometryPositionCount(GeometryPositionState.PARTIAL, None, partial),
            GeometryPositionCount(GeometryPositionState.SUPERSEDED, None, superseded),
            GeometryPositionCount(
                GeometryPositionState.MISSING,
                None,
                expected - board_positions - superseded - deferred_total,
            ),
            *(
                GeometryPositionCount(GeometryPositionState.DEFERRED, reason, count)
                for reason, count in deferred_by_reason
            ),
        ]
        total_images = sum(image_counter.values())
        gate = self._gate_counts(params, import_filter)
        return GeometryCompletenessReport(
            game_id=game_id,
            import_job_id=import_job_id,
            images=GeometryImageCounts(
                total=total_images,
                complete=image_counter[GeometryImageState.COMPLETE],
                incomplete_missing=image_counter[GeometryImageState.INCOMPLETE_MISSING],
                incomplete_partial=image_counter[GeometryImageState.INCOMPLETE_PARTIAL],
                incomplete_uncertain=image_counter[GeometryImageState.INCOMPLETE_UNCERTAIN],
                no_source_geometry=image_counter[GeometryImageState.NO_SOURCE_GEOMETRY],
                import_failed=image_counter[GeometryImageState.IMPORT_FAILED],
                superseded=image_counter[GeometryImageState.SUPERSEDED],
            ),
            expected_board_count=expected,
            positions=tuple(positions),
            source_statuses=tuple(source_statuses),
            computed_at=datetime.now(UTC),
            gate=gate,
            sequence_ownership=(
                None if import_job_id is None else self._sequence_ownership(game_id, import_job_id)
            ),
        )

    def _sequence_ownership(self, game_id: UUID, import_job_id: UUID) -> ImportSequenceOwnership:
        params = {"game_id": game_id, "import_job_id": import_job_id}
        replaced = [
            int(row[0]) for row in self._session.execute(text(_REPLACED_SEQUENCES_SQL), params)
        ]
        skipped = [
            int(row[0])
            for row in self._session.execute(
                text(_SKIPPED_SEQUENCES_SQL), {**params, "reasons": list(SKIPPED_OWNER_REASONS)}
            )
        ]
        return ImportSequenceOwnership(
            replaced_count=len(replaced),
            replaced_sequence_numbers=tuple(replaced[:MAX_IMPORT_SEQUENCE_NUMBERS]),
            skipped_count=len(skipped),
            skipped_sequence_numbers=tuple(skipped[:MAX_IMPORT_SEQUENCE_NUMBERS]),
        )

    def _gate_counts(self, params: dict[str, object], import_filter: str) -> GeometryGateCounts:
        counts: Counter[str] = Counter()
        not_evaluated = 0
        for status, evaluated, count in self._session.execute(
            text(_GATE_COUNTS_SQL.format(import_filter=import_filter)), params
        ):
            if not evaluated:
                not_evaluated += int(count)
            else:
                counts["null" if status is None else str(status)] += int(count)
        withheld = int(
            self._session.execute(
                text(_GATE_WITHHELD_BOARDS_SQL.format(import_filter=import_filter)), params
            ).scalar_one()
        )
        return GeometryGateCounts(
            geometry_complete=counts[SourceImageGeometryStatus.GEOMETRY_COMPLETE.value],
            geometry_incomplete=counts[SourceImageGeometryStatus.GEOMETRY_INCOMPLETE.value],
            geometry_exception=counts[SourceImageGeometryStatus.GEOMETRY_EXCEPTION.value],
            outside_gate=counts["null"],
            not_evaluated=not_evaluated,
            withheld_boards=withheld,
        )

    def incomplete_images(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        image_state: GeometryImageState | None = None,
        after: GeometryImageCursor | None = None,
        limit: int = MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
        completeness_status: SourceImageGeometryStatus | None = None,
        gaps_only: bool = False,
    ) -> IncompleteGeometryImagePage | None:
        if not 1 <= limit <= MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_LIMIT_INVALID",
                f"limit must be between 1 and {MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE}.",
            )
        if image_state is GeometryImageState.COMPLETE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_STATE_INVALID",
                "The incomplete image list cannot be filtered by the complete state.",
            )
        if completeness_status is SourceImageGeometryStatus.GEOMETRY_COMPLETE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_STATUS_INVALID",
                "The image queue cannot be filtered by the complete status.",
            )
        if gaps_only and (image_state is not None or completeness_status is not None):
            raise geometry_completeness_filter_conflict()
        if not self._bind(game_id, import_job_id):
            return None
        params = self._scope_params(game_id, import_job_id)
        params["row_limit"] = limit + 1
        import_filter = self._import_filter(import_job_id)
        # The default list is "all incomplete": complete and superseded images
        # are left out unless the superseded state is asked for explicitly.
        # ``gaps_only`` (TASK-0961) narrows it to the real gaps, without the
        # unconfirmed automatic grids. The gate queue (TASK-0807) selects by
        # the persisted status instead; the classified state then only narrows
        # it further. State lists are built from enum values, never from input.
        if completeness_status is not None:
            import_filter += " AND s.geometry_completeness_status = :completeness_status"
            params["completeness_status"] = completeness_status.value
            state_filter = "true"
        elif gaps_only:
            state_filter = _state_in_sql(REAL_GAP_IMAGE_STATES)
        elif image_state is None:
            state_filter = _state_in_sql(INCOMPLETE_IMAGE_STATES)
        else:
            state_filter = "true"
        if image_state is not None:
            state_filter = "image_state = :image_state"
            params["image_state"] = image_state.value
        cursor_filter = ""
        if after is not None:
            cursor_filter = " AND (relative_path, id) > (:after_path, :after_id)"
            params["after_path"] = after.relative_path
            params["after_id"] = after.source_image_id
        rows = self._session.execute(
            text(
                _LIST_SQL.format(
                    import_filter=import_filter,
                    state_filter=state_filter,
                    cursor_filter=cursor_filter,
                )
            ),
            params,
        ).all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        image_ids = [row[0] for row in page_rows]
        positions_by_image = self._positions(game_id, image_ids)

        images = tuple(
            IncompleteGeometryImage(
                source_image_id=row[0],
                import_job_id=row[1],
                relative_path=str(row[2]),
                source_status=str(row[3]),
                image_state=GeometryImageState(row[4]),
                source_revision=None if row[5] is None else int(row[5]),
                sequence_range_start=None if row[6] is None else int(row[6]),
                sequence_range_end=None if row[7] is None else int(row[7]),
                expected_board_count=None if row[8] is None else int(row[8]),
                oriented_width=None if row[9] is None else int(row[9]),
                oriented_height=None if row[10] is None else int(row[10]),
                import_error_code=None if row[11] is None else str(row[11]),
                positions=positions_by_image.get(row[0], ()),
                completeness_status=(
                    None if row[12] is None else SourceImageGeometryStatus(str(row[12]))
                ),
                completeness_evaluated_at=row[13],
                exception_reason=None if row[14] is None else str(row[14]),
                exception_by=None if row[15] is None else str(row[15]),
                exception_at=row[16],
            )
            for row in page_rows
        )
        last = images[-1] if images else None
        return IncompleteGeometryImagePage(
            game_id=game_id,
            import_job_id=import_job_id,
            image_state=image_state,
            images=images,
            next_cursor=(
                GeometryImageCursor(last.relative_path, last.source_image_id)
                if has_more and last is not None
                else None
            ),
            completeness_status=completeness_status,
            gaps_only=gaps_only,
        )

    def source_image_asset(
        self, game_id: UUID, source_image_id: UUID
    ) -> GeometrySourceImageAsset | None:
        """Path and checksum of one source image of the game; ``None`` for an unknown game."""

        if not self._bind(game_id, None):
            return None
        row = self._session.execute(
            text(
                "SELECT s.relative_path, s.checksum_sha256 FROM source_images s "
                "WHERE s.game_id = :game_id AND s.id = :source_image_id"
            ),
            {"game_id": game_id, "source_image_id": source_image_id},
        ).first()
        if row is None:
            raise ImageReviewNotFoundError(
                "IMAGE_GEOMETRY_COMPLETENESS_SOURCE_IMAGE_NOT_FOUND",
                "The selected source image does not belong to this game.",
            )
        return GeometrySourceImageAsset(
            source_image_id=source_image_id,
            relative_path=str(row[0]),
            checksum_sha256=str(row[1]),
        )

    def low_quality_boards(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        thresholds: LowQualityThresholds,
        limit: int = MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    ) -> LowQualityBoardsReport | None:
        if not 1 <= limit <= MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE:
            raise ImageReviewError(
                "IMAGE_GEOMETRY_COMPLETENESS_LIMIT_INVALID",
                f"limit must be between 1 and {MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE}.",
            )
        if not self._bind(game_id, import_job_id):
            return None
        # The cell table has millions of rows: bound the query and fail loudly
        # instead of returning an empty (and therefore misleading) result.
        self._session.execute(
            text(f"SET LOCAL statement_timeout = {LOW_QUALITY_STATEMENT_TIMEOUT_MS}")
        )
        params = self._scope_params(game_id, import_job_id)
        params.update(
            max_confidence=thresholds.max_confidence,
            min_cells=thresholds.min_cells,
            row_limit=limit,
        )
        try:
            rows = self._session.execute(
                text(
                    _LOW_QUALITY_SQL.format(
                        import_filter=(
                            "" if import_job_id is None else " AND c.import_job_id = :import_job_id"
                        )
                    )
                ),
                params,
            ).all()
        except OperationalError as error:
            if getattr(error.orig, "sqlstate", None) == _QUERY_CANCELED_SQLSTATE:
                raise ImageReviewConflictError(
                    "IMAGE_GEOMETRY_LOW_QUALITY_TIMEOUT",
                    "The low-quality symbol query exceeded its time limit. "
                    "Narrow it to one import.",
                    details={"timeoutMs": LOW_QUALITY_STATEMENT_TIMEOUT_MS},
                ) from error
            raise
        return LowQualityBoardsReport(
            game_id=game_id,
            import_job_id=import_job_id,
            max_confidence=thresholds.max_confidence,
            min_cells=thresholds.min_cells,
            total_boards=int(rows[0][8]) if rows else 0,
            boards=tuple(
                LowQualityBoard(
                    recognized_board_id=row[0],
                    low_cell_count=int(row[1]),
                    min_confidence=float(row[2]),
                    source_image_id=row[3],
                    position_index=int(row[4]),
                    sequence_number=None if row[5] is None else int(row[5]),
                    import_job_id=row[6],
                    relative_path=str(row[7]),
                )
                for row in rows
            ),
            computed_at=datetime.now(UTC),
        )

    def _bind(self, game_id: UUID, import_job_id: UUID | None) -> bool:
        """Route the session to the game's store; ``False`` for an unknown game.

        ``games``/``jobs`` live in ``public``; every other table is game-owned
        and reachable only after the router binds the transaction (the
        ``/admin/image-review-items`` routes sit outside ``/admin/games/{id}``,
        so no middleware does it).
        """

        if self._session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is None:
            return False
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        if import_job_id is not None:
            owner = self._session.scalar(
                select(JobModel.game_id).where(JobModel.id == import_job_id)
            )
            if owner != game_id:
                raise ImageReviewNotFoundError(
                    "IMAGE_GEOMETRY_COMPLETENESS_IMPORT_NOT_FOUND",
                    "The selected import does not belong to this game.",
                )
        return True

    @staticmethod
    def _scope_params(game_id: UUID, import_job_id: UUID | None) -> dict[str, object]:
        params: dict[str, object] = {"game_id": game_id}
        if import_job_id is not None:
            params["import_job_id"] = import_job_id
        return params

    @staticmethod
    def _import_filter(import_job_id: UUID | None) -> str:
        return "" if import_job_id is None else " AND s.import_job_id = :import_job_id"

    def _positions(
        self, game_id: UUID, image_ids: Sequence[UUID]
    ) -> dict[UUID, tuple[GeometryImagePosition, ...]]:
        if not image_ids:
            return {}
        rows = self._session.execute(
            text(_POSITIONS_SQL), {"game_id": game_id, "image_ids": list(image_ids)}
        ).all()
        grouped: dict[UUID, list[GeometryImagePosition]] = {}
        for row in rows:
            image_id = row[0]
            position_index = int(row[1])
            classification = classify_position(
                GeometryPositionFacts(
                    position_index=position_index,
                    board_exists=row[2] is not None,
                    completeness_status=None if row[3] is None else str(row[3]),
                    geometry_approved=bool(row[4]),
                    source_revision_accepted=bool(row[5]),
                    deferred_reason_code=None if row[6] is None else str(row[6]),
                    sequence_live_elsewhere=bool(row[9]),
                )
            )
            grouped.setdefault(image_id, []).append(
                GeometryImagePosition(
                    position_index=position_index,
                    sequence_number=expected_sequence_number(int(row[8]), position_index),
                    state=classification.state,
                    reason_code=classification.reason_code,
                    recognized_board_id=row[2],
                    quad=extract_position_quad(row[7] if isinstance(row[7], dict) else None),
                    # The same ``geometry_approved`` fact the classifier read.
                    human_approved=bool(row[4]),
                )
            )
        return {image_id: tuple(positions) for image_id, positions in grouped.items()}


def _state_in_sql(states: Sequence[GeometryImageState]) -> str:
    """``image_state IN (...)`` over enum values (never request input)."""

    return "image_state IN (" + ", ".join(f"'{state.value}'" for state in states) + ")"


def geometry_completeness_filter_conflict() -> ImageReviewError:
    return ImageReviewError(
        "IMAGE_GEOMETRY_COMPLETENESS_FILTER_CONFLICT",
        "gapsOnly cannot be combined with imageState or completenessStatus.",
    )


def classify_source_images(
    session: Session,
    game_id: UUID,
    image_ids: Sequence[UUID],
    *,
    accepted_board_overrides: Mapping[UUID, bool] | None = None,
) -> dict[UUID, GeometryImageState]:
    """Classify a batch of images with the domain classifier (TASK-0807).

    The single source of the D-484 definition: the same position facts as the
    list (``_POSITIONS_SQL``) and the image facts of ``classify_image``. The
    caller has bound the session to ``game_id``. ``accepted_board_overrides``
    replaces ``source_revision_accepted`` of the given boards; the read-only
    backfill preview uses it to classify as if a re-pointing had happened.
    Unknown ids are absent from the result.
    """

    if not image_ids:
        return {}
    ids = list(dict.fromkeys(image_ids))
    overrides = accepted_board_overrides or {}
    # Connection-level execution: the session's textual-SQL event would treat
    # these reads as writes, which a read-only preview transaction refuses.
    connection = session.connection()
    position_rows = connection.execute(
        text(_POSITIONS_SQL), {"game_id": game_id, "image_ids": ids}
    ).all()
    states_by_image: dict[UUID, list[GeometryPositionState]] = {}
    for row in position_rows:
        board_id = row[2]
        accepted = bool(row[5])
        if board_id is not None and board_id in overrides:
            accepted = overrides[board_id]
        states_by_image.setdefault(row[0], []).append(
            classify_position(
                GeometryPositionFacts(
                    position_index=int(row[1]),
                    board_exists=board_id is not None,
                    completeness_status=None if row[3] is None else str(row[3]),
                    geometry_approved=bool(row[4]),
                    source_revision_accepted=accepted,
                    deferred_reason_code=None if row[6] is None else str(row[6]),
                    sequence_live_elsewhere=bool(row[9]),
                )
            ).state
        )
    result: dict[UUID, GeometryImageState] = {}
    for image_id, has_source_geometry, has_live, twin, failed in connection.execute(
        text(_IMAGE_FACTS_SQL), {"game_id": game_id, "image_ids": ids}
    ):
        result[image_id] = classify_image(
            states_by_image.get(image_id, ()),
            has_source_geometry=bool(has_source_geometry),
            has_live_boards=bool(has_live),
            checksum_twin_has_live_boards=bool(twin),
            import_file_failed=bool(failed),
        )
    return result


__all__ = [
    "LOW_QUALITY_STATEMENT_TIMEOUT_MS",
    "MAX_IMPORT_SEQUENCE_NUMBERS",
    "GeometryCompletenessReport",
    "GeometryGateCounts",
    "GeometryImageCounts",
    "GeometryImagePosition",
    "GeometryImageSourceStatusCount",
    "GeometryPositionCount",
    "GeometrySourceImageAsset",
    "ImportSequenceOwnership",
    "IncompleteGeometryImage",
    "IncompleteGeometryImagePage",
    "LowQualityBoard",
    "LowQualityBoardsReport",
    "SqlAlchemyImageGeometryCompletenessRepository",
    "classify_source_images",
    "geometry_completeness_filter_conflict",
]
