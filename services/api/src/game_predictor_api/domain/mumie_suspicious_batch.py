"""Owner-approved, bounded exception for one immutable Mumie detector and grid."""

from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_cut_suspicion import (
    GRID_CUT_SUSPICION_THRESHOLD,
    assess_grid_cut,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewListItem
from game_predictor_api.domain.jobs import JobConflictError

GAME = UUID("246a1f54-eee8-49d5-b11a-0fde70e5eecd")
VERSION = UUID("9404ced0-f0b8-5095-9dda-afcf2123a76a")
MANIFEST = "a71fc03a0ab6ac9a8f36dac7830ddc434e43209d1efe13d19e6f6a0513abcb40"
BASE = UUID("6cc10344-1d69-5765-b8c8-423a0313984a")
FAMILY = UUID("79e6b4f3-b481-44dc-8e29-d5ed0e5c72bc")
REPORT = UUID("99e44024-fd3b-593d-9436-13c3d2839b7b")
RUNTIME = "mumie-suspicious-100-v1"
MAX_BOARDS = 100


def board_pin(item: ImageGridReviewListItem) -> dict[str, Any]:
    assert item.cut_suspicion is not None and item.review_item_id and item.recognized_board_id
    return {
        "review": str(item.review_item_id),
        "board": str(item.recognized_board_id),
        "source": str(item.source_image_id),
        "job": str(item.import_job_id),
        "sequence": item.sequence_number,
        "position": item.position_index,
        "revision": item.geometry_revision,
        "resolution": item.resolution_revision,
        "checksum": item.source_checksum_sha256,
        "score": item.cut_suspicion.score,
    }


def require_batch(game: UUID, command: dict[str, Any]) -> list[dict[str, Any]]:
    pins = command["suspiciousBatch"]
    if (
        game != GAME
        or command.get("modelVersionId") != str(VERSION)
        or command.get("executionScope") != "pilot"
        or command.get("selector") != {"categories": ["unconfirmed"]}
        or not isinstance(pins, list)
        or not 1 <= len(pins) <= MAX_BOARDS
    ):
        raise JobConflictError(
            "GRID_REINFERENCE_SUSPICIOUS_SCOPE", "Invalid game, model or batch scope."
        )
    if (
        len({p["review"] for p in pins}) != len(pins)
        or len({p["sequence"] for p in pins}) != len(pins)
        or pins != sorted(pins, key=lambda p: (-p["score"], p["sequence"]))
    ):
        raise JobConflictError(
            "GRID_REINFERENCE_SUSPICIOUS_SCOPE", "Invalid batch order or repeated board."
        )
    return pins


def matches_snapshot(pin: dict[str, Any], target: dict[str, Any]) -> bool:
    board, review = target["board"], target["review"]
    if board is None or review is None or target["kind"] != "automatic":
        return False
    suspicion = assess_grid_cut(board["board_geometry"].get("latticeNodes"))
    return (
        board["id"] == pin["board"]
        and review["id"] == pin["review"]
        and board["source_image_id"] == pin["source"]
        and review["import_job_id"] == pin["job"]
        and board["geometry_revision"] == pin["revision"]
        and review["resolution_revision"] == pin["resolution"]
        and target["positionIndex"] == pin["position"]
        and target["sequenceNumber"] == pin["sequence"]
        and board["approved_geometry_revision"] is None
        and board["asset_mode"] == "virtual_source"
        and board["completeness_status"] == "complete"
        and not board["unavailable_cell_indices"]
        and review["status"] == "pending"
        and all(not cell["quality_issue"] for cell in target["cells"])
        and suspicion is not None
        and suspicion.score == pin["score"]
        and suspicion.score > GRID_CUT_SUSPICION_THRESHOLD
    )
