"""HTTP boundary for automatic symbol-catalog bootstrap."""

import hashlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from game_predictor_api.application.symbol_bootstrap import SymbolBootstrapService
from game_predictor_api.domain.catalog import CatalogConflictError, CatalogNotFoundError
from game_predictor_api.domain.symbol_bootstrap import SymbolBootstrapDefinition
from game_predictor_api.schemas.catalog import ErrorResponse, SymbolResponse
from game_predictor_api.schemas.symbol_bootstrap import (
    SymbolBootstrapResolveCommand,
    SymbolBootstrapRunResponse,
    SymbolBootstrapStartCommand,
    SymbolImageCandidatePageResponse,
    SymbolImageSelectionCommand,
    to_symbol_bootstrap_response,
    to_symbol_image_candidate_page_response,
)

SymbolBootstrapServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game or bootstrap not found"},
    409: {"model": ErrorResponse, "description": "Bootstrap conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_symbol_bootstrap_router(
    service_dependency: SymbolBootstrapServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["symbol-bootstrap"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/{game_id}/symbol-bootstrap",
        response_model=SymbolBootstrapRunResponse | None,
        operation_id="getLatestSymbolBootstrap",
        summary="Get the latest symbol bootstrap run",
        responses=ERROR_RESPONSES,
    )
    def latest(
        game_id: UUID,
        service: Annotated[SymbolBootstrapService, service_parameter],
    ) -> SymbolBootstrapRunResponse | None:
        run = service.latest(game_id)
        return None if run is None else to_symbol_bootstrap_response(run)

    @router.post(
        "/{game_id}/symbol-bootstrap",
        response_model=SymbolBootstrapRunResponse,
        operation_id="startSymbolBootstrap",
        summary="Build symbol proposals from imported crops",
        responses=ERROR_RESPONSES,
    )
    def start(
        game_id: UUID,
        payload: SymbolBootstrapStartCommand,
        service: Annotated[SymbolBootstrapService, service_parameter],
    ) -> SymbolBootstrapRunResponse:
        return to_symbol_bootstrap_response(
            service.start(
                game_id,
                expected_symbol_count=payload.expected_symbol_count,
                created_by=payload.created_by,
            )
        )

    @router.post(
        "/{game_id}/symbol-bootstrap/{bootstrap_id}/resolution",
        response_model=SymbolBootstrapRunResponse,
        operation_id="resolveSymbolBootstrap",
        summary="Resolve a symbol cluster-count conflict",
        responses=ERROR_RESPONSES,
    )
    def resolve(
        game_id: UUID,
        bootstrap_id: UUID,
        payload: SymbolBootstrapResolveCommand,
        service: Annotated[SymbolBootstrapService, service_parameter],
    ) -> SymbolBootstrapRunResponse:
        run = service.get(game_id, bootstrap_id)
        candidates = {item.candidate_id: item for item in run.candidates}
        definitions = tuple(
            SymbolBootstrapDefinition(
                mobile_code=item.mobile_code,
                code=item.code,
                name=item.name,
                candidate_ids=item.candidate_ids,
                image_path=(
                    candidates[item.candidate_ids[0]].representative_crop_relative_path
                    if item.candidate_ids[0] in candidates
                    else ""
                ),
            )
            for item in payload.symbols
        )
        return to_symbol_bootstrap_response(
            service.resolve(
                game_id,
                bootstrap_id,
                definitions=definitions,
            )
        )

    @router.get(
        "/{game_id}/symbols/{symbol_id}/image-candidates",
        response_model=SymbolImageCandidatePageResponse,
        operation_id="listSymbolImageCandidates",
        summary="List a bounded page of actual crop candidates",
        responses=ERROR_RESPONSES,
    )
    def list_image_candidates(
        game_id: UUID,
        symbol_id: UUID,
        service: Annotated[SymbolBootstrapService, service_parameter],
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        limit: Annotated[int, Query(ge=1, le=10)] = 10,
    ) -> SymbolImageCandidatePageResponse:
        return to_symbol_image_candidate_page_response(
            service.image_candidates(
                game_id,
                symbol_id,
                after_cursor=after_cursor,
                limit=limit,
            )
        )

    @router.get(
        "/{game_id}/symbols/{symbol_id}/image-candidates/{observation_id}/asset",
        response_class=FileResponse,
        operation_id="getSymbolImageCandidateAsset",
        summary="Read one checksum-bound symbol crop candidate",
        responses=ERROR_RESPONSES,
    )
    def get_image_candidate_asset(
        game_id: UUID,
        symbol_id: UUID,
        observation_id: UUID,
        service: Annotated[SymbolBootstrapService, service_parameter],
    ) -> FileResponse:
        candidate = service.image_candidate(game_id, symbol_id, observation_id)
        path = _resolve_candidate_asset(
            artifact_root,
            candidate.crop_relative_path,
            candidate.crop_checksum_sha256,
        )
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "private, immutable, max-age=31536000"},
        )

    @router.get(
        "/{game_id}/symbols/{symbol_id}/image/asset",
        response_class=FileResponse,
        operation_id="getSymbolImageAsset",
        summary="Read the current checksum-bound symbol reference image",
        responses=ERROR_RESPONSES,
    )
    def get_symbol_image_asset(
        game_id: UUID,
        symbol_id: UUID,
        service: Annotated[SymbolBootstrapService, service_parameter],
    ) -> FileResponse:
        candidate = service.selected_image_candidate(game_id, symbol_id)
        path = _resolve_candidate_asset(
            artifact_root,
            candidate.crop_relative_path,
            candidate.crop_checksum_sha256,
        )
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})

    @router.post(
        "/{game_id}/symbols/{symbol_id}/image-candidates/{observation_id}/selection",
        response_model=SymbolResponse,
        operation_id="selectSymbolImageCandidate",
        summary="Select a checksum-bound crop as the symbol reference image",
        responses=ERROR_RESPONSES,
    )
    def select_image_candidate(
        game_id: UUID,
        symbol_id: UUID,
        observation_id: UUID,
        payload: SymbolImageSelectionCommand,
        service: Annotated[SymbolBootstrapService, service_parameter],
    ) -> SymbolResponse:
        candidate = service.image_candidate(game_id, symbol_id, observation_id)
        _resolve_candidate_asset(
            artifact_root,
            candidate.crop_relative_path,
            candidate.crop_checksum_sha256,
        )
        return SymbolResponse.model_validate(
            service.select_image_candidate(
                game_id,
                symbol_id,
                observation_id,
                name=payload.name,
            )
        )

    return router


def _resolve_candidate_asset(root: Path, relative_value: str, checksum: str) -> Path:
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CatalogConflictError(
            "SYMBOL_IMAGE_ASSET_INVALID",
            "The symbol image candidate path is unsafe.",
        )
    data_root = (root.resolve() / "data").resolve()
    path = (root.resolve() / Path(*relative.parts)).resolve()
    if not path.is_relative_to(data_root) or not path.is_file():
        raise CatalogNotFoundError(
            "SYMBOL_IMAGE_ASSET_NOT_FOUND",
            "The symbol image candidate file is unavailable.",
        )
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise CatalogConflictError(
            "SYMBOL_IMAGE_ASSET_TYPE_INVALID",
            "The symbol image candidate must be a PNG or JPEG file.",
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != checksum:
        raise CatalogConflictError(
            "SYMBOL_IMAGE_ASSET_CHECKSUM_MISMATCH",
            "The symbol image candidate checksum does not match.",
        )
    return path


__all__ = ["create_symbol_bootstrap_router"]
