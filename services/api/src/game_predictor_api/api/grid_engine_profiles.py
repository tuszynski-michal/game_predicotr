"""Read-only HTTP view of the grid engine profiles and their managed models."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from game_predictor_api.application.grid_engine_profiles import (
    GridEngineProfileService,
    GridEngineProfileView,
)
from game_predictor_api.schemas.grid_engine_profiles import (
    GridEngineModelFileResponse,
    GridEngineProfileResponse,
    GridEngineReportResultResponse,
)
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore


def create_grid_engine_profiles_router(artifact_root: Path) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["grid-engine-profiles"])
    service = GridEngineProfileService(ManagedGridEngineModelStore(artifact_root))

    @router.get(
        "/grid-engine-profiles",
        response_model=list[GridEngineProfileResponse],
        operation_id="listGridEngineProfiles",
        summary="List grid engine profiles and the state of their models",
    )
    def list_grid_engine_profiles() -> list[GridEngineProfileResponse]:
        return [_to_response(view) for view in service.list_profiles()]

    return router


def _to_response(view: GridEngineProfileView) -> GridEngineProfileResponse:
    version = view.model.version
    return GridEngineProfileResponse(
        configuration=view.profile.configuration,
        label=view.profile.label,
        description=view.profile.description,
        model_kind=version.model_kind,
        model_version=version.model_version,
        version=version.version,
        run_id=version.run_id,
        export_id=version.export_id,
        preset=version.preset_name,
        preset_fingerprint=version.preset_fingerprint,
        weights_sha256=version.weights_sha256,
        frozen_on=version.frozen_on,
        managed_path=version.relative_directory.as_posix(),
        status=view.model.status,
        reason_code=view.model.reason_code,
        message=view.model.message,
        manifest_status=view.model.manifest_status,
        files=[
            GridEngineModelFileResponse(
                name=state.file.name,
                expected_sha256=state.file.sha256,
                size_bytes=state.file.size_bytes,
                status=state.status,
            )
            for state in view.model.files
        ],
        report_results=[
            GridEngineReportResultResponse(dataset=result.dataset, result=result.result)
            for result in version.report_results
        ],
    )
