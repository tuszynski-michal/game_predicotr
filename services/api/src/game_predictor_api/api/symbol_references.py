"""Read-only HTTP API for human-approved symbol reference crop candidates."""

import hashlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from game_predictor_api.application.symbol_references import (
    ApprovedSymbolReferenceService,
)
from game_predictor_api.domain.catalog import CatalogConflictError, CatalogNotFoundError
from game_predictor_api.schemas.catalog import ErrorResponse, SymbolResponse
from game_predictor_api.schemas.symbol_references import (
    ApprovedSymbolReferenceCandidatePageResponse,
    ApprovedSymbolReferenceSelectionCommand,
    to_approved_symbol_reference_candidate_page_response,
)

ApprovedSymbolReferenceServiceDependency = Callable[..., object]
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Game, symbol, or crop not found"},
    409: {"model": ErrorResponse, "description": "Candidate cursor conflict"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def create_symbol_references_router(
    service_dependency: ApprovedSymbolReferenceServiceDependency,
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/admin/games", tags=["symbol-references"])
    service_parameter = Depends(service_dependency)

    @router.get(
        "/{game_id}/symbols/{symbol_id}/approved-image-candidates",
        response_model=ApprovedSymbolReferenceCandidatePageResponse,
        operation_id="listApprovedSymbolReferenceCandidates",
        summary="List human-approved crop candidates for a symbol reference",
        responses=ERROR_RESPONSES,
    )
    def list_candidates(
        game_id: UUID,
        symbol_id: UUID,
        service: Annotated[ApprovedSymbolReferenceService, service_parameter],
        after_cursor: Annotated[str | None, Query(alias="afterCursor")] = None,
        limit: Annotated[int, Query(ge=1, le=20)] = 20,
    ) -> ApprovedSymbolReferenceCandidatePageResponse:
        return to_approved_symbol_reference_candidate_page_response(
            service.candidates(
                game_id,
                symbol_id,
                after_cursor=after_cursor,
                limit=limit,
            )
        )

    @router.get(
        "/{game_id}/symbols/{symbol_id}/approved-image-candidates/{observation_id}/asset",
        response_class=FileResponse,
        operation_id="getApprovedSymbolReferenceCandidateAsset",
        summary="Read one checksum-bound human-approved crop candidate",
        responses=ERROR_RESPONSES,
    )
    def get_candidate_asset(
        game_id: UUID,
        symbol_id: UUID,
        observation_id: UUID,
        service: Annotated[ApprovedSymbolReferenceService, service_parameter],
    ) -> Response:
        candidate = service.candidate(game_id, symbol_id, observation_id)
        if candidate.is_virtual:
            rendered = service.virtual_candidate_asset(game_id, symbol_id, observation_id)
            return Response(
                content=rendered.content,
                media_type=rendered.media_type,
                headers={"Cache-Control": "no-store"},
            )
        path = resolve_symbol_reference_asset(
            artifact_root,
            candidate.crop_relative_path or "",
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
        summary="Read the current human-approved symbol reference image",
        responses=ERROR_RESPONSES,
    )
    def get_reference_asset(
        game_id: UUID,
        symbol_id: UUID,
        service: Annotated[ApprovedSymbolReferenceService, service_parameter],
    ) -> FileResponse:
        reference = service.reference(game_id, symbol_id)
        path = resolve_symbol_reference_asset(
            artifact_root,
            reference.image_relative_path,
            reference.image_checksum_sha256,
        )
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})

    @router.post(
        "/{game_id}/symbols/{symbol_id}/approved-image-candidates/{observation_id}/selection",
        response_model=SymbolResponse,
        operation_id="selectApprovedSymbolReferenceCandidate",
        summary="Persist one checksum-bound human-approved crop as a symbol reference",
        responses=ERROR_RESPONSES,
    )
    def select_candidate(
        game_id: UUID,
        symbol_id: UUID,
        observation_id: UUID,
        payload: ApprovedSymbolReferenceSelectionCommand,
        service: Annotated[ApprovedSymbolReferenceService, service_parameter],
    ) -> SymbolResponse:
        return SymbolResponse.model_validate(
            service.select(
                game_id,
                symbol_id,
                observation_id,
                expected_checksum_sha256=payload.expected_checksum_sha256,
                selected_by=payload.selected_by,
            )
        )

    return router


def resolve_symbol_reference_asset(root: Path, relative_value: str, checksum: str) -> Path:
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CatalogConflictError(
            "SYMBOL_REFERENCE_ASSET_INVALID",
            "The symbol reference crop path is unsafe.",
        )
    data_root = (root.resolve() / "data").resolve()
    relative_path = Path(*relative.parts)
    candidates = [(root.resolve() / relative_path).resolve()]
    if relative.parts[0] != "data":
        candidates.append((data_root / relative_path).resolve())
    path = next(
        (
            candidate
            for candidate in candidates
            if candidate.is_relative_to(data_root) and candidate.is_file()
        ),
        None,
    )
    if path is None:
        raise CatalogNotFoundError(
            "SYMBOL_REFERENCE_ASSET_NOT_FOUND",
            "The approved symbol reference crop is unavailable.",
        )
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise CatalogConflictError(
            "SYMBOL_REFERENCE_ASSET_TYPE_INVALID",
            "The approved symbol reference crop must be a PNG or JPEG file.",
        )
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise CatalogConflictError(
            "SYMBOL_REFERENCE_ASSET_CHECKSUM_MISMATCH",
            "The approved symbol reference crop checksum does not match.",
        )
    return path


__all__ = ["create_symbol_references_router", "resolve_symbol_reference_asset"]
