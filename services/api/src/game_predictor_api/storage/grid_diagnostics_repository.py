"""Bounded read-only aggregates for the existing board coverage endpoint."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.application.grid_diagnostics import (
    GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD,
    GridDiagnostics,
)
from game_predictor_api.storage.image_geometry_completeness_repository import (
    SqlAlchemyImageGeometryCompletenessRepository,
)

_BOARDS_SQL = """
WITH review AS (
 SELECT ri.status, ri.sequence_number,
   ri.status IN ('pending', 'accepted', 'corrected')
     AND b.completeness_status = 'complete' AS qualifies,
   c.sequence_number IS NOT NULL AS canonical
 FROM image_review_items ri
 JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
 LEFT JOIN image_sequence_canonical c
   ON c.game_id = :game_id AND c.sequence_number = ri.sequence_number
 WHERE ri.game_id = :game_id
)
SELECT status, count(*) AS rows,
 count(DISTINCT sequence_number) FILTER (WHERE sequence_number BETWEEN 1 AND :expected)
   AS sequences,
 count(*) FILTER (WHERE qualifies AND sequence_number BETWEEN 1 AND :expected)
   AS qualifying_rows,
 count(DISTINCT sequence_number)
   FILTER (WHERE qualifies AND sequence_number BETWEEN 1 AND :expected) AS qualifying_sequences,
 count(DISTINCT sequence_number)
   FILTER (WHERE qualifies AND canonical AND sequence_number BETWEEN 1 AND :expected) AS overlap
FROM review GROUP BY status ORDER BY status
"""

_CELLS_SQL = """
WITH current_cells AS (
 SELECT c.review_item_id, c.source_visibility, c.assigned_symbol_id, c.quality_issue,
   c.review_state, c.prediction_confidence,
   c.source_available OR c.source_visibility = 'outside' AS visible
 FROM image_symbol_review_cells c
 JOIN recognized_boards b ON b.game_id = :game_id AND b.id = c.recognized_board_id
   AND b.geometry_revision = c.geometry_revision
 WHERE c.game_id = :game_id
   AND (c.source_available OR c.source_visibility = 'outside')
   AND c.review_item_id NOT IN (
     SELECT id FROM image_review_items
     WHERE game_id = :game_id AND status IN ('rejected', 'superseded')
   )
), cell_counts AS (
 SELECT count(*) FILTER (WHERE visible) AS total,
 count(*) FILTER (WHERE visible AND source_visibility IS DISTINCT FROM 'outside'
   AND (assigned_symbol_id IS NULL OR quality_issue IN ('grid_issue', 'unreadable')))
   AS unknown,
 count(*) FILTER (WHERE visible AND review_state = 'pending') AS pending,
 count(*) FILTER (WHERE visible AND review_state = 'approved') AS approved,
 count(*) FILTER (WHERE visible AND quality_issue = 'unreadable') AS unreadable,
 count(*) FILTER (WHERE visible AND source_visibility = 'outside') AS outside,
 count(*) FILTER (WHERE visible AND review_state = 'pending'
   AND prediction_confidence < :threshold) AS low_confidence,
 count(*) FILTER (WHERE visible AND review_state = 'pending' AND
   source_visibility IS DISTINCT FROM 'outside' AND
   (assigned_symbol_id IS NULL OR quality_issue IN ('grid_issue', 'unreadable')))
   AS unknown_pending,
 count(*) FILTER (WHERE visible AND review_state = 'pending'
   AND quality_issue = 'unreadable') AS unreadable_pending,
 count(*) FILTER (WHERE visible AND source_visibility IS DISTINCT FROM 'outside'
   AND (assigned_symbol_id IS NULL OR quality_issue IN ('grid_issue', 'unreadable'))
   AND review_state = 'pending' AND prediction_confidence < :threshold) AS unknown_low
 FROM current_cells
), flagged AS (
 SELECT DISTINCT c.review_item_id FROM image_symbol_review_cells c
 JOIN recognized_boards b ON b.game_id = :game_id AND b.id = c.recognized_board_id
 WHERE c.game_id = :game_id AND c.quality_issue = 'grid_issue'
   AND c.review_state = 'pending' AND c.geometry_revision = b.geometry_revision
), board_counts AS (
 SELECT count(*) FILTER (WHERE f.review_item_id IS NOT NULL) AS flagged,
 count(*) FILTER (WHERE b.completeness_status = 'complete'
   AND b.approved_geometry_revision IS DISTINCT FROM b.geometry_revision
   AND r.status IS DISTINCT FROM 'accepted') AS unconfirmed,
 count(*) FILTER (WHERE f.review_item_id IS NOT NULL AND b.completeness_status = 'complete'
   AND b.approved_geometry_revision IS DISTINCT FROM b.geometry_revision
   AND r.status IS DISTINCT FROM 'accepted') AS flagged_unconfirmed
 FROM image_review_items ri
 JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
 LEFT JOIN image_source_geometry_revisions r
   ON r.game_id = :game_id AND r.id = b.source_geometry_revision_id
 LEFT JOIN flagged f ON f.review_item_id = ri.id
 WHERE ri.game_id = :game_id AND ri.status IN ('pending', 'accepted', 'corrected')
)
SELECT * FROM cell_counts CROSS JOIN board_counts
"""

_SLOT_COVERAGE_SQL = """
WITH slots AS (
 SELECT p.sequence_number,
   EXISTS (SELECT 1 FROM image_sequence_canonical c
     WHERE c.game_id = :game_id AND c.sequence_number = p.sequence_number)
   OR EXISTS (SELECT 1 FROM image_review_items ri
     JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
     WHERE ri.game_id = :game_id AND ri.sequence_number = p.sequence_number
       AND ri.status IN ('pending', 'accepted', 'corrected')
       AND b.completeness_status = 'complete') AS added
 FROM image_board_geometry_pending p WHERE p.game_id = :game_id AND p.status = 'pending'
)
SELECT count(*) FILTER (WHERE sequence_number IS NULL) AS unnumbered,
 count(*) FILTER (WHERE sequence_number NOT BETWEEN 1 AND :expected) AS out_of_range,
 count(*) FILTER (WHERE sequence_number BETWEEN 1 AND :expected AND added) AS already_added,
 count(*) FILTER (WHERE sequence_number BETWEEN 1 AND :expected AND NOT added) AS missing_slots,
 count(DISTINCT sequence_number)
   FILTER (WHERE sequence_number BETWEEN 1 AND :expected AND NOT added) AS missing_unique_sequences
