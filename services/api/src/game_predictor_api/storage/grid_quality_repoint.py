"""Positive evidence for an unchanged frozen target after a sibling manual save."""

import copy
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.storage.grid_quality_observations import geometry_approval_fence


def unchanged_frozen_target(
    session: Session,
    game: UUID,
    source: UUID,
    frozen: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    """Keep aggregate references strict unless the canonical writer proves publication."""
    current = geometry_approval_fence(target)
    if current == frozen:
        return True
    old, live = frozen.get("board") or {}, current["board"]
    start, end = old.get("source_geometry_revision_id"), live.get("source_geometry_revision_id")
    if not start or not end or start == end or old.get("geometry_revision") != 0:
        return False
    if live.get("geometry_revision") != 0 or not _equal_except_references(
        frozen, current, start, end
    ):
        return False
    previous = _revision(session, game, source, start)
    newest = _revision(session, game, source, end)
    if not previous or not newest:
        return False
    if previous["geometry_checksum_sha256"] != old.get("geometry_checksum_sha256"):
        return False
    if newest["geometry_checksum_sha256"] != live.get("geometry_checksum_sha256"):
        return False
    slot = _slot(previous, old["position_index"])
    if not slot or slot.get("sequenceNumber") != old["sequence_number"]:
        return False
    if not _same_source_and_slot(previous, newest, slot):
        return False
    if newest["geometry_source"] != "manual" or newest["engine_kind"] != "manual_v1":
        return False
    # The canonical writer's immutable revision and geometry_saved event
    # prove publication of this exact source/checksum by another target.
    # No universal cell-event requirement: withheld targets may have no cells.
    publication = (
        session.connection()
        .execute(
            text("""SELECT r.id FROM image_board_geometry_revisions r
        JOIN recognized_boards b ON b.game_id=r.game_id AND b.id=r.recognized_board_id
        JOIN image_board_geometry_review_events a ON a.game_id=r.game_id
          AND a.recognized_board_id=r.recognized_board_id AND a.review_item_id=r.review_item_id
          AND a.geometry_revision=r.revision AND a.action='geometry_saved'
          AND a.board_checksum_sha256=r.geometry_checksum_sha256 AND a.actor=r.corrected_by
        WHERE r.game_id=:game AND b.source_image_id=:source
          AND r.recognized_board_id<>CAST(:board AS uuid)
          AND r.source_geometry_revision_id=CAST(:revision AS uuid)
          AND r.geometry_checksum_sha256=:checksum AND r.corrected_by=:actor
          AND r.asset_mode='virtual_source' AND r.revision>0 LIMIT 1"""),
            {
                "game": game,
                "source": source,
                "board": old["id"],
                "revision": newest["id"],
                "checksum": newest["geometry_checksum_sha256"],
                "actor": newest["created_by"],
            },
        )
        .scalar_one_or_none()
    )
    return publication is not None


def _revision(session: Session, game: UUID, source: UUID, revision: str) -> dict[str, Any] | None:
    return (
        session.connection()
        .execute(
            text(
                "SELECT to_jsonb(g) FROM image_source_geometry_revisions g "
                "WHERE game_id=:game AND source_image_id=:source AND id=CAST(:id AS uuid)"
            ),
            {"game": game, "source": source, "id": revision},
        )
        .scalar_one_or_none()
    )


def _slot(revision: dict[str, Any], index: int) -> dict[str, Any] | None:
    return next(
        (slot for slot in revision["board_geometries"] if slot["positionIndex"] == index), None
    )


def _same_source_and_slot(old: dict[str, Any], new: dict[str, Any], slot: dict[str, Any]) -> bool:
    keys = (
        "game_id",
        "source_image_id",
        "source_checksum_sha256",
        "normalized_pixel_checksum_sha256",
        "oriented_width",
        "oriented_height",
        "coordinate_space",
        "normalization_adapter_version",
        "topology_rules_version_id",
        "sequence_range_start",
        "sequence_range_end",
        "active_board_slots",
        "topology_fingerprint_sha256",
        "sequence_attestation_schema_version",
        "sequence_attestation_checksum_sha256",
    )
    return (
        old["status"] != "reverted"
        and new["status"] != "reverted"
        and all(old.get(key) == new.get(key) for key in keys)
        and _slot(new, slot["positionIndex"]) == slot
    )


def _equal_except_references(
    old: dict[str, Any], current: dict[str, Any], start: str, end: str
) -> bool:
    normalized = copy.deepcopy(current)
    normalized["board"]["source_geometry_revision_id"] = start
    normalized["board"]["geometry_checksum_sha256"] = old["board"]["geometry_checksum_sha256"]
    for cell in normalized["cells"]:
        for key in ("source_geometry_revision_id", "approved_source_geometry_revision_id"):
            if cell.get(key) == end:
                cell[key] = start
    for render in normalized["renders"]:
        if render.get("source_geometry_revision_id") == end:
            render["source_geometry_revision_id"] = start
    return normalized == old
