"""Read-only SQLAlchemy repository of the D-484 geometry completeness report.

The unit is the source image. Its expected boards are the
``active_board_slots`` of the newest ``image_source_geometry_revisions`` row
(the *current* revision); the state of each expected position comes from the
``recognized_boards`` row at that position and the revision that board points
to (see ``domain.image_geometry_completeness`` for the rules). Counters are
aggregated in SQL per image; the position-level query, which feeds the pure
classifier, only runs for one page of at most 100 images.

Nothing here writes: every statement is a ``SELECT`` (plus a transaction-local
``SET`` of the statement timeout for the low-quality signal).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_geometry_completeness import (
    MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
    GeometryImageCursor,
    GeometryImageState,
    GeometryPositionFacts,
    GeometryPositionState,
    LowQualityThresholds,
    Quad,
    classify_position,
    expected_sequence_number,
    extract_position_quad,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewError,
    ImageReviewNotFoundError,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import GameModel, JobModel

LOW_QUALITY_STATEMENT_TIMEOUT_MS = 10_000
_QUERY_CANCELED_SQLSTATE = "57014"

# Shared prefix of every statement: the images in scope, their current source
# revision and per-image board counts over the *expected* positions only (a
# board outside the current revision's slots never counts).
#
# A complete board is ``uncertain`` unless a human approved its current
# geometry (``approved_geometry_revision = geometry_revision``) or the source
# revision it points to is ``accepted``. A deferred position is a missing one
# with an open pending row; ``_DEFERRED_BY_REASON_SQL`` splits it out.
_IMAGE_STATES_CTE = """
WITH images AS (
  SELECT s.id, s.import_job_id, s.relative_path, s.status, s.oriented_width, s.oriented_height
  FROM source_images s
  WHERE s.game_id = :game_id{import_filter}
), current_revision AS (
  SELECT DISTINCT ON (r.source_image_id)
    r.source_image_id, r.id, r.revision, r.sequence_range_start, r.sequence_range_end,
    r.active_board_slots, r.oriented_width, r.oriented_height
  FROM image_source_geometry_revisions r
  JOIN images i ON i.id = r.source_image_id
  WHERE r.game_id = :game_id
  ORDER BY r.source_image_id, r.revision DESC
), board_counts AS (
  SELECT b.source_image_id,
    count(*) AS n_boards,
    count(*) FILTER (WHERE b.completeness_status = 'pending_partial') AS n_partial,
    count(*) FILTER (
      WHERE b.completeness_status = 'complete'
        AND NOT (b.approved_geometry_revision IS NOT NULL
                 AND b.approved_geometry_revision = b.geometry_revision)
        AND p.status IS DISTINCT FROM 'accepted'
    ) AS n_uncertain
  FROM recognized_boards b
  JOIN current_revision c
    ON c.source_image_id = b.source_image_id AND b.position_index = ANY (c.active_board_slots)
  LEFT JOIN image_source_geometry_revisions p
    ON p.game_id = b.game_id AND p.id = b.source_geometry_revision_id
  WHERE b.game_id = :game_id
  GROUP BY b.source_image_id
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
    CASE
      WHEN c.source_image_id IS NULL THEN 'no_source_geometry'
      WHEN cardinality(c.active_board_slots) > COALESCE(bc.n_boards, 0) THEN 'incomplete_missing'
      WHEN bc.n_partial > 0 THEN 'incomplete_partial'
      WHEN bc.n_uncertain > 0 THEN 'incomplete_uncertain'
      ELSE 'complete'
    END AS image_state
  FROM images i
  LEFT JOIN current_revision c ON c.source_image_id = i.id
  LEFT JOIN board_counts bc ON bc.source_image_id = i.id
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
  COALESCE(sum(n_uncertain), 0) AS uncertain_positions
FROM image_states
GROUP BY image_state, source_status
ORDER BY image_state, source_status
"""
)

_DEFERRED_BY_REASON_SQL = (
    _IMAGE_STATES_CTE
    + """
SELECT g.reason_code, count(*) AS positions
FROM image_board_geometry_pending g
JOIN current_revision c
  ON c.source_image_id = g.source_image_id AND g.position_index = ANY (c.active_board_slots)
WHERE g.game_id = :game_id
  AND g.status = 'pending'
  AND NOT EXISTS (
    SELECT 1 FROM recognized_boards b
    WHERE b.game_id = g.game_id
      AND b.source_image_id = g.source_image_id
      AND b.position_index = g.position_index
  )
GROUP BY g.reason_code
ORDER BY g.reason_code
"""
)

_LIST_SQL = (
    _IMAGE_STATES_CTE
    + """
SELECT id, import_job_id, relative_path, source_status, image_state, source_revision,
  sequence_range_start, sequence_range_end, expected_boards, oriented_width, oriented_height
FROM image_states
WHERE image_state <> 'complete'{state_filter}{cursor_filter}
ORDER BY relative_path, id
LIMIT :row_limit
"""
)

# Positions of the images on one page. ``geometry_entry`` is the entry of the
# revision the board was cut from (the grid the pipeline used), or of the
# current revision when the position has no board.
_POSITIONS_SQL = """
WITH current_revision AS (
  SELECT DISTINCT ON (r.source_image_id)
    r.source_image_id, r.sequence_range_start, r.active_board_slots, r.board_geometries
  FROM image_source_geometry_revisions r
  WHERE r.game_id = :game_id AND r.source_image_id = ANY (:image_ids)
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
  c.sequence_range_start
FROM current_revision c
CROSS JOIN LATERAL unnest(c.active_board_slots) AS slot(position_index)
LEFT JOIN recognized_boards b
  ON b.game_id = :game_id AND b.source_image_id = c.source_image_id
  AND b.position_index = slot.position_index
LEFT JOIN image_source_geometry_revisions p
  ON p.game_id = :game_id AND p.id = b.source_geometry_revision_id
LEFT JOIN pending g
  ON g.source_image_id = c.source_image_id AND g.position_index = slot.position_index
ORDER BY c.source_image_id, slot.position_index
"""

# One review item of any board of the image: the existing source-asset endpoint
# is keyed by a review item, and an image without a recognized board has none.
_PREVIEW_ITEMS_SQL = """
SELECT DISTINCT ON (b.source_image_id) b.source_image_id, ri.id AS review_item_id
FROM recognized_boards b
JOIN image_review_items ri ON ri.game_id = b.game_id AND ri.recognized_board_id = b.id
WHERE b.game_id = :game_id AND b.source_image_id = ANY (:image_ids)
ORDER BY b.source_image_id, (ri.status = 'superseded'), b.position_index, ri.id
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


@dataclass(frozen=True, slots=True)
class GeometryImageCounts:
    total: int
    complete: int
    incomplete_missing: int
    incomplete_partial: int
    incomplete_uncertain: int
    no_source_geometry: int

    @property
    def incomplete(self) -> int:
        return self.total - self.complete


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
class GeometryCompletenessReport:
    game_id: UUID
    import_job_id: UUID | None
    images: GeometryImageCounts
    expected_board_count: int
    positions: tuple[GeometryPositionCount, ...]
    source_statuses: tuple[GeometryImageSourceStatusCount, ...]
    computed_at: datetime


@dataclass(frozen=True, slots=True)
class GeometryImagePosition:
    position_index: int
    sequence_number: int
    state: GeometryPositionState
    reason_code: str | None
    recognized_board_id: UUID | None
    quad: Quad | None


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
    preview_review_item_id: UUID | None
    positions: tuple[GeometryImagePosition, ...]


@dataclass(frozen=True, slots=True)
class IncompleteGeometryImagePage:
    game_id: UUID
    import_job_id: UUID | None
    image_state: GeometryImageState | None
    images: tuple[IncompleteGeometryImage, ...]
    next_cursor: GeometryImageCursor | None


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
        expected = board_positions = partial = uncertain = 0
        for (
            state,
            source_status,
            images,
            expected_positions,
            boards,
            n_partial,
            n_uncertain,
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

        deferred_by_reason = [(str(reason), int(count)) for reason, count in deferred_rows]
        deferred_total = sum(count for _, count in deferred_by_reason)
        positions = [
            GeometryPositionCount(
                GeometryPositionState.OK, None, board_positions - partial - uncertain
            ),
            GeometryPositionCount(GeometryPositionState.UNCERTAIN, None, uncertain),
            GeometryPositionCount(GeometryPositionState.PARTIAL, None, partial),
            GeometryPositionCount(
                GeometryPositionState.MISSING,
                None,
                expected - board_positions - deferred_total,
            ),
            *(
                GeometryPositionCount(GeometryPositionState.DEFERRED, reason, count)
                for reason, count in deferred_by_reason
            ),
        ]
        total_images = sum(image_counter.values())
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
            ),
            expected_board_count=expected,
            positions=tuple(positions),
            source_statuses=tuple(source_statuses),
            computed_at=datetime.now(UTC),
        )

    def incomplete_images(
        self,
        game_id: UUID,
        *,
        import_job_id: UUID | None = None,
        image_state: GeometryImageState | None = None,
        after: GeometryImageCursor | None = None,
        limit: int = MAX_GEOMETRY_COMPLETENESS_PAGE_SIZE,
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
        if not self._bind(game_id, import_job_id):
            return None
        params = self._scope_params(game_id, import_job_id)
        params["row_limit"] = limit + 1
        state_filter = ""
        if image_state is not None:
            state_filter = " AND image_state = :image_state"
            params["image_state"] = image_state.value
        cursor_filter = ""
        if after is not None:
            cursor_filter = " AND (relative_path, id) > (:after_path, :after_id)"
            params["after_path"] = after.relative_path
            params["after_id"] = after.source_image_id
        rows = self._session.execute(
            text(
                _LIST_SQL.format(
                    import_filter=self._import_filter(import_job_id),
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
        preview_items = self._preview_review_items(game_id, image_ids)

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
                preview_review_item_id=preview_items.get(row[0]),
                positions=positions_by_image.get(row[0], ()),
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
                )
            )
        return {image_id: tuple(positions) for image_id, positions in grouped.items()}

    def _preview_review_items(self, game_id: UUID, image_ids: Sequence[UUID]) -> dict[UUID, UUID]:
        if not image_ids:
            return {}
        rows = self._session.execute(
            text(_PREVIEW_ITEMS_SQL), {"game_id": game_id, "image_ids": list(image_ids)}
        ).all()
        return {row[0]: row[1] for row in rows}


__all__ = [
    "LOW_QUALITY_STATEMENT_TIMEOUT_MS",
    "GeometryCompletenessReport",
    "GeometryImageCounts",
    "GeometryImagePosition",
    "GeometryImageSourceStatusCount",
    "GeometryPositionCount",
    "IncompleteGeometryImage",
    "IncompleteGeometryImagePage",
    "LowQualityBoard",
    "LowQualityBoardsReport",
    "SqlAlchemyImageGeometryCompletenessRepository",
]
