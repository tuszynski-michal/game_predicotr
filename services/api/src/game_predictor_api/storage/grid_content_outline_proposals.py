"""Read-only page of symbol outline proposals for boards with a human-approved grid (D-608)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from sqlalchemy import text

from game_predictor_api.domain.grid_cell_content import content_source_identity
from game_predictor_api.domain.grid_content_outline_proposals import (
    OUTLINE_PROPOSAL_VERSION,
    outline_proposal_cells,
)

if TYPE_CHECKING:
    from .grid_cell_content import SqlAlchemyGridCellContentRepository

OutlineView = Literal["todo", "approved", "all"]

# Same human-approval rule as the default grid-learning scope (D-606): the current
# geometry revision is approved by a person, not by a system or worker actor.
_CANDIDATES = """
WITH candidates AS (
  SELECT b.id AS board_id, b.position_index, b.sequence_number,
         b.board_geometry->'latticeNodes' AS nodes,
         s.id, s.checksum_sha256, s.normalized_pixel_checksum_sha256,
         s.oriented_width, s.oriented_height, s.coordinate_space,
         s.normalization_adapter_version, s.exif_orientation, s.created_at,
         coalesce(latest.revision, 0) AS content_revision,
         coalesce((latest.document->'reference'->>'humanApproved')::boolean, false)
           AS content_approved
  FROM recognized_boards b
  JOIN source_images s ON s.game_id = b.game_id AND s.id = b.source_image_id
  LEFT JOIN LATERAL (
    SELECT r.revision, r.document FROM grid_cell_content_revisions r
    WHERE r.game_id = b.game_id
      AND r.pixel_sha256 = s.normalized_pixel_checksum_sha256
      AND r.position_index = b.position_index
    ORDER BY r.revision DESC LIMIT 1
  ) latest ON true
  WHERE b.game_id = :game
    AND b.status <> 'rejected'
    AND b.sequence_number IS NOT NULL AND b.sequence_number > 0
    AND b.approved_geometry_revision = b.geometry_revision
    AND b.geometry_approved_by IS NOT NULL AND b.geometry_approved_at IS NOT NULL
    AND b.geometry_approved_by NOT LIKE 'system:%'
    AND b.geometry_approved_by NOT LIKE 'worker:%'
    AND coalesce(cardinality(b.unavailable_cell_indices), 0) = 0
    AND jsonb_typeof(b.board_geometry->'latticeNodes') = 'array'
    AND s.purged_at IS NULL
    AND s.normalized_pixel_checksum_sha256 IS NOT NULL
    AND public.source_replacement_source_current_v1(s.game_id, s.id, s.checksum_sha256)
)
"""


def list_outline_proposals(
    repo: SqlAlchemyGridCellContentRepository,
    game: UUID,
    view: OutlineView,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    session = repo.session
    repo.bind(game)
    counts = session.execute(
        text(
            _CANDIDATES + "SELECT count(*) FILTER (WHERE NOT content_approved) AS todo,"
            " count(*) FILTER (WHERE content_approved) AS approved FROM candidates"
        ),
        {"game": game},
    ).one()
    rows = (
        session.execute(
            text(
                _CANDIDATES
                + """SELECT * FROM candidates
                WHERE :view = 'all' OR content_approved = (:view = 'approved')
                ORDER BY created_at, id, position_index
                LIMIT :limit OFFSET :offset"""
            ),
            {"game": game, "view": view, "limit": limit + 1, "offset": offset},
        )
        .mappings()
        .all()
    )
    items = []
    for row in rows[:limit]:
        source = content_source_identity(dict(row))
        cells = outline_proposal_cells(row["nodes"], source.width, source.height)
        items.append(
            {
                "boardId": row["board_id"],
                "source": source,
                "positionIndex": row["position_index"],
                "sequenceNumber": row["sequence_number"],
                "contentRevision": row["content_revision"],
                "contentApproved": row["content_approved"],
                "cells": cells,
            }
        )
    return {
        "version": OUTLINE_PROPOSAL_VERSION,
        "gameId": game,
        "view": view,
        "counts": {"todo": counts.todo, "approved": counts.approved},
        "items": items,
        "offset": offset,
        "nextOffset": offset + limit if len(rows) > limit else None,
    }
