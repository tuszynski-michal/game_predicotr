"""Grid-audit proposals: an immutable list of boards with a network grid to correct.

TASK-0840. A silent-grid audit (TASK-0831) compared every saved board grid with
the ``neural_grid`` network and the operator chose the boards whose saved grid is
wrong. The import command writes those boards, in worklist order, into one
checksum-bound artifact under the API artifact root, with the network grid of
each board as a proposal. Nothing about the queue is stored in the database: its
state is derived from the current geometry revision of each board, so a board
leaves the queue as soon as any geometry save gives it a newer revision.

All coordinates are ``exif-normalized-rgb-pixels-v1`` pixels of the source image,
the space of the stored board geometry and of the correction editor.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal
from uuid import UUID

from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError

GRID_AUDIT_PROPOSALS_SCHEMA = "grid-audit-proposals-v1"
GRID_AUDIT_PROPOSALS_MANIFEST_SCHEMA = "grid-audit-proposals-manifest-v1"
GRID_AUDIT_COORDINATE_SPACE: Final[Literal["exif-normalized-rgb-pixels-v1"]] = (
    "exif-normalized-rgb-pixels-v1"
)
GRID_AUDIT_PROVENANCE: Final[Literal["audit-network-proposal"]] = "audit-network-proposal"
# 6 x 4 lattice nodes of a 5 x 3 board, row-major; the outer corners in the
# editor's winding (top-left, top-right, bottom-right, bottom-left).
GRID_AUDIT_NODE_COUNT = 24
GRID_AUDIT_CORNER_NODES = (0, 5, 23, 18)


class GridAuditProposalError(ImageGridReviewError):
    """Stable failure of the audit proposal artifact or one of its items."""


class GridAuditImportStatus(StrEnum):
    """Result of the read-only verification at import time."""

    PROPOSAL = "proposal"
    # The board's geometry revision changed between the audit and the import.
    STALE = "stale"
    # The board is no longer a current board with a review item.
    BOARD_MISSING = "board_missing"
    # The network found no grid for the board (no proposal to offer).
    NO_NETWORK_GRID = "no_network_grid"


class GridAuditQueueStatus(StrEnum):
    """State of one item now, derived from the current board."""

    OPEN = "open"
    # A newer geometry revision exists: the board was corrected (by any path).
    CORRECTED = "corrected"
    # The board changed after the audit (at import or now): no stale proposal.
    STALE = "stale"
    # The board is gone or has no current review item.
    REMOVED = "removed"
    NO_PROPOSAL = "no_proposal"


@dataclass(frozen=True, slots=True)
class GridAuditPoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class GridAuditProposalGrid:
    corners: tuple[GridAuditPoint, GridAuditPoint, GridAuditPoint, GridAuditPoint]
    nodes: tuple[GridAuditPoint, ...]


@dataclass(frozen=True, slots=True)
class GridAuditProposalItem:
    ordinal: int
    item_id: str
    verdict_source: str
    audit_class: str
    level: str | None
    human_decided_cells: int
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    sequence_number: int
    position_index: int
    audit_geometry_revision: int
    import_geometry_revision: int | None
    import_status: GridAuditImportStatus
    proposal: GridAuditProposalGrid | None


@dataclass(frozen=True, slots=True)
class GridAuditProposalArtifact:
    audit_id: str
    game_id: UUID
    created_at: str
    sha256: str
    items: tuple[GridAuditProposalItem, ...]

    def item(self, item_id: str) -> GridAuditProposalItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise GridAuditProposalError(
            "GRID_AUDIT_PROPOSAL_ITEM_NOT_FOUND",
            "The audit proposal list has no such item.",
        )


@dataclass(frozen=True, slots=True)
class GridAuditBoardState:
    """The current state of one audited board (read from the database)."""

    recognized_board_id: UUID
    geometry_revision: int
    current_review_item: bool


def derive_grid_audit_queue_status(
    item: GridAuditProposalItem, board: GridAuditBoardState | None
) -> GridAuditQueueStatus:
    """Open only while the board still has exactly the audited geometry revision.

    A board whose revision differs from the audit's never gets the proposal: the
    network grid was compared with a geometry that no longer exists.
    """

    if item.import_status is GridAuditImportStatus.BOARD_MISSING:
        return GridAuditQueueStatus.REMOVED
    if item.import_status is GridAuditImportStatus.STALE:
        # Changed between the audit and the import: never offered, never
        # counted as corrected from this list.
        return GridAuditQueueStatus.STALE
    if board is None or not board.current_review_item:
        return GridAuditQueueStatus.REMOVED
    if board.geometry_revision > item.audit_geometry_revision:
        return GridAuditQueueStatus.CORRECTED
    if board.geometry_revision != item.audit_geometry_revision:
        return GridAuditQueueStatus.STALE
    if item.import_status is not GridAuditImportStatus.PROPOSAL or item.proposal is None:
        return GridAuditQueueStatus.NO_PROPOSAL
    return GridAuditQueueStatus.OPEN


def proposal_grid_from_nodes(nodes: Sequence[Sequence[float]]) -> GridAuditProposalGrid:
    """The four outer corners (rounded to pixels) of 24 network lattice nodes."""

    points = tuple(_point(node) for node in nodes)
    if len(points) != GRID_AUDIT_NODE_COUNT:
        raise GridAuditProposalError(
            "GRID_AUDIT_PROPOSALS_INVALID",
            "A network grid must have exactly 24 lattice nodes.",
        )
    corners = tuple(
        GridAuditPoint(x=float(round(points[index].x)), y=float(round(points[index].y)))
        for index in GRID_AUDIT_CORNER_NODES
    )
    return GridAuditProposalGrid(
        corners=(corners[0], corners[1], corners[2], corners[3]),
        nodes=points,
    )


def parse_grid_audit_proposal_document(
    document: Mapping[str, Any], *, sha256: str
) -> GridAuditProposalArtifact:
    """Validate the artifact written by ``scripts/import_grid_audit_proposals.py``."""

    try:
        if document.get("schema") != GRID_AUDIT_PROPOSALS_SCHEMA:
            raise ValueError("schema")
        if document.get("coordinateSpace") != GRID_AUDIT_COORDINATE_SPACE:
            raise ValueError("coordinateSpace")
        items = tuple(_parse_item(raw) for raw in document["items"])
        artifact = GridAuditProposalArtifact(
            audit_id=_text(document["auditId"]),
            game_id=UUID(str(document["gameId"])),
            created_at=_text(document["createdAt"]),
            sha256=sha256,
            items=items,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise GridAuditProposalError(
            "GRID_AUDIT_PROPOSALS_INVALID",
            "The grid audit proposal artifact is malformed.",
        ) from error
    ordinals = [item.ordinal for item in items]
    if ordinals != list(range(len(items))) or len({item.item_id for item in items}) != len(items):
        raise GridAuditProposalError(
            "GRID_AUDIT_PROPOSALS_INVALID",
            "The grid audit proposal items must be ordered and unique.",
        )
    return artifact


def grid_audit_proposal_item_document(item: GridAuditProposalItem) -> dict[str, Any]:
    """The JSON form of one item (the inverse of the parser)."""

    return {
        "ordinal": item.ordinal,
        "itemId": item.item_id,
        "verdictSource": item.verdict_source,
        "auditClass": item.audit_class,
        "level": item.level,
        "humanDecidedCells": item.human_decided_cells,
        "recognizedBoardId": str(item.recognized_board_id),
        "sourceImageId": str(item.source_image_id),
        "importJobId": str(item.import_job_id),
        "sequenceNumber": item.sequence_number,
        "positionIndex": item.position_index,
        "auditGeometryRevision": item.audit_geometry_revision,
        "importGeometryRevision": item.import_geometry_revision,
        "importStatus": item.import_status.value,
        "proposal": None
        if item.proposal is None
        else {
            "corners": [{"x": point.x, "y": point.y} for point in item.proposal.corners],
            "nodes": [[point.x, point.y] for point in item.proposal.nodes],
        },
    }


def _parse_item(raw: Mapping[str, Any]) -> GridAuditProposalItem:
    status = GridAuditImportStatus(str(raw["importStatus"]))
    proposal_raw = raw.get("proposal")
    proposal = None
    if proposal_raw is not None:
        proposal = proposal_grid_from_nodes(proposal_raw["nodes"])
        stored = tuple(_point(point) for point in proposal_raw["corners"])
        if stored != proposal.corners:
            raise ValueError("proposal corners do not match the nodes")
    if (status is GridAuditImportStatus.PROPOSAL) != (proposal is not None):
        raise ValueError("only a verified item carries a proposal")
    import_revision = raw.get("importGeometryRevision")
    position = _integer(raw["positionIndex"])
    if not 0 <= position <= 8:
        raise ValueError("positionIndex")
    return GridAuditProposalItem(
        ordinal=_integer(raw["ordinal"]),
        item_id=_text(raw["itemId"]),
        verdict_source=_text(raw["verdictSource"]),
        audit_class=_text(raw["auditClass"]),
        level=None if raw.get("level") is None else _text(raw["level"]),
        human_decided_cells=_integer(raw["humanDecidedCells"]),
        recognized_board_id=UUID(str(raw["recognizedBoardId"])),
        source_image_id=UUID(str(raw["sourceImageId"])),
        import_job_id=UUID(str(raw["importJobId"])),
        sequence_number=_integer(raw["sequenceNumber"]),
        position_index=position,
        audit_geometry_revision=_integer(raw["auditGeometryRevision"]),
        import_geometry_revision=None if import_revision is None else _integer(import_revision),
        import_status=status,
        proposal=proposal,
    )


def _point(value: Any) -> GridAuditPoint:
    if isinstance(value, Mapping):
        x, y = value["x"], value["y"]
    else:
        x, y = value
    if isinstance(x, bool) or isinstance(y, bool):
        raise ValueError("point")
    point = GridAuditPoint(x=float(x), y=float(y))
    if not (math.isfinite(point.x) and math.isfinite(point.y)):
        raise ValueError("point")
    return point


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("integer")
    return int(value)


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("text")
    return str(value)


__all__ = [
    "GRID_AUDIT_COORDINATE_SPACE",
    "GRID_AUDIT_CORNER_NODES",
    "GRID_AUDIT_NODE_COUNT",
    "GRID_AUDIT_PROPOSALS_MANIFEST_SCHEMA",
    "GRID_AUDIT_PROPOSALS_SCHEMA",
    "GRID_AUDIT_PROVENANCE",
    "GridAuditBoardState",
    "GridAuditImportStatus",
    "GridAuditPoint",
    "GridAuditProposalArtifact",
    "GridAuditProposalError",
    "GridAuditProposalGrid",
    "GridAuditProposalItem",
    "GridAuditQueueStatus",
    "derive_grid_audit_queue_status",
    "grid_audit_proposal_item_document",
    "parse_grid_audit_proposal_document",
    "proposal_grid_from_nodes",
]
