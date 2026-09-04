"""OpenAPI contracts for the game-wide grid validation queue."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometrySaveResult,
    VirtualGridGeometrySourceCommand,
    VirtualGridGeometrySourceSaveResult,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridApprovalResult,
    ImageGridReviewCounts,
    ImageGridReviewListItem,
    ImageGridReviewPage,
    ImageGridReviewSourceApprovalTarget,
    ImageGridReviewState,
    ImageGridReviewView,
    ImageGridSourceApprovalResult,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryPoint,
    ImageReviewGeometryRevision,
    crop_sample_id,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.image_reviews import (
    OperationalImageReviewGeometryPoint,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ImageGridReviewItemResponse(ApiModel):
    review_item_id: UUID
    game_id: UUID
    import_job_id: UUID
    recognized_board_id: UUID
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
    local_lattice_status: str | None = None
    local_lattice_version: str | None = None
    asset_mode: str
    geometry_engine_name: str | None
    geometry_engine_version: str | None
    board_confidence: float = Field(ge=0, le=1)
    reason_codes: tuple[str, ...]
    state: ImageGridReviewState


class ImageGridReviewCountsResponse(ApiModel):
    needs_validation: int = Field(ge=0)
    needs_correction: int = Field(ge=0)
    approved: int = Field(ge=0)
    total: int = Field(ge=0)


class ImageGridReviewPageResponse(ApiModel):
    game_id: UUID
    view: ImageGridReviewView
    import_job_id: UUID | None
    items: tuple[ImageGridReviewItemResponse, ...]
    counts: ImageGridReviewCountsResponse
    previous_cursor: str | None
    next_cursor: str | None


class ImageGridReviewApprovalCommand(ApiModel):
    expected_resolution_revision: int = Field(ge=0)
    expected_geometry_revision: int = Field(ge=0)
    expected_source_checksum_sha256: Sha256
    expected_source_width: int = Field(gt=0)
    expected_source_height: int = Field(gt=0)
    expected_grid_rows: int = Field(gt=0)
    expected_grid_columns: int = Field(gt=0)


class ImageGridReviewApprovalResponse(ApiModel):
    item: ImageGridReviewItemResponse
    changed: bool


class ImageGridReviewSourceApprovalTargetRequest(ApiModel):
    review_item_id: UUID
    expected_resolution_revision: int = Field(ge=0)
    expected_geometry_revision: int = Field(ge=0)
    expected_source_checksum_sha256: Sha256
    expected_source_width: int = Field(gt=0)
    expected_source_height: int = Field(gt=0)
    expected_grid_rows: int = Field(gt=0)
    expected_grid_columns: int = Field(gt=0)


class ImageGridReviewSourceApprovalCommand(ApiModel):
    source_image_id: UUID
    targets: tuple[ImageGridReviewSourceApprovalTargetRequest, ...] = Field(
        min_length=1,
        max_length=9,
    )


class ImageGridReviewSourceApprovalResponse(ApiModel):
    source_image_id: UUID
    approved_review_item_ids: tuple[UUID, ...]
    changed_count: int = Field(ge=0)


class ImageGridReviewGeometryPreviewCommand(ApiModel):
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


class ImageGridReviewGeometryCommand(ImageGridReviewGeometryPreviewCommand):
    idempotency_key: UUID


class ImageGridReviewSourceGeometryTargetCommand(ImageGridReviewGeometryPreviewCommand):
    review_item_id: UUID


class ImageGridReviewSourceGeometryCommand(ApiModel):
    source_image_id: UUID
    idempotency_key: UUID
    targets: tuple[ImageGridReviewSourceGeometryTargetCommand, ...] = Field(
        min_length=1,
        max_length=9,
    )


class ImageGridReviewGeometryCellResponse(ApiModel):
    cell_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    crop_sample_id: Sha256
    crop_checksum_sha256: Sha256


class ImageGridReviewGeometryRevisionResponse(ApiModel):
    id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    revision: int = Field(ge=1)
    idempotency_key: UUID
    command_sha256: Sha256
    decision_checksum_sha256: Sha256 | None
    corners: tuple[
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
        OperationalImageReviewGeometryPoint,
    ]
    asset_mode: str = "legacy_file"
    board_checksum_sha256: Sha256 | None = None
    source_geometry_revision_id: UUID | None = None
    geometry_checksum_sha256: Sha256 | None = None
    virtual_render_spec_checksum_sha256: Sha256 | None = None
    cropper_version: str
    grid_rows: int = Field(gt=0)
    grid_columns: int = Field(gt=0)
    cells: tuple[ImageGridReviewGeometryCellResponse, ...] = Field(min_length=1)
    corrected_by: str
    created_at: datetime


class ImageGridReviewGeometryResponse(ApiModel):
    geometry_revision: ImageGridReviewGeometryRevisionResponse
    created: bool


class ImageGridReviewSourceGeometryResponse(ApiModel):
    source_image_id: UUID
    geometry_revisions: tuple[ImageGridReviewGeometryRevisionResponse, ...]
    created: bool


def to_image_grid_review_item_response(
    item: ImageGridReviewListItem,
) -> ImageGridReviewItemResponse:
    geometry = dict(item.geometry)
    return ImageGridReviewItemResponse(
        review_item_id=item.review_item_id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        recognized_board_id=item.recognized_board_id,
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
        board_frame_quad=_optional_geometry_quad(geometry.get("boardFrameQuad")),
        symbol_grid_quad=_optional_geometry_quad(
            geometry.get("symbolGridQuad") or geometry.get("quad")
        ),
        local_lattice_status=_optional_text(geometry.get("localLatticeStatus")),
        local_lattice_version=_optional_text(geometry.get("localLatticeVersion")),
        asset_mode=item.asset_mode,
        geometry_engine_name=item.geometry_engine_name,
        geometry_engine_version=item.geometry_engine_version,
        board_confidence=item.board_confidence,
        reason_codes=item.reason_codes,
        state=item.state,
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


def to_image_grid_review_approval_response(
    result: ImageGridApprovalResult,
) -> ImageGridReviewApprovalResponse:
    return ImageGridReviewApprovalResponse(
        item=to_image_grid_review_item_response(result.item),
        changed=result.changed,
    )


def to_image_grid_review_source_approval_targets(
    payload: ImageGridReviewSourceApprovalCommand,
) -> tuple[ImageGridReviewSourceApprovalTarget, ...]:
    return tuple(
        ImageGridReviewSourceApprovalTarget(
            review_item_id=target.review_item_id,
            expected_resolution_revision=target.expected_resolution_revision,
            expected_geometry_revision=target.expected_geometry_revision,
            expected_source_checksum_sha256=target.expected_source_checksum_sha256,
            expected_source_width=target.expected_source_width,
            expected_source_height=target.expected_source_height,
            expected_grid_rows=target.expected_grid_rows,
            expected_grid_columns=target.expected_grid_columns,
        )
        for target in payload.targets
    )


def to_image_grid_review_source_approval_response(
    result: ImageGridSourceApprovalResult,
) -> ImageGridReviewSourceApprovalResponse:
    return ImageGridReviewSourceApprovalResponse(
        source_image_id=result.source_image_id,
        approved_review_item_ids=result.approved_review_item_ids,
        changed_count=result.changed_count,
    )


def to_image_grid_review_geometry_response(
    *,
    revision: ImageReviewGeometryRevision,
    grid_rows: int,
    grid_columns: int,
    created: bool,
) -> ImageGridReviewGeometryResponse:
    return ImageGridReviewGeometryResponse(
        geometry_revision=ImageGridReviewGeometryRevisionResponse(
            id=revision.id,
            review_item_id=revision.review_item_id,
            recognized_board_id=revision.recognized_board_id,
            revision=revision.revision,
            idempotency_key=revision.idempotency_key,
            command_sha256=revision.command_sha256,
            decision_checksum_sha256=revision.decision_checksum_sha256,
            corners=(
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[0].x, y=revision.corners[0].y
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[1].x, y=revision.corners[1].y
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[2].x, y=revision.corners[2].y
                ),
                OperationalImageReviewGeometryPoint(
                    x=revision.corners[3].x, y=revision.corners[3].y
                ),
            ),
            board_checksum_sha256=revision.board_checksum_sha256,
            asset_mode="legacy_file",
            source_geometry_revision_id=None,
            geometry_checksum_sha256=None,
            virtual_render_spec_checksum_sha256=None,
            cropper_version=revision.cropper_version,
            grid_rows=grid_rows,
            grid_columns=grid_columns,
            cells=tuple(
                ImageGridReviewGeometryCellResponse(
                    cell_index=cell.row_index * grid_columns + cell.column_index,
                    row_index=cell.row_index,
                    column_index=cell.column_index,
                    crop_sample_id=crop_sample_id(
                        recognized_board_id=revision.recognized_board_id,
                        row_index=cell.row_index,
                        column_index=cell.column_index,
                        cropper_version=revision.cropper_version,
                        crop_relative_path=cell.crop_relative_path,
                        crop_checksum_sha256=cell.crop_checksum_sha256,
                    ),
                    crop_checksum_sha256=cell.crop_checksum_sha256,
                )
                for cell in revision.cells
            ),
            corrected_by=revision.corrected_by,
            created_at=revision.created_at,
        ),
        created=created,
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
            id=revision.id,
            review_item_id=revision.review_item_id,
            recognized_board_id=revision.recognized_board_id,
            revision=revision.revision,
            idempotency_key=revision.idempotency_key,
            command_sha256=revision.command_sha256,
            decision_checksum_sha256=None,
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
            board_checksum_sha256=None,
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


def to_virtual_grid_review_source_geometry_commands(
    payload: ImageGridReviewSourceGeometryCommand,
) -> tuple[VirtualGridGeometrySourceCommand, ...]:
    return tuple(
        VirtualGridGeometrySourceCommand(
            review_item_id=target.review_item_id,
            expected_geometry_revision=target.expected_geometry_revision,
            expected_resolution_revision=target.expected_resolution_revision,
            expected_source_checksum_sha256=target.expected_source_checksum_sha256,
            expected_source_width=target.expected_source_width,
            expected_source_height=target.expected_source_height,
            expected_grid_rows=target.expected_grid_rows,
            expected_grid_columns=target.expected_grid_columns,
            corners=tuple(
                ImageReviewGeometryPoint(x=corner.x, y=corner.y) for corner in target.corners
            ),
        )
        for target in payload.targets
    )


def to_virtual_grid_review_source_geometry_response(
    result: VirtualGridGeometrySourceSaveResult,
    *,
    source_image_id: UUID,
    grid_rows: int,
    grid_columns: int,
) -> ImageGridReviewSourceGeometryResponse:
    return ImageGridReviewSourceGeometryResponse(
        source_image_id=source_image_id,
        geometry_revisions=tuple(
            to_virtual_grid_review_geometry_response(
                VirtualGridGeometrySaveResult(revision=revision, created=result.created),
                grid_rows=grid_rows,
                grid_columns=grid_columns,
            ).geometry_revision
            for revision in result.revisions
        ),
        created=result.created,
    )


__all__ = [
    "ImageGridReviewApprovalCommand",
    "ImageGridReviewApprovalResponse",
    "ImageGridReviewSourceApprovalCommand",
    "ImageGridReviewSourceApprovalResponse",
    "ImageGridReviewCountsResponse",
    "ImageGridReviewGeometryCommand",
    "ImageGridReviewGeometryResponse",
    "ImageGridReviewSourceGeometryCommand",
    "ImageGridReviewSourceGeometryResponse",
    "ImageGridReviewGeometryPreviewCommand",
    "ImageGridReviewItemResponse",
    "ImageGridReviewPageResponse",
    "to_image_grid_review_approval_response",
    "to_image_grid_review_source_approval_response",
    "to_image_grid_review_source_approval_targets",
    "to_image_grid_review_geometry_response",
    "to_image_grid_review_page_response",
    "to_virtual_grid_review_geometry_response",
    "to_virtual_grid_review_source_geometry_commands",
    "to_virtual_grid_review_source_geometry_response",
]
