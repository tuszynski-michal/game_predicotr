"""Typed additive review/command metadata for the existing selection API."""

from typing import Annotated, Literal
from uuid import UUID

from game_predictor_worker.semi_automatic_selection.v7_quality import (
    V7BlurSeverity,
    V7BoardReadability,
    V7BoardVisibility,
    V7DecorationVisibility,
    V7OcclusionSeverity,
    V7QualityWarning,
    V7SymbolContentLoss,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import V7RangeProofKind
from pydantic import Field, model_validator

from game_predictor_api.domain.v7_selection_delivery import V7CorrectionReason, V7OutputDecision
from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class V7PilotSnapshotResponse(ApiModel):
    geometry_family_id: str
    source_game_ref: str | None
    source_policy: Literal["exact_sources", "operator_selected_local_folder"] = "exact_sources"
    profile_fingerprint: Sha256
    observer_fingerprint: Sha256
    ocr_model_fingerprint: Sha256
    pilot_generation: int = Field(ge=0, strict=True)
    binding_fingerprint: Sha256
    receipt_fingerprint: Sha256


class V7ConfirmedRange(ApiModel):
    start: int = Field(ge=1, strict=True)
    end: int = Field(ge=1, strict=True)


class V7LabelSlotResponse(ApiModel):
    position_index: int = Field(ge=0, le=8)
    state: Literal["not_observed", "observed_without_number", "recognized"]
    sequence_number: int | None = Field(default=None, ge=1)
    recognition_confidence: float | None = Field(default=None, ge=0, le=1)
    position_confidence: float | None = Field(default=None, ge=0, le=1)
    visibility: V7BoardVisibility
    readability: V7BoardReadability
    blur: V7BlurSeverity
    occlusion: V7OcclusionSeverity
    symbol_content_loss: V7SymbolContentLoss
    decoration: V7DecorationVisibility


class V7SourceProofResponse(ApiModel):
    kind: V7RangeProofKind
    range_start: int | None = None
    range_end: int | None = None
    supporting_source_ids: list[str]
    reason_codes: list[str]


class V7SourceDiagnosticsResponse(ApiModel):
    version: Literal["v7-source-diagnostics-v1"]
    source_index: int = Field(ge=0)
    source_id: Sha256
    source_checksum_sha256: Sha256
    source_error_code: str | None = None
    slots: list[V7LabelSlotResponse] = Field(min_length=9, max_length=9)
    proof: V7SourceProofResponse


class V7ProvenSourceResponse(ApiModel):
    source_index: int = Field(ge=0)
    source_id: Sha256
    proof_kind: V7RangeProofKind
    supporting_source_ids: list[str]
    occurrence_id: str
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)


class V7ReviewCandidateResponse(ApiModel):
    source_index: int = Field(ge=0)
    source_id: Sha256
    diagnostics: V7SourceDiagnosticsResponse | None = None
    proof_kinds: list[V7RangeProofKind]
    warnings: list[V7QualityWarning]


class V7DraftResponse(ApiModel):
    source_index: int = Field(ge=0)
    source_checksum_sha256: Sha256
    estimated: bool
    reason: str
    directory: str


class V7ReviewResponse(ApiModel):
    version: Literal["v7-review-projection-v1"]
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)
    candidate: V7ReviewCandidateResponse | None
    proven_sources: list[V7ProvenSourceResponse]
    occurrence_id: str | None
    manual_confirmation_required: Literal[True]
    source_manifest_fingerprint: Sha256
    draft: V7DraftResponse | None = None


class V7OutputOperationResponse(ApiModel):
    operation_id: UUID
    state: Literal["reserved", "recovery_required", "committed", "conflict", "failed"]
    decision_generation: int = Field(ge=0)
    source_index: int = Field(ge=0)
    confirmed_range: V7ConfirmedRange
    error_code: str | None = None


class V7OutputReceiptResponse(ApiModel):
    operation_id: UUID
    state: Literal["committed", "conflict", "failed"]
    source_index: int = Field(ge=0)
    source_checksum_sha256: Sha256
    confirmed_range: V7ConfirmedRange
    target_name: str
    owner_operation_id: UUID | None
    decision_generation: int = Field(ge=0)
    output_checksum_sha256: Sha256 | None
    error_code: str | None


class V7OutputDecisionRequest(ApiModel):
    workflow_mode: Literal["v7_selection"]
    operation_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    source_index: int = Field(ge=0, strict=True)
    expected_source_checksum_sha256: Sha256
    kind: Literal["manual_first", "manual_no_ocr", "manual_replace"]
    confirmed_range: V7ConfirmedRange
    operator_confirmed_range: bool = Field(strict=True)
    operator_confirmed_incomplete_page: bool = Field(default=False, strict=True)
    expected_target_checksum_sha256: Sha256 | None = None
    expected_owner_operation_id: UUID | None = None
    correction_reason: V7CorrectionReason | None = None

    @model_validator(mode="after")
    def validate_command_shape(self) -> "V7OutputDecisionRequest":
        if not 1 <= self.confirmed_range.end - self.confirmed_range.start + 1 <= 9:
            raise ValueError("Confirmed range must contain 1–9 consecutive boards.")
        if self.kind == "manual_replace":
            if (
                self.expected_target_checksum_sha256 is None
                or self.expected_owner_operation_id is None
            ):
                raise ValueError("Replace needs the current owner and target checksum.")
        elif (
            self.expected_target_checksum_sha256 is not None
            or self.expected_owner_operation_id is not None
        ):
            raise ValueError("Only replace accepts a previous owner.")
        return self

    def to_domain(self) -> V7OutputDecision:
        return V7OutputDecision(
            self.operation_id,
            self.expected_revision,
            self.source_index,
            self.expected_source_checksum_sha256,
            self.kind,
            self.confirmed_range.start,
            self.confirmed_range.end,
            self.operator_confirmed_range,
            self.operator_confirmed_incomplete_page,
            self.expected_target_checksum_sha256,
            self.expected_owner_operation_id,
            self.correction_reason,
        )
