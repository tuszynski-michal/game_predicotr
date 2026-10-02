"""OpenAPI contracts for the game-wide grid correction queue."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometrySaveResult,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewCounts,
    ImageGridReviewListItem,
    ImageGridReviewPage,
    ImageGridReviewSlotKind,
    ImageGridReviewState,
    ImageGridReviewView,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.geometry_qualification import (
    AutomaticFrameGeometryProposalPayload,
    AutomaticPartialGeometryProposalPayload,
    GeometryQualificationPayload,
    GridCorrectionCellSymbolPayload,
)
from game_predictor_api.schemas.geometry_qualification import (
    ManualSourceGeometryPoint as OperationalImageReviewGeometryPoint,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ImageGridReviewItemResponse(ApiModel):
    geometry_qualification: GeometryQualificationPayload | None = None
    automatic_partial_proposal: AutomaticPartialGeometryProposalPayload | None = None
    automatic_frame_proposal: AutomaticFrameGeometryProposalPayload | None = None
    slot_id: UUID
    slot_kind: ImageGridReviewSlotKind
    review_item_id: UUID | None
    game_id: UUID
    import_job_id: UUID
    recognized_board_id: UUID | None
    pending_geometry_id: UUID | None
    source_image_id: UUID
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    source_checksum_sha256: Sha256
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    geometry_revision: int = Field(ge=0)
    approved_geometry_revision: int | None = Field(default=None, ge=0)
    resolution_revision: int = Field(ge=0)
    grid_rows: int = Field(gt=0)
    grid_columns: int = Field(gt=0)
    geometry: dict[str, object]
    analysis_quad: (
        tuple[
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
        ]
        | None
    ) = None
    board_frame_quad: (
        tuple[
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
        ]
        | None
    ) = None
    symbol_grid_quad: (
        tuple[
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
        ]
        | None
    ) = None
    review_draft_quad: (
        tuple[
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
            OperationalImageReviewGeometryPoint,
        ]
        | None
    ) = None
    review_draft_origin: str | None = None
    review_uncertainty_reason: str | None = None
    local_lattice_status: str | None = None
    local_lattice_version: str | None = None
    # D-467 S6 (TASK-0796): every recognized board is ``virtual_source``.
    asset_mode: Literal["virtual_source"]
    geometry_engine_name: str | None
    geometry_engine_version: str | None
    board_confidence: float = Field(ge=0, le=1)
    reason_codes: tuple[str, ...]
    state: ImageGridReviewState
    reported_cell_indices: tuple[Annotated[int, Field(ge=0)], ...] = ()


class ImageGridReviewCountsResponse(ApiModel):
    needs_validation: int = Field(ge=0)
    needs_correction: int = Field(ge=0)
    approved: int = Field(ge=0)
    total: int = Field(ge=0)
    full_grids: int = Field(default=0, ge=0)
    lateral_partial_proposals: int = Field(default=0, ge=0)
    confirmed_partial_grids: int = Field(default=0, ge=0)
    manual_correction: int = Field(default=0, ge=0)
    correction: int = Field(default=0, ge=0)


class ImageGridReviewPageResponse(ApiModel):
    game_id: UUID
    view: ImageGridReviewView
    import_job_id: UUID | None
    items: tuple[ImageGridReviewItemResponse, ...]
    counts: ImageGridReviewCountsResponse
    previous_cursor: str | None
    next_cursor: str | None


class ImageGridReviewGeometryPreviewCommand(ApiModel):
    geometry_qualification: GeometryQualificationPayload | None = None
    expected_geometry_revision: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ] = Field(description="Source-image outer corners in row-major winding")
    expected_source_checksum_sha256: Sha256
    expected_source_width: int = Field(gt=0)
    expected_source_height: int = Field(gt=0)
    expected_grid_rows: int = Field(gt=0)
    expected_grid_columns: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_signed_source_points(self) -> ImageGridReviewGeometryPreviewCommand:
        partial = (
            self.geometry_qualification is not None
            and self.geometry_qualification.completeness_status == "pending_partial"
        )
        for point in self.corners:
            if not partial and (point.x < 0 or point.y < 0):
                raise ValueError("signed corners require explicitly partial geometry")
            if partial and not (
                -self.expected_source_width <= point.x <= 2 * self.expected_source_width
                and -self.expected_source_height <= point.y <= 2 * self.expected_source_height
            ):
                raise ValueError("manual geometry exceeds source editing bounds")
        return self


class ImageGridReviewGeometryCommand(ImageGridReviewGeometryPreviewCommand):
    idempotency_key: UUID
    cell_symbols: tuple[GridCorrectionCellSymbolPayload, ...] = ()


class ImageGridReviewGeometryCellResponse(ApiModel):
    cell_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    crop_sample_id: Sha256
    crop_checksum_sha256: Sha256


class ImageGridReviewGeometryRevisionResponse(ApiModel):
    geometry_qualification: GeometryQualificationPayload | None = None
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    command_sha256: Sha256
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]
    asset_mode: Literal["virtual_source"]
    source_geometry_revision_id: UUID
    geometry_checksum_sha256: Sha256
    virtual_render_spec_checksum_sha256: Sha256
    cropper_version: str
    grid_rows: int = Field(gt=0)
    grid_columns: int = Field(gt=0)
    cells: tuple[ImageGridReviewGeometryCellResponse, ...]
    corrected_by: str
    created_at: datetime


class ImageGridReviewGeometryResponse(ApiModel):
    geometry_revision: ImageGridReviewGeometryRevisionResponse
    created: bool


def to_image_grid_review_item_response(
    item: ImageGridReviewListItem,
) -> ImageGridReviewItemResponse:
    geometry = dict(item.geometry)
    symbol_grid_quad = (
        geometry["symbolGridQuad"] if "symbolGridQuad" in geometry else geometry.get("quad")
    )
    return ImageGridReviewItemResponse(
        geometry_qualification=(
            GeometryQualificationPayload.model_validate(
                GeometryQualification.from_dict(geometry["geometryQualification"]).to_client_dict()
            )
            if geometry.get("geometryQualification") is not None
            else None
        ),
        automatic_partial_proposal=(
            AutomaticPartialGeometryProposalPayload.model_validate(
                geometry["automaticPartialProposal"]
            )
            if geometry.get("automaticPartialProposal") is not None
            else None
        ),
        automatic_frame_proposal=(
            AutomaticFrameGeometryProposalPayload.model_validate(geometry["automaticFrameProposal"])
            if geometry.get("automaticFrameProposal") is not None
            else None
        ),
        slot_id=item.slot_id,
        slot_kind=item.slot_kind,
        review_item_id=item.review_item_id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        recognized_board_id=item.recognized_board_id,
        pending_geometry_id=item.pending_geometry_id,
        source_image_id=item.source_image_id,
        position_index=item.position_index,
        sequence_number=item.sequence_number,
        source_checksum_sha256=item.source_checksum_sha256,
        source_width=item.source_width,
        source_height=item.source_height,
        geometry_revision=item.geometry_revision,
        approved_geometry_revision=item.approved_geometry_revision,
        resolution_revision=item.resolution_revision,
        grid_rows=item.topology.rows,
        grid_columns=item.topology.columns,
        geometry=geometry,
        analysis_quad=_optional_geometry_quad(geometry.get("analysisQuad")),
        review_draft_quad=_optional_geometry_quad(geometry.get("reviewDraftQuad")),
        review_draft_origin=_optional_text(geometry.get("reviewDraftOrigin")),
        review_uncertainty_reason=_optional_text(geometry.get("reviewUncertaintyReason")),
        board_frame_quad=_optional_geometry_quad(geometry.get("boardFrameQuad")),
        symbol_grid_quad=_optional_geometry_quad(symbol_grid_quad),
        local_lattice_status=_optional_text(geometry.get("localLatticeStatus")),
        local_lattice_version=_optional_text(geometry.get("localLatticeVersion")),
        # Pydantic still validates the literal at runtime (fail closed).
        asset_mode=cast(Literal["virtual_source"], item.asset_mode),
        geometry_engine_name=item.geometry_engine_name,
        geometry_engine_version=item.geometry_engine_version,
        board_confidence=item.board_confidence,
        reason_codes=item.reason_codes,
        state=item.state,
        reported_cell_indices=item.reported_cell_indices,
    )


def _optional_geometry_quad(
    value: object,
) -> (
    tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]
    | None
):
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        points = tuple(OperationalImageReviewGeometryPoint.model_validate(point) for point in value)
    except (TypeError, ValueError):
        return None
    return (points[0], points[1], points[2], points[3])


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def to_image_grid_review_counts_response(
    counts: ImageGridReviewCounts,
) -> ImageGridReviewCountsResponse:
    return ImageGridReviewCountsResponse(
        needs_validation=counts.needs_validation,
        needs_correction=counts.needs_correction,
        approved=counts.approved,
        total=counts.total,
        full_grids=(
            counts.needs_validation + counts.approved
            if counts.full_grids is None
            else counts.full_grids
        ),
        lateral_partial_proposals=counts.lateral_partial_proposals,
        confirmed_partial_grids=counts.confirmed_partial_grids,
        manual_correction=counts.manual_correction,
        correction=counts.correction,
    )


def to_image_grid_review_page_response(
    *,
    game_id: UUID,
    view: ImageGridReviewView,
    import_job_id: UUID | None,
    page: ImageGridReviewPage,
) -> ImageGridReviewPageResponse:
    return ImageGridReviewPageResponse(
        game_id=game_id,
        view=view,
        import_job_id=import_job_id,
        items=tuple(to_image_grid_review_item_response(item) for item in page.items),
        counts=to_image_grid_review_counts_response(page.counts),
        previous_cursor=page.previous_cursor,
        next_cursor=page.next_cursor,
    )


def to_virtual_grid_review_geometry_response(
    result: VirtualGridGeometrySaveResult,
    *,
    grid_rows: int,
    grid_columns: int,
) -> ImageGridReviewGeometryResponse:
    revision = result.revision
    return ImageGridReviewGeometryResponse(
        geometry_revision=ImageGridReviewGeometryRevisionResponse(
            geometry_qualification=GeometryQualificationPayload.model_validate(
                revision.geometry_qualification.to_client_dict()
            )
            if revision.geometry_qualification is not None
            else None,
            id=revision.id,
            review_item_id=revision.review_item_id,
            recognized_board_id=revision.recognized_board_id,
            revision=revision.revision,
            idempotency_key=revision.idempotency_key,
            command_sha256=revision.command_sha256,
            corners=(
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[0].x,
                    y=revision.corners[0].y,
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[1].x,
                    y=revision.corners[1].y,
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[2].x,
                    y=revision.corners[2].y,
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[3].x,
                    y=revision.corners[3].y,
                ),
            ),
            asset_mode="virtual_source",
            source_geometry_revision_id=revision.source_geometry_revision_id,
            geometry_checksum_sha256=revision.geometry_checksum_sha256,
            virtual_render_spec_checksum_sha256=(revision.virtual_render_spec_checksum_sha256),
            cropper_version=revision.cropper_version,
            grid_rows=grid_rows,
            grid_columns=grid_columns,
            cells=tuple(
                ImageGridReviewGeometryCellResponse(
                    cell_index=cell.cell_index,
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    crop_sample_id=cell.crop_sample_id,
                    crop_checksum_sha256=cell.crop_checksum_sha256,
                )
                for cell in revision.cells
            ),
            corrected_by=revision.corrected_by,
            created_at=revision.created_at,
        ),
        created=result.created,
    )


__all__ = [
    "ImageGridReviewCountsResponse",
    "ImageGridReviewGeometryCommand",
    "ImageGridReviewGeometryResponse",
    "ImageGridReviewGeometryPreviewCommand",
    "ImageGridReviewItemResponse",
    "ImageGridReviewPageResponse",
    "to_image_grid_review_page_response",
    "to_virtual_grid_review_geometry_response",
]
