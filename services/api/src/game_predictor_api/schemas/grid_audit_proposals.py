"""OpenAPI contracts of the read-only grid-audit proposal queue (TASK-0840)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.grid_audit_proposals import (
    GridAuditProposalView,
    GridAuditQueueEntry,
    GridAuditQueuePage,
)
from game_predictor_api.application.grid_audit_symbol_suggestions import GridAuditSymbolSuggestions
from game_predictor_api.domain.grid_audit_proposals import (
    GRID_AUDIT_COORDINATE_SPACE,
    GRID_AUDIT_PROVENANCE,
    GridAuditImportStatus,
    GridAuditProposalError,
    GridAuditQueueStatus,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.geometry_qualification import (
    GridCorrectionCellSymbolSuggestionResponse,
    ManualSourceGeometryPoint,
)
from game_predictor_api.schemas.image_grid_reviews import (
    ImageGridReviewGeometryPreviewCommand,
    ImageGridReviewItemResponse,
    to_image_grid_review_item_response,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class GridAuditQueueCountsResponse(ApiModel):
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    corrected: int = Field(ge=0)
    stale: int = Field(ge=0)
    removed: int = Field(ge=0)
    no_proposal: int = Field(ge=0)
    open_with_symbol_decisions: int = Field(ge=0)


class GridAuditQueueItemResponse(ApiModel):
    ordinal: int = Field(ge=0)
    item_id: str
    verdict_source: str
    audit_class: str
    level: str | None
    human_decided_cells: int = Field(ge=0)
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    sequence_number: int = Field(ge=0)
    position_index: int = Field(ge=0, le=8)
    audit_geometry_revision: int = Field(ge=0)
    current_geometry_revision: int | None = Field(default=None, ge=0)
    import_status: GridAuditImportStatus
    status: GridAuditQueueStatus


class GridAuditQueuePageResponse(ApiModel):
    game_id: UUID
    audit_id: str
    created_at: str
    artifact_sha256: Sha256
    counts: GridAuditQueueCountsResponse
    items: tuple[GridAuditQueueItemResponse, ...]
    next_after_ordinal: int | None


class GridAuditNodeResponse(ApiModel):
    x: float
    y: float


class GridAuditProposalGridResponse(ApiModel):
    coordinate_space: Literal["exif-normalized-rgb-pixels-v1"] = GRID_AUDIT_COORDINATE_SPACE
    provenance: Literal["audit-network-proposal"] = GRID_AUDIT_PROVENANCE
    corners: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ] = Field(description="Outer corners of the network grid, row-major winding")
    nodes: tuple[GridAuditNodeResponse, ...] = Field(
        description="The 24 network lattice nodes (6 x 4, row-major)"
    )


class GridAuditSymbolSuggestionsResponse(ApiModel):
    algorithm_version: Literal["symbol-reference-library-v1"] = "symbol-reference-library-v1"
    generated_at: str
    artifact_sha256: Sha256
    preview_command: ImageGridReviewGeometryPreviewCommand
    cells: tuple[GridCorrectionCellSymbolSuggestionResponse, ...]
    tentative_cell_indices: tuple[int, ...] = Field(
        default=(), description="Best candidates without unanimous agreement; review before saving"
    )


class GridAuditProposalResponse(ApiModel):
    game_id: UUID
    audit_id: str
    item: GridAuditQueueItemResponse
    proposal: GridAuditProposalGridResponse | None = Field(
        description="Only while the board still has the audited geometry revision"
    )
    review_item: ImageGridReviewItemResponse | None = Field(
        description="The current board as the correction queue serves it"
    )
    symbol_suggestions: GridAuditSymbolSuggestionsResponse | None = Field(
        default=None,
        description="New advisory symbols for exactly the proposed preview; never old approvals",
    )


def to_grid_audit_queue_item_response(entry: GridAuditQueueEntry) -> GridAuditQueueItemResponse:
    item = entry.item
    return GridAuditQueueItemResponse(
        ordinal=item.ordinal,
        item_id=item.item_id,
        verdict_source=item.verdict_source,
        audit_class=item.audit_class,
        level=item.level,
        human_decided_cells=item.human_decided_cells,
        recognized_board_id=item.recognized_board_id,
        source_image_id=item.source_image_id,
        import_job_id=item.import_job_id,
        sequence_number=item.sequence_number,
        position_index=item.position_index,
        audit_geometry_revision=item.audit_geometry_revision,
        current_geometry_revision=entry.current_geometry_revision,
        import_status=item.import_status,
        status=entry.status,
    )


def to_grid_audit_queue_page_response(
    *, game_id: UUID, page: GridAuditQueuePage
) -> GridAuditQueuePageResponse:
    counts = page.counts
    return GridAuditQueuePageResponse(
        game_id=game_id,
        audit_id=page.audit_id,
        created_at=page.created_at,
        artifact_sha256=page.sha256,
        counts=GridAuditQueueCountsResponse(
            total=counts.total,
            open=counts.open,
            corrected=counts.corrected,
            stale=counts.stale,
            removed=counts.removed,
            no_proposal=counts.no_proposal,
            open_with_symbol_decisions=counts.open_with_symbol_decisions,
        ),
        items=tuple(to_grid_audit_queue_item_response(entry) for entry in page.items),
        next_after_ordinal=page.next_after_ordinal,
    )


def to_grid_audit_proposal_response(
    *, game_id: UUID, view: GridAuditProposalView
) -> GridAuditProposalResponse:
    proposal = view.proposal
    return GridAuditProposalResponse(
        game_id=game_id,
        audit_id=view.audit_id,
        item=to_grid_audit_queue_item_response(view.entry),
        proposal=None
        if proposal is None
        else GridAuditProposalGridResponse(
            corners=(
                _corner(proposal.corners[0].x, proposal.corners[0].y),
                _corner(proposal.corners[1].x, proposal.corners[1].y),
                _corner(proposal.corners[2].x, proposal.corners[2].y),
                _corner(proposal.corners[3].x, proposal.corners[3].y),
            ),
            nodes=tuple(GridAuditNodeResponse(x=node.x, y=node.y) for node in proposal.nodes),
        ),
        review_item=None
        if view.review_item is None
        else to_image_grid_review_item_response(view.review_item),
        symbol_suggestions=_symbol_suggestions_response(view.symbol_suggestions),
    )


def _symbol_suggestions_response(
    suggestions: GridAuditSymbolSuggestions | None,
) -> GridAuditSymbolSuggestionsResponse | None:
    if suggestions is None:
        return None
    try:
        return GridAuditSymbolSuggestionsResponse(
            generated_at=suggestions.generated_at,
            artifact_sha256=suggestions.sha256,
            preview_command=ImageGridReviewGeometryPreviewCommand.model_validate(
                suggestions.preview_command
            ),
            cells=tuple(
                GridCorrectionCellSymbolSuggestionResponse(
                    cell_index=cell.cell_index,
                    symbol_id=cell.symbol_id,
                    origin="predicted",
                )
                for cell in suggestions.cells
            ),
            tentative_cell_indices=tuple(
                cell.cell_index for cell in suggestions.cells if cell.is_tentative
            ),
        )
    except ValueError as error:
        raise GridAuditProposalError(
            "GRID_AUDIT_SYMBOL_SUGGESTIONS_INVALID",
            "The symbol suggestion preview command is malformed.",
        ) from error


def _corner(x: float, y: float) -> ManualSourceGeometryPoint:
    return ManualSourceGeometryPoint(x=round(x), y=round(y))


__all__ = [
    "GridAuditNodeResponse",
    "GridAuditProposalGridResponse",
    "GridAuditProposalResponse",
    "GridAuditQueueCountsResponse",
    "GridAuditQueueItemResponse",
    "GridAuditQueuePageResponse",
    "to_grid_audit_proposal_response",
    "to_grid_audit_queue_page_response",
]