FROM slots
"""


def read_grid_diagnostics(
    session: Session,
    *,
    game_id: UUID,
    expected: int,
    canonical_sequences: int,
    missing_signals: dict[str, int],
    missing_intersections: dict[str, int],
) -> GridDiagnostics:
    """Caller binds the game before any SQL; no source or projection is mutated."""
    params = {
        "game_id": game_id,
        "expected": expected,
        "threshold": GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD,
    }
    reviews = session.execute(text(_BOARDS_SQL), params).mappings().all()
    # Distinct counts per status may overlap; calculate the union separately.
    qualifying_sequences = int(
        session.scalar(
            text("""
      SELECT count(DISTINCT ri.sequence_number) FROM image_review_items ri
      JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
      WHERE ri.game_id = :game_id AND ri.status IN ('pending', 'accepted', 'corrected')
        AND b.completeness_status = 'complete' AND ri.sequence_number BETWEEN 1 AND :expected
    """),
            params,
        )
        or 0
    )
    overlap = int(
        session.scalar(
            text("""
      SELECT count(DISTINCT ri.sequence_number) FROM image_review_items ri
      JOIN recognized_boards b ON b.game_id = :game_id AND b.id = ri.recognized_board_id
      JOIN image_sequence_canonical c
        ON c.game_id = :game_id AND c.sequence_number = ri.sequence_number
      WHERE ri.game_id = :game_id AND ri.status IN ('pending', 'accepted', 'corrected')
        AND b.completeness_status = 'complete' AND ri.sequence_number BETWEEN 1 AND :expected
    """),
            params,
        )
        or 0
    )
    slots = (
        session.execute(
            text("""
      SELECT status, reason_code, count(*) AS count FROM image_board_geometry_pending
      WHERE game_id = :game_id GROUP BY status, reason_code ORDER BY status, reason_code
    """),
            params,
        )
        .mappings()
        .all()
    )
    slot_statuses: dict[str, int] = {}
    slot_reasons: dict[str, int] = {}
    for row in slots:
        slot_statuses[row["status"]] = slot_statuses.get(row["status"], 0) + int(row["count"])
        if row["status"] == "pending":
            slot_reasons[row["reason_code"]] = int(row["count"])
    cells = session.execute(text(_CELLS_SQL), params).mappings().one()
    slot_coverage = session.execute(text(_SLOT_COVERAGE_SQL), params).mappings().one()
    geometry = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(game_id)
    assert geometry is not None
    qualifying_rows = sum(int(row["qualifying_rows"]) for row in reviews)
    positions: dict[str, int] = {}
    for position in geometry.positions:
        positions[position.state.value] = positions.get(position.state.value, 0) + position.count
    return GridDiagnostics(
        low_confidence_threshold=GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD,
        review_rows_by_status={row["status"]: int(row["rows"]) for row in reviews},
        review_sequences_by_status={row["status"]: int(row["sequences"]) for row in reviews},
        qualifying_review_rows=qualifying_rows,
        qualifying_review_sequences=qualifying_sequences,
        canonical_sequences=canonical_sequences,
        canonical_review_overlap=overlap,
        duplicate_qualifying_review_rows=qualifying_rows - qualifying_sequences,
        deferred_slots_by_status=slot_statuses,
        deferred_slots_by_reason=slot_reasons,
        deferred_slot_coverage={key: int(value) for key, value in slot_coverage.items()},
        flagged_grid_boards=int(cells["flagged"]),
        unconfirmed_geometry_boards=int(cells["unconfirmed"]),
        flagged_unconfirmed_boards=int(cells["flagged_unconfirmed"]),
        symbol_cells={
            key: int(cells[key])
            for key in (
                "total",
                "unknown",
                "pending",
                "approved",
                "unreadable",
                "outside",
                "low_confidence",
            )
        },
        symbol_cell_intersections={
            key: int(cells[key]) for key in ("unknown_pending", "unreadable_pending", "unknown_low")
        },
        missing_reason_signals=missing_signals,
        missing_reason_intersections=missing_intersections,
        source_images=asdict(geometry.images),
        source_positions=positions,
        source_gate={
            key: value for key, value in asdict(geometry.gate).items() if isinstance(value, int)
        }
        if geometry.gate is not None
        else {},
    )
