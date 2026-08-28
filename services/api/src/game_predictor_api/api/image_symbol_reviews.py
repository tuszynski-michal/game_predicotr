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
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_symbol_reviews import (
    SymbolCellReviewBulkOperationRequest,
    SymbolCellReviewBulkOperationResponse,
    SymbolCellReviewBulkOperationStartRequest,
    SymbolCellReviewBulkOperationStartResponse,
    SymbolCellReviewBulkPreviewResponse,
    SymbolCellReviewMutationRequest,
    SymbolCellReviewMutationResponse,
    SymbolCellReviewPageResponse,
    SymbolCellReviewProjectionStartResponse,
    SymbolCellReviewProjectionStatusResponse,
    to_symbol_cell_review_bulk_operation_response,
    to_symbol_cell_review_bulk_preview_response,
    to_symbol_cell_review_bulk_request,
    to_symbol_cell_review_mutation_response,
    to_symbol_cell_review_page_response,
    to_symbol_cell_review_projection_start_response,
    to_symbol_cell_review_projection_status_response,
)

SymbolCellReviewQueryServiceDependency = Callable[..., object]
SymbolCellReviewBulkOperationServiceDependency = Callable[..., object]
SymbolCellReviewMutationServiceDependency = Callable[..., object]
SymbolCellReviewBackfillServiceDependency = Callable[..., object]
_LOCAL_ADMIN_ACTOR = "local-admin"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game or current crop not found"},
    409: {"model": ErrorResponse, "description": "Cursor, readiness, or crop conflict"},
    422: {"model": ErrorResponse, "description": "Invalid symbol-cell review query"},
}


def create_image_symbol_reviews_router(
    service_dependency: SymbolCellReviewQueryServiceDependency,
    mutation_service_dependency: SymbolCellReviewMutationServiceDependency,
    bulk_operation_service_dependency: SymbolCellReviewBulkOperationServiceDependency,
    backfill_service_dependency: SymbolCellReviewBackfillServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["symbol-cell-reviews"])
    service_parameter = Depends(service_dependency)
    mutation_service_parameter = Depends(mutation_service_dependency)
    bulk_operation_service_parameter = Depends(bulk_operation_service_dependency)
    backfill_service_parameter = Depends(backfill_service_dependency)

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
        summary="List current symbol-cell reviews with bounded keyset pagination",
        responses=ERROR_RESPONSES,
    )
    def list_symbol_cell_reviews(
        game_id: UUID,
        service: Annotated[SymbolCellReviewQueryService, service_parameter],
        symbol_id: Annotated[str, Query(alias="symbolId")],
        state: SymbolCellReviewFilterState = SymbolCellReviewFilterState.ALL,
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        before_cursor: Annotated[str | None, Query(alias="beforeCursor")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
    ) -> SymbolCellReviewPageResponse:
        return to_symbol_cell_review_page_response(
            service.list(
                game_id=game_id,
                symbol_id=_parse_symbol_filter(symbol_id),
                state=state,
                after_cursor=after_cursor,
                before_cursor=before_cursor,
                limit=limit,
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
        expected_crop_checksum_sha256: Annotated[str, Query(alias="expectedCropChecksumSha256")],
        thumbnail_size: Annotated[int, Query(alias="thumbnailSize", ge=32, le=256)] = 100,
    ) -> Response:
        asset = service.asset(
            game_id=game_id,
            cell_review_id=cell_review_id,
            expected_crop_checksum_sha256=expected_crop_checksum_sha256,
        )
        _path, content = read_symbol_cell_review_asset(
            artifact_root,
            asset.crop_relative_path,
            asset.crop_checksum_sha256,
        )
        return symbol_cell_review_thumbnail_response(content, thumbnail_size)

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
