"""OpenAPI contracts for local V7 numeric-label geometry calibration."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SessionId = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


class V7LabelGeometrySessionCreate(ApiModel):
    geometry_family_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    corpus_case_ids: list[str] = Field(min_length=1, max_length=100)


class V7LabelGeometrySessionSourceResponse(ApiModel):
    source_id: str = Field(min_length=1)
    source_checksum_sha256: Sha256
    corpus_case_id: str = Field(min_length=1)
    split: Literal["calibration"]
    geometry_family_id: str = Field(min_length=1)


class V7LabelGeometrySlotResponse(ApiModel):
    source_id: str = Field(min_length=1)
    position_index: int = Field(ge=0, le=8)
    state: Literal["unreviewed", "annotated", "unavailable"]
    center_x: float | None = Field(default=None, gt=0, lt=1)
    center_y: float | None = Field(default=None, gt=0, lt=1)
    crop_assessment: Literal["contained", "clipped", "uncertain"] | None = None


class V7LabelGeometryReceiptResponse(ApiModel):
    operation_id: SessionId
    operation_fingerprint: Sha256
    revision: int = Field(ge=1)


class V7LabelGeometrySessionResponse(ApiModel):
    session_id: SessionId
    revision: int = Field(ge=0)
    manifest_fingerprint: Sha256
    geometry_family_id: str = Field(min_length=1)
    status: Literal["active", "blocked_source_drift"]
    sources: list[V7LabelGeometrySessionSourceResponse]
    slots: list[V7LabelGeometrySlotResponse]
    capture_groups: dict[str, str]


class V7LabelGeometrySessionMutation(ApiModel):
    operation_id: SessionId
    expected_revision: int = Field(ge=0)
    kind: Literal["annotated", "unavailable", "set_capture_group"]
    source_id: str = Field(min_length=1)
    position_index: int | None = Field(default=None, ge=0, le=8)
    center_x: float | None = Field(default=None, gt=0, lt=1)
    center_y: float | None = Field(default=None, gt=0, lt=1)
    crop_assessment: Literal["contained", "clipped", "uncertain"] | None = None
    capture_group_id: str | None = Field(default=None, min_length=1, max_length=128)


class V7LabelGeometrySessionMutationResponse(ApiModel):
    session: V7LabelGeometrySessionResponse
    receipt: V7LabelGeometryReceiptResponse


class V7LabelGeometrySessionExportRequest(ApiModel):
    expected_revision: int = Field(ge=0)


class V7LabelGeometrySessionExportResponse(ApiModel):
    export_checksum_sha256: Sha256
    revision: int = Field(ge=0)


class V7LabelGeometryProfileResponse(ApiModel):
    profile_fingerprint: Sha256
    revision: int = Field(ge=0)
    session_export_checksum_sha256: Sha256
    calibration: dict[str, object]


class V7LabelGeometryProfileListResponse(ApiModel):
    items: list[V7LabelGeometryProfileResponse]


class V7LabelGeometryAdoptionResponse(ApiModel):
    adoption_key: str = Field(min_length=1)
    source_game_ref: str = Field(min_length=1)
    geometry_family_id: str = Field(min_length=1)
    profile_fingerprint: Sha256
    validation_report_fingerprint: Sha256


class V7LabelGeometryAdoptionListResponse(ApiModel):
    items: list[V7LabelGeometryAdoptionResponse]


__all__ = [
    "V7LabelGeometryAdoptionListResponse",
    "V7LabelGeometryAdoptionResponse",
    "V7LabelGeometryProfileListResponse",
    "V7LabelGeometryProfileResponse",
    "V7LabelGeometrySessionCreate",
    "V7LabelGeometrySessionExportRequest",
    "V7LabelGeometrySessionExportResponse",
    "V7LabelGeometrySessionMutation",
    "V7LabelGeometrySessionMutationResponse",
    "V7LabelGeometrySessionResponse",
]
