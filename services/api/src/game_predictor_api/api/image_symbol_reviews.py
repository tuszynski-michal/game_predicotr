"""Local Admin API for bounded, checksum-bound symbol-cell review reads."""

import hashlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from game_predictor_api.application.image_symbol_reviews import (
    DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
    SymbolCellReviewQueryService,
)
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.image_symbol_reviews import (
    SymbolCellReviewPageResponse,
    to_symbol_cell_review_page_response,
)

SymbolCellReviewQueryServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game or current crop not found"},
    409: {"model": ErrorResponse, "description": "Cursor, readiness, or crop conflict"},
    422: {"model": ErrorResponse, "description": "Invalid symbol-cell review query"},
}


def create_image_symbol_reviews_router(
    service_dependency: SymbolCellReviewQueryServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["symbol-cell-reviews"])
    service_parameter = Depends(service_dependency)

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
        limit: Annotated[
            int, Query(ge=1, le=100)
        ] = DEFAULT_SYMBOL_CELL_REVIEW_PAGE_SIZE,
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
        expected_crop_checksum_sha256: Annotated[
            str, Query(alias="expectedCropChecksumSha256")
        ],
    ) -> FileResponse:
        asset = service.asset(
            game_id=game_id,
            cell_review_id=cell_review_id,
            expected_crop_checksum_sha256=expected_crop_checksum_sha256,
        )
        path = resolve_symbol_cell_review_asset(
            artifact_root,
            asset.crop_relative_path,
            asset.crop_checksum_sha256,
        )
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "private, immutable, max-age=31536000"},
        )

    return router


def resolve_symbol_cell_review_asset(root: Path, relative_value: str, checksum: str) -> Path:
    """Resolve a read-only crop below managed data and re-check its bytes."""

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
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_ASSET_CHECKSUM_MISMATCH",
            "The current symbol-cell crop bytes do not match their checksum.",
        )
    return path


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


__all__ = ["create_image_symbol_reviews_router", "resolve_symbol_cell_review_asset"]
