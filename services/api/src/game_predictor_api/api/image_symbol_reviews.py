"""Local Admin API for bounded, checksum-bound symbol-cell review reads."""

import hashlib
from collections.abc import Callable
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError

from game_predictor_api.application.image_symbol_review_backfill import (
    SymbolCellReviewBackfillService,
)
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkOperationService,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.application.image_symbol_reviews import (
    DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
    SymbolCellReviewQueryService,
)
from game_predictor_api.application.unreadable_board_reviews import (
    UnreadableBoardReviewService,
    UnreadableBoardReviewView,
)
from game_predictor_api.application.virtual_cell_previews import (
    VirtualCellPreviewService,
    VirtualCellPreviewTarget,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_symbol_reviews import (
    ResolveUnreadableCellRequest,
    SymbolCellReviewBulkOperationRequest,
    SymbolCellReviewBulkOperationResponse,
    SymbolCellReviewBulkOperationStartRequest,
    SymbolCellReviewBulkOperationStartResponse,
    SymbolCellReviewBulkPreviewResponse,
    SymbolCellReviewCountSnapshotResponse,
    SymbolCellReviewMutationRequest,
    SymbolCellReviewMutationResponse,
    SymbolCellReviewPageResponse,
    SymbolCellReviewProjectionStartResponse,
    SymbolCellReviewProjectionStatusResponse,
    UnreadableBoardReviewDetailResponse,
    UnreadableBoardReviewPageResponse,
    UnreadableSymbolAssignmentRequest,
    VirtualCellPreviewBatchRequest,
    VirtualCellPreviewBatchResponse,
    VirtualCellPreviewTileResponse,
    to_symbol_cell_review_bulk_operation_response,
    to_symbol_cell_review_bulk_preview_response,
    to_symbol_cell_review_bulk_request,
    to_symbol_cell_review_count_snapshot_response,
    to_symbol_cell_review_mutation_response,
    to_symbol_cell_review_page_response,
    to_symbol_cell_review_projection_start_response,
    to_symbol_cell_review_projection_status_response,
    to_unreadable_board_review_detail_response,
    to_unreadable_board_review_page_response,
)

SymbolCellReviewQueryServiceDependency = Callable[..., object]
VirtualCellPreviewServiceDependency = Callable[..., object]
SymbolCellReviewBulkOperationServiceDependency = Callable[..., object]
SymbolCellReviewMutationServiceDependency = Callable[..., object]
SymbolCellReviewBackfillServiceDependency = Callable[..., object]
UnreadableBoardReviewServiceDependency = Callable[..., object]
_LOCAL_ADMIN_ACTOR = "local-admin"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game or current crop not found"},
    409: {"model": ErrorResponse, "description": "Cursor, readiness, or crop conflict"},
    422: {"model": ErrorResponse, "description": "Invalid symbol-cell review query"},
}


