"""OpenAPI contracts for local V7 numeric-label geometry calibration."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

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


class V7ValidationSourceReferenceRequest(ApiModel):
    source_id: str = Field(min_length=1, max_length=256)
    source_checksum_sha256: Sha256


class V7ValidationSourceObservationRequest(V7ValidationSourceReferenceRequest):
    represented_range_start: int = Field(ge=1)
    represented_range_end: int = Field(ge=1)
    top_cropped: bool
    bottom_cropped: bool

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.represented_range_end < self.represented_range_start:
            raise ValueError("representedRangeEnd must be at least representedRangeStart.")
        return self


class V7ValidationTruthRequest(ApiModel):
    case_id: str = Field(min_length=1, max_length=256)
    corpus_case_id: str = Field(min_length=1, max_length=64)
    split: Literal["development", "calibration", "validation"]
    expected_range_start: int = Field(ge=1)
    expected_range_end: int = Field(ge=1)
    evidence_sources: list[V7ValidationSourceReferenceRequest] = Field(min_length=1)
    acceptable_representative_sources: list[V7ValidationSourceReferenceRequest] = Field(
        default_factory=list
    )
    automatically_recoverable: bool
    eligible_acceptable_representative: bool

    @model_validator(mode="after")
    def validate_truth(self) -> Self:
        if self.expected_range_end < self.expected_range_start:
            raise ValueError("expectedRangeEnd must be at least expectedRangeStart.")
        if self.eligible_acceptable_representative != bool(self.acceptable_representative_sources):
            raise ValueError(
                "eligibleAcceptableRepresentative must match acceptableRepresentativeSources."
            )
        return self


class V7ValidationPredictionSnapshotRequest(ApiModel):
    case_id: str = Field(min_length=1, max_length=256)
    predicted_range_start: int | None = Field(default=None, ge=1)
    predicted_range_end: int | None = Field(default=None, ge=1)
    selected_source: V7ValidationSourceReferenceRequest | None = None
    top_warning: bool
    bottom_warning: bool
    manual_review: bool

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        has_range = self.predicted_range_start is not None or self.predicted_range_end is not None
        if has_range != (self.selected_source is not None):
            raise ValueError("A predicted range requires exactly one selectedSource.")
        if has_range and (self.predicted_range_start is None or self.predicted_range_end is None):
            raise ValueError("A predicted range requires both range boundaries.")
        if (
            has_range
            and self.predicted_range_start is not None
            and self.predicted_range_end is not None
            and self.predicted_range_end < self.predicted_range_start
        ):
            raise ValueError("predictedRangeEnd must be at least predictedRangeStart.")
        if not has_range and (self.top_warning or self.bottom_warning):
            raise ValueError("No selected source requires no warnings.")
        return self


class V7ValidationReportCreate(ApiModel):
    operation_id: SessionId
    profile_fingerprint: Sha256
    source_game_ref: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    truth: list[V7ValidationTruthRequest] = Field(min_length=1)
    source_observations: list[V7ValidationSourceObservationRequest] = Field(min_length=1)
    prediction_snapshots: list[V7ValidationPredictionSnapshotRequest] = Field(min_length=1)


class V7ValidationReportResponse(ApiModel):
    validation_report_fingerprint: Sha256
    profile_fingerprint: Sha256
    observer_fingerprint: Sha256
    geometry_family_id: str = Field(min_length=1)
    source_game_ref: str = Field(min_length=1)
    corpus_manifest_fingerprint: Sha256
    corpus_inventory_fingerprint: Sha256
    acceptance: dict[str, object]
    created: bool


class V7LabelGeometryAdoptionCreate(ApiModel):
    operation_id: SessionId
    profile_fingerprint: Sha256
    source_game_ref: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    validation_report_fingerprint: Sha256


class V7LabelGeometryAdoptionMutationResponse(ApiModel):
    adoption: V7LabelGeometryAdoptionResponse
    created: bool


__all__ = [
    "V7LabelGeometryAdoptionListResponse",
    "V7LabelGeometryAdoptionCreate",
    "V7LabelGeometryAdoptionMutationResponse",
    "V7LabelGeometryAdoptionResponse",
    "V7LabelGeometryProfileListResponse",
    "V7LabelGeometryProfileResponse",
    "V7LabelGeometrySessionCreate",
    "V7LabelGeometrySessionExportRequest",
    "V7LabelGeometrySessionExportResponse",
    "V7LabelGeometrySessionMutation",
    "V7LabelGeometrySessionMutationResponse",
    "V7LabelGeometrySessionResponse",
    "V7ValidationPredictionSnapshotRequest",
    "V7ValidationReportCreate",
    "V7ValidationReportResponse",
    "V7ValidationSourceObservationRequest",
    "V7ValidationSourceReferenceRequest",
    "V7ValidationTruthRequest",
]
