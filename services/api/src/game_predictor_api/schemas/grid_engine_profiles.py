"""OpenAPI schemas of the read-only grid engine profile listing (TASK-0830)."""

from __future__ import annotations

from pydantic import Field

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import GridEngineModelStatus
from game_predictor_api.schemas.catalog import ApiModel


class GridEngineModelFileResponse(ApiModel):
    name: str
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    status: GridEngineModelStatus


class GridEngineReportResultResponse(ApiModel):
    dataset: str
    result: str


class GridEngineProfileResponse(ApiModel):
    configuration: GameShapeGeometryConfiguration
    label: str
    description: str
    model_kind: str
    model_version: str
    version: str
    run_id: str
    export_id: str
    preset: str
    preset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_on: str
    managed_path: str
    status: GridEngineModelStatus
    reason_code: str
    message: str
    manifest_status: GridEngineModelStatus
    files: list[GridEngineModelFileResponse]
    report_results: list[GridEngineReportResultResponse]