def create_image_symbol_reviews_router(
    service_dependency: SymbolCellReviewQueryServiceDependency,
    virtual_preview_service_dependency: VirtualCellPreviewServiceDependency,
    mutation_service_dependency: SymbolCellReviewMutationServiceDependency,
    bulk_operation_service_dependency: SymbolCellReviewBulkOperationServiceDependency,
    backfill_service_dependency: SymbolCellReviewBackfillServiceDependency,
    unreadable_board_service_dependency: UnreadableBoardReviewServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["symbol-cell-reviews"])
    service_parameter = Depends(service_dependency)
    virtual_preview_service_parameter = Depends(virtual_preview_service_dependency)
    mutation_service_parameter = Depends(mutation_service_dependency)
    bulk_operation_service_parameter = Depends(bulk_operation_service_dependency)
    backfill_service_parameter = Depends(backfill_service_dependency)
    unreadable_board_service_parameter = Depends(unreadable_board_service_dependency)

    @router.get(
        "/{game_id}/unreadable-board-reviews",
        response_model=UnreadableBoardReviewPageResponse,
        operation_id="listUnreadableBoardReviews",
        summary="List current logical boards containing unreadable symbol crops",
        responses=ERROR_RESPONSES,
    )
    def list_unreadable_board_reviews(
        game_id: UUID,
        service: Annotated[UnreadableBoardReviewService, unreadable_board_service_parameter],
        view: UnreadableBoardReviewView = UnreadableBoardReviewView.PENDING,
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> UnreadableBoardReviewPageResponse:
        return to_unreadable_board_review_page_response(
            service.list(game_id=game_id, view=view, after_cursor=after_cursor, limit=limit)
        )

    @router.get(
        "/{game_id}/unreadable-board-reviews/{review_item_id}",
        response_model=UnreadableBoardReviewDetailResponse,
        operation_id="getUnreadableBoardReview",
        summary="Read one current board with all topology-aware symbol cells",
        responses=ERROR_RESPONSES,
    )
    def get_unreadable_board_review(
        game_id: UUID,
        review_item_id: UUID,
        service: Annotated[UnreadableBoardReviewService, unreadable_board_service_parameter],
    ) -> UnreadableBoardReviewDetailResponse:
        return to_unreadable_board_review_detail_response(
            service.detail(game_id=game_id, review_item_id=review_item_id)
        )

    @router.post(
        "/{game_id}/unreadable-board-reviews/{review_item_id}/cells/{cell_index}/resolve",
        response_model=SymbolCellReviewMutationResponse,
        operation_id="resolveUnreadableBoardReviewCell",
        summary="Resolve one unreadable crop as an active symbol or logical unknown",
        responses=ERROR_RESPONSES,
    )
    def resolve_unreadable_board_review_cell(
        game_id: UUID,
        review_item_id: UUID,
        cell_index: int,
        request: ResolveUnreadableCellRequest,
        service: Annotated[UnreadableBoardReviewService, unreadable_board_service_parameter],
    ) -> SymbolCellReviewMutationResponse:
        target_symbol_id = (
            request.assignment.symbol_id
            if isinstance(request.assignment, UnreadableSymbolAssignmentRequest)
            else None
        )
        return to_symbol_cell_review_mutation_response(
            service.resolve(
                game_id=game_id,
                review_item_id=review_item_id,
                cell_index=cell_index,
                expected_revision=request.expected_revision,
                expected_geometry_revision=request.expected_geometry_revision,
                expected_crop_sample_id=request.expected_crop_sample_id,
                expected_crop_checksum_sha256=request.expected_crop_checksum_sha256,
                target_symbol_id=target_symbol_id,
                actor=_LOCAL_ADMIN_ACTOR,
            )
        )

    @router.get(
        "/{game_id}/symbol-cell-review-projection",
        response_model=SymbolCellReviewProjectionStatusResponse,
        operation_id="getSymbolCellReviewProjectionStatus",
        summary="Get symbol-cell review projection readiness and progress",
        responses=ERROR_RESPONSES,
    )
    def get_symbol_cell_review_projection_status(
        game_id: UUID,
        service: Annotated[SymbolCellReviewBackfillService, backfill_service_parameter],
    ) -> SymbolCellReviewProjectionStatusResponse:
        return to_symbol_cell_review_projection_status_response(service.status(game_id))

    @router.post(
        "/{game_id}/symbol-cell-review-projection",
        response_model=SymbolCellReviewProjectionStartResponse,
        operation_id="startSymbolCellReviewProjectionBackfill",
        summary="Start or resume durable symbol-cell review projection preparation",
        responses=ERROR_RESPONSES,
    )
    def start_symbol_cell_review_projection_backfill(
        game_id: UUID,
        service: Annotated[SymbolCellReviewBackfillService, backfill_service_parameter],
    ) -> SymbolCellReviewProjectionStartResponse:
        return to_symbol_cell_review_projection_start_response(service.start(game_id))

    @router.post(
        "/{game_id}/symbol-cell-review-operations/preview",
        response_model=SymbolCellReviewBulkPreviewResponse,
        operation_id="previewSymbolCellReviewBulkOperation",
        summary="Preview a frozen local symbol-cell review operation",
        responses=ERROR_RESPONSES,
    )
    def preview_symbol_cell_review_bulk_operation(
        game_id: UUID,
        request: SymbolCellReviewBulkOperationRequest,
        service: Annotated[
            SymbolCellReviewBulkOperationService,
            bulk_operation_service_parameter,
        ],
    ) -> SymbolCellReviewBulkPreviewResponse:
        return to_symbol_cell_review_bulk_preview_response(
            service.preview(
                game_id=game_id,
                request=to_symbol_cell_review_bulk_request(
                    request,
                    actor=_LOCAL_ADMIN_ACTOR,
                ),
            )
        )

    @router.post(
        "/{game_id}/symbol-cell-reviews/{cell_review_id}/decision",
        response_model=SymbolCellReviewMutationResponse,
        operation_id="applySymbolCellReviewDecision",
        summary="Apply one atomic checksum-bound symbol-cell review decision",
        responses=ERROR_RESPONSES,
    )
    def apply_symbol_cell_review_decision(
        game_id: UUID,
        cell_review_id: UUID,
        request: SymbolCellReviewMutationRequest,
        service: Annotated[SymbolCellReviewMutationService, mutation_service_parameter],
    ) -> SymbolCellReviewMutationResponse:
        if request.action is SymbolCellReviewAction.REASSIGN:
            assert request.target_symbol_id is not None
            result = service.reassign(
                game_id=game_id,
                cell_review_id=cell_review_id,
                expected_revision=request.expected_revision,
                expected_geometry_revision=request.expected_geometry_revision,
                expected_crop_sample_id=request.expected_crop_sample_id,
                expected_crop_checksum_sha256=request.expected_crop_checksum_sha256,
                target_symbol_id=request.target_symbol_id,
                actor=_LOCAL_ADMIN_ACTOR,
            )
        elif request.action is SymbolCellReviewAction.MARK_GRID_ISSUE:
            result = service.mark_grid_issue(
                game_id=game_id,
                cell_review_id=cell_review_id,
                expected_revision=request.expected_revision,
                expected_geometry_revision=request.expected_geometry_revision,
                expected_crop_sample_id=request.expected_crop_sample_id,
                expected_crop_checksum_sha256=request.expected_crop_checksum_sha256,
                actor=_LOCAL_ADMIN_ACTOR,
            )
        elif request.action is SymbolCellReviewAction.MARK_UNREADABLE:
            result = service.mark_unreadable(
                game_id=game_id,
                cell_review_id=cell_review_id,
                expected_revision=request.expected_revision,
                expected_geometry_revision=request.expected_geometry_revision,
                expected_crop_sample_id=request.expected_crop_sample_id,
                expected_crop_checksum_sha256=request.expected_crop_checksum_sha256,
                actor=_LOCAL_ADMIN_ACTOR,
            )
        else:
            result = service.approve(
                game_id=game_id,
                cell_review_id=cell_review_id,
                expected_revision=request.expected_revision,
                expected_geometry_revision=request.expected_geometry_revision,
                expected_crop_sample_id=request.expected_crop_sample_id,
                expected_crop_checksum_sha256=request.expected_crop_checksum_sha256,
                actor=_LOCAL_ADMIN_ACTOR,
            )
        return to_symbol_cell_review_mutation_response(result)

    @router.post(
        "/{game_id}/symbol-cell-review-operations",
        response_model=SymbolCellReviewBulkOperationStartResponse,
        operation_id="startSymbolCellReviewBulkOperation",
        summary="Start an idempotent local symbol-cell review operation",
        responses=ERROR_RESPONSES,
    )
    def start_symbol_cell_review_bulk_operation(
        game_id: UUID,
        request: SymbolCellReviewBulkOperationStartRequest,
        service: Annotated[
            SymbolCellReviewBulkOperationService,
            bulk_operation_service_parameter,
        ],
    ) -> SymbolCellReviewBulkOperationStartResponse:
        operation, created = service.start(
            game_id=game_id,
            request=to_symbol_cell_review_bulk_request(
                request,
                actor=_LOCAL_ADMIN_ACTOR,
            ),
            idempotency_key=request.idempotency_key,
        )
        return SymbolCellReviewBulkOperationStartResponse(
            operation=to_symbol_cell_review_bulk_operation_response(operation),
            created=created,
        )

    @router.get(
        "/{game_id}/symbol-cell-review-operations/{operation_id}",
        response_model=SymbolCellReviewBulkOperationResponse,
        operation_id="getSymbolCellReviewBulkOperation",
        summary="Get durable local symbol-cell review operation status",
        responses=ERROR_RESPONSES,
    )
    def get_symbol_cell_review_bulk_operation(
        game_id: UUID,
        operation_id: UUID,
        service: Annotated[
            SymbolCellReviewBulkOperationService,
            bulk_operation_service_parameter,
        ],
    ) -> SymbolCellReviewBulkOperationResponse:
        return to_symbol_cell_review_bulk_operation_response(
            service.get(game_id=game_id, operation_id=operation_id)
        )

    @router.get(
        "/{game_id}/symbol-cell-reviews",
        response_model=SymbolCellReviewPageResponse,
        operation_id="listSymbolCellReviews",
        summary="List current symbol-cell reviews with keyset pagination",
        responses=ERROR_RESPONSES,
    )
    def list_symbol_cell_reviews(
        game_id: UUID,
        service: Annotated[SymbolCellReviewQueryService, service_parameter],
        symbol_id: Annotated[str, Query(alias="symbolId")],
        state: SymbolCellReviewFilterState = SymbolCellReviewFilterState.ALL,
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        before_cursor: Annotated[str | None, Query(alias="beforeCursor")] = None,
        min_confidence: Annotated[float | None, Query(alias="minConfidence", ge=0, le=1)] = None,
        max_confidence: Annotated[float | None, Query(alias="maxConfidence", ge=0, le=1)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
    ) -> SymbolCellReviewPageResponse:
        return to_symbol_cell_review_page_response(
            service.list(
                game_id=game_id,
                symbol_id=_parse_symbol_filter(symbol_id),
                state=state,
                after_cursor=after_cursor,
                before_cursor=before_cursor,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                limit=limit,
            )
        )

    @router.get(
        "/{game_id}/symbol-cell-review-counts",
        response_model=SymbolCellReviewCountSnapshotResponse,
        operation_id="getSymbolCellReviewCounts",
        summary="Count one revision-bound symbol-cell review filter independently",
        responses=ERROR_RESPONSES,
    )
    def get_symbol_cell_review_counts(
        game_id: UUID,
        service: Annotated[SymbolCellReviewQueryService, service_parameter],
        symbol_id: Annotated[str, Query(alias="symbolId")],
        catalog_revision: Annotated[int, Query(alias="catalogRevision", ge=0)],
        state: SymbolCellReviewFilterState = SymbolCellReviewFilterState.PENDING,
        min_confidence: Annotated[float | None, Query(alias="minConfidence", ge=0, le=1)] = None,
        max_confidence: Annotated[float | None, Query(alias="maxConfidence", ge=0, le=1)] = None,
    ) -> SymbolCellReviewCountSnapshotResponse:
        return to_symbol_cell_review_count_snapshot_response(
            service.counts(
                game_id=game_id,
                symbol_id=_parse_symbol_filter(symbol_id),
                state=state,
                expected_catalog_revision=catalog_revision,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
            )
        )

    @router.get(
        "/{game_id}/symbol-cell-reviews/{cell_review_id}/asset",
        response_class=FileResponse,
        operation_id="getSymbolCellReviewAsset",
        summary="Read one current checksum-bound symbol-cell crop",
        responses=ERROR_RESPONSES,
    )
    def get_symbol_cell_review_asset(
        game_id: UUID,
        cell_review_id: UUID,
        service: Annotated[SymbolCellReviewQueryService, service_parameter],
        preview_service: Annotated[VirtualCellPreviewService, virtual_preview_service_parameter],
        expected_crop_checksum_sha256: Annotated[str, Query(alias="expectedCropChecksumSha256")],
        expected_render_spec_checksum_sha256: Annotated[
            str | None, Query(alias="expectedRenderSpecChecksumSha256")
        ] = None,
        thumbnail_size: Annotated[int, Query(alias="thumbnailSize", ge=32, le=256)] = 100,
    ) -> Response:
        asset = service.asset(
            game_id=game_id,
            cell_review_id=cell_review_id,
            expected_crop_checksum_sha256=expected_crop_checksum_sha256,
        )
        if asset.asset_mode == "virtual_source":
            if expected_render_spec_checksum_sha256 is None:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_PREVIEW_RENDER_SPEC_REQUIRED",
                    "Virtual symbol-cell previews require expectedRenderSpecChecksumSha256.",
                )
            target = VirtualCellPreviewTarget(
                cell_review_id=cell_review_id,
                expected_revision=asset.revision,
                expected_render_spec_checksum_sha256=expected_render_spec_checksum_sha256,
            )
            virtual_assets = service.virtual_preview_assets(game_id=game_id, targets=(target,))
            batch = preview_service.render_batch(
                game_id=game_id,
                assets=virtual_assets,
                preview_size=thumbnail_size,
            )
            content = preview_service.read_atlas(game_id=game_id, batch_key=batch.batch_key).content
            return virtual_symbol_cell_review_thumbnail_response(content)
        _path, content = read_symbol_cell_review_asset(
            artifact_root,
            _required_relative_path(asset.crop_relative_path),
            asset.crop_checksum_sha256,
        )
        return symbol_cell_review_thumbnail_response(content, thumbnail_size)

    @router.post(
        "/{game_id}/virtual-cell-preview-batches",
        response_model=VirtualCellPreviewBatchResponse,
        operation_id="createVirtualCellPreviewBatch",
        summary="Render a bounded cached WebP atlas for current virtual symbol cells",
        responses=ERROR_RESPONSES,
    )
    def create_virtual_cell_preview_batch(
        game_id: UUID,
        request: VirtualCellPreviewBatchRequest,
        service: Annotated[SymbolCellReviewQueryService, service_parameter],
        preview_service: Annotated[VirtualCellPreviewService, virtual_preview_service_parameter],
    ) -> VirtualCellPreviewBatchResponse:
        targets = tuple(
            VirtualCellPreviewTarget(
                cell_review_id=cell.cell_review_id,
                expected_revision=cell.expected_revision,
                expected_render_spec_checksum_sha256=cell.expected_render_spec_checksum_sha256,
            )
            for cell in request.cells
        )
        assets = service.virtual_preview_assets(game_id=game_id, targets=targets)
        batch = preview_service.render_batch(
            game_id=game_id,
            assets=assets,
            preview_size=request.preview_size,
        )
        return VirtualCellPreviewBatchResponse(
            batch_key=batch.batch_key,
            atlas_url=(
                f"/api/v1/admin/games/{game_id}/virtual-cell-preview-batches/"
                f"{batch.batch_key}/atlas"
            ),
            atlas_checksum_sha256=batch.atlas_checksum_sha256,
            tiles=tuple(
                VirtualCellPreviewTileResponse(
                    cell_review_id=tile.cell_review_id,
                    x=tile.x,
                    y=tile.y,
                    width=tile.width,
                    height=tile.height,
                )
                for tile in batch.tiles
            ),
            expires_at=batch.expires_at,
        )

    @router.get(
        "/{game_id}/virtual-cell-preview-batches/{batch_key}/atlas",
        operation_id="getVirtualCellPreviewAtlas",
        summary="Read one non-expired checksum-verified virtual preview atlas",
        responses=ERROR_RESPONSES,
    )
    def get_virtual_cell_preview_atlas(
        game_id: UUID,
        batch_key: str,
        preview_service: Annotated[VirtualCellPreviewService, virtual_preview_service_parameter],
    ) -> Response:
        cached = preview_service.read_atlas(game_id=game_id, batch_key=batch_key)
        return virtual_symbol_cell_review_thumbnail_response(cached.content)

    return router


def resolve_symbol_cell_review_asset(root: Path, relative_value: str, checksum: str) -> Path:
    """Resolve a read-only crop below managed data and re-check its bytes."""

    path, _content = read_symbol_cell_review_asset(root, relative_value, checksum)
    return path


def read_symbol_cell_review_asset(
    root: Path,
    relative_value: str,
    checksum: str,
) -> tuple[Path, bytes]:
    """Read and verify one managed crop exactly once."""

    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_INVALID",
            "The symbol-cell crop path is unsafe.",
        )
    resolved_root = root.resolve()
    data_root = (resolved_root / "data").resolve()
    candidate_paths = [(resolved_root / Path(*relative.parts)).resolve()]
    if relative.parts[0] != "data":
        candidate_paths.append((data_root / Path(*relative.parts)).resolve())
    path = next(
        (
            candidate
            for candidate in candidate_paths
            if candidate.is_relative_to(data_root)
            and candidate.is_file()
            and not candidate.is_symlink()
        ),
        None,
    )
    if path is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_NOT_FOUND",
            "The current symbol-cell crop is unavailable.",
        )
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_TYPE_INVALID",
            "The symbol-cell crop must be a PNG or JPEG file.",
        )
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_CHECKSUM_MISMATCH",
            "The current symbol-cell crop bytes do not match their checksum.",
        )
    return path, content


def symbol_cell_review_thumbnail_response(content: bytes, size: int) -> Response:
    """Render one bounded card thumbnail and let the browser cache it immutably."""

    try:
        with Image.open(BytesIO(content)) as source:
            image = source.convert("RGB")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=82, method=4)
    except (OSError, UnidentifiedImageError) as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_INVALID",
            "The current symbol-cell crop cannot be rendered as a thumbnail.",
        ) from error
    content = output.getvalue()
    return Response(
        content=content,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, immutable, max-age=31536000",
            "Content-Length": str(len(content)),
        },
    )


def virtual_symbol_cell_review_thumbnail_response(content: bytes) -> Response:
    """Return a short-lived derived atlas; its cache key binds current provenance."""

    return Response(
        content=content,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, max-age=900, must-revalidate",
            "Content-Length": str(len(content)),
        },
    )


def _required_relative_path(value: str | None) -> str:
    if value is None:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_INVALID",
            "A legacy symbol-cell crop has no relative path.",
        )
    return value


def _parse_symbol_filter(value: str) -> UUID | None:
    if value == "unknown":
        return None
    try:
        return UUID(value)
    except ValueError as error:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_SYMBOL_FILTER_INVALID",
            "symbolId must be an active symbol UUID or the literal unknown.",
        ) from error


__all__ = [
    "create_image_symbol_reviews_router",
    "read_symbol_cell_review_asset",
    "resolve_symbol_cell_review_asset",
    "symbol_cell_review_thumbnail_response",
]
