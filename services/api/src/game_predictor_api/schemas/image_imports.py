"""HTTP schemas for controlled local image-folder imports."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from game_predictor_worker.images.lateral_partial_contract import GeometryEngineVariant
from pydantic import Field, StrictInt, field_validator, model_validator

from game_predictor_api.application.browser_staging_retention import (
    BrowserStagingBoardImportStatus,
)
from game_predictor_api.application.image_imports import (
    BrowserReadySelection,
    ImageSelectionPurpose,
    SelectedImageFolder,
)
from game_predictor_api.application.iterative_image_imports import (
    CuratedImageImportProgress,
)
from game_predictor_api.domain.image_import_engine_policy import ImageImportEnginePolicy
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardContext,
    ImageGeometryGuardBoardTarget,
    ImageGeometryGuardDecision,
    ImageGeometryGuardResolutionManifest,
)
from game_predictor_api.domain.image_sequence_canonical import (
    BrowserImageUploadPlan,
    ImageSequenceImportPreflight,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.geometry_qualification import (
    AutomaticPartialGeometryProposalPayload,
    GeometryQualificationPayload,
    ManualSourceGeometryPoint,
)
from game_predictor_api.schemas.jobs import JobResponse


class ImageFolderSelectionResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    selection_token: str | None = None
    path: str | None = None
    supported_file_count: int = 0
    expires_at: datetime | None = None
    purpose: ImageSelectionPurpose | None = None
    input_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @classmethod
    def selected(cls, value: SelectedImageFolder) -> "ImageFolderSelectionResponse":
        return cls(
            status="selected",
            selection_token=value.selection_token,
            path=None if value.managed else str(value.path),
            supported_file_count=value.supported_file_count,
            expires_at=value.expires_at,
            purpose=value.purpose,
            input_manifest_sha256=value.input_manifest_sha256,
        )

    @classmethod
    def cancelled(cls) -> "ImageFolderSelectionResponse":
        return cls(status="cancelled")


class ImageFolderImportResponse(ApiModel):
    job: JobResponse


class ImageSequenceImportPreflightResponse(ApiModel):
    game_id: UUID
    source_file_count: int = Field(ge=0)
    attested_file_count: int = Field(ge=0)
    new_sequence_count: int = Field(ge=0)
    reused_sequence_count: int = Field(ge=0)
    skipped_source_count: int = Field(ge=0)
    partial_source_count: int = Field(ge=0)
    alternative_source_count: int = Field(ge=0)
    first_unresolved_sequence: int | None = Field(default=None, ge=1)
    last_unresolved_sequence: int | None = Field(default=None, ge=1)
    warnings: list[str]

    @classmethod
    def from_domain(
        cls,
        value: ImageSequenceImportPreflight,
    ) -> "ImageSequenceImportPreflightResponse":
        return cls(
            game_id=value.game_id,
            source_file_count=value.source_file_count,
            attested_file_count=value.attested_file_count,
            new_sequence_count=value.new_sequence_count,
            reused_sequence_count=value.reused_sequence_count,
            skipped_source_count=value.skipped_source_count,
            partial_source_count=value.partial_source_count,
            alternative_source_count=value.alternative_source_count,
            first_unresolved_sequence=value.first_unresolved_sequence,
            last_unresolved_sequence=value.last_unresolved_sequence,
            warnings=list(value.warnings),
        )


class BrowserReadySelectionResponse(ApiModel):
    upload_id: UUID
    display_name: str
    expected_file_count: int = Field(ge=1)
    expected_total_bytes: int = Field(ge=1)
    uploaded_file_count: int = Field(ge=0)
    uploaded_bytes: int = Field(ge=0)
    purpose: ImageSelectionPurpose
    game_id: UUID | None
    created_at: datetime
    completed_at: datetime | None
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    superseded_by_upload_id: UUID | None = None
    board_import_status: BrowserStagingBoardImportStatus | None = None

    @classmethod
    def from_domain(cls, value: BrowserReadySelection) -> "BrowserReadySelectionResponse":
        upload = value.upload
        return cls(
            upload_id=upload.upload_id,
            display_name=upload.display_name,
            expected_file_count=upload.expected_file_count,
            expected_total_bytes=upload.expected_total_bytes,
            uploaded_file_count=len(upload.uploaded_indexes),
            uploaded_bytes=upload.uploaded_bytes,
            purpose=upload.purpose,
            game_id=upload.game_id,
            created_at=upload.created_at,
            completed_at=value.completed_at,
            manifest_checksum_sha256=value.manifest.checksum_sha256,
            superseded_by_upload_id=upload.superseded_by_upload_id,
            board_import_status=value.board_import_status,
        )


class BrowserPageSourceReplacementConfirm(ApiModel):
    game_id: UUID
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str = Field(min_length=1, max_length=1000)
    replacement_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BrowserPageSourceReplacementDiscard(ApiModel):
    game_id: UUID


class BrowserImageImportPreflightCreate(ApiModel):
    game_id: UUID
    geometry_engine_variant: GeometryEngineVariant = (
        GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1
    )

    @field_validator("geometry_engine_variant", mode="before")
    @classmethod
    def default_engine(cls, value: object) -> object:
        return value or GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1


class BrowserPageGeometryPreflightCreate(ApiModel):
    game_id: UUID
    page_registration_variant: Literal["standard_v0_10", "board_area_test"] = "standard_v0_10"
    geometry_engine_variant: GeometryEngineVariant = (
        GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1
    )
    managed_source_job_id: UUID | None = None

    @field_validator("geometry_engine_variant", mode="before")
    @classmethod
    def default_engine(cls, value: object) -> object:
        return value or GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1


class BrowserCanonicalRange(ApiModel):
    sequence_range_start: int = Field(ge=1)
    sequence_range_end: int = Field(ge=1)


class BrowserImageImportPreflightResponse(ImageSequenceImportPreflightResponse):
    upload_id: UUID
    display_name: str
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbol_model_ready: bool
    unclassified_cold_start_allowed: bool = False
    symbol_model_blocker_code: (
        Literal[
            "SYMBOL_MODEL_ACTIVATION_REQUIRED",
            "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED",
        ]
        | None
    ) = None
    symbol_model_inference_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    symbol_model_snapshot_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    grid_profile_inference_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_engine_policy: ImageImportEnginePolicy
    image_engine_policy_revision: int = Field(ge=0)
    geometry_preflight_required: bool
    operator_excluded_source_count: int = Field(default=0, ge=0)
    upload_plan_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    skipped_canonical_ranges: list["BrowserCanonicalRange"] = Field(default_factory=list)
    geometry_engine_variant: GeometryEngineVariant | None = None
    geometry_engine_variant_enabled: bool = True
    geometry_engine_variant_blocker_code: str | None = None
    geometry_engine_variant_blocker_message: str | None = None
    page_registration_variant: Literal["standard_v0_10", "board_area_test"] | None = None
    geometry_preflight_job: JobResponse | None = None
    geometry_preflight_artifact_ready: bool = False
    geometry_preflight_artifact_blocker_code: str | None = None
    geometry_preflight_artifact_blocker_message: str | None = None
    existing_import_job: JobResponse | None = None


class BrowserPageGeometryPreflightResponse(ApiModel):
    created: bool
    job: JobResponse


class PageGeometryPoint(ApiModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class ImageGeometryGuardBoardTargetResponse(ApiModel):
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str = Field(min_length=1, max_length=1000)
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    reason_codes: list[str]
    page_geometry: dict[str, object] | None
    analysis_quad: object | None
    proposed_symbol_grid_quad: object | None
    evidence: dict[str, object] | None

    @classmethod
    def from_domain(
        cls, value: ImageGeometryGuardBoardTarget
    ) -> "ImageGeometryGuardBoardTargetResponse":
        return cls(
            source_checksum_sha256=value.source_checksum_sha256,
            source_relative_path=value.source_relative_path,
            position_index=value.position_index,
            sequence_number=value.sequence_number,
            reason_codes=list(value.reason_codes),
            page_geometry=value.page_geometry,
            analysis_quad=value.analysis_quad,
            proposed_symbol_grid_quad=value.proposed_symbol_grid_quad,
            evidence=value.evidence,
        )


class ImageGeometryGuardBoardContextResponse(ApiModel):
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str = Field(min_length=1, max_length=1000)
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    reason_codes: list[str]
    page_geometry: dict[str, object] | None
    analysis_quad: object | None
    symbol_grid_quad: object | None
    evidence: dict[str, object] | None
    requires_decision: bool

    @classmethod
    def from_domain(
        cls, value: ImageGeometryGuardBoardContext
    ) -> "ImageGeometryGuardBoardContextResponse":
        return cls(
            source_checksum_sha256=value.source_checksum_sha256,
            source_relative_path=value.source_relative_path,
            position_index=value.position_index,
            sequence_number=value.sequence_number,
            reason_codes=list(value.reason_codes),
            page_geometry=value.page_geometry,
            analysis_quad=value.analysis_quad,
            symbol_grid_quad=value.symbol_grid_quad,
            evidence=value.evidence,
            requires_decision=value.requires_decision,
        )


class ImageGeometryGuardDecisionResponse(ApiModel):
    id: UUID
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    revision: int = Field(ge=1)
    disposition: Literal["corrected_full", "partial", "rejected"]
    symbol_grid_quad: list[ManualSourceGeometryPoint] | None
    unavailable_cell_indices: list[int]
    reason: str | None
    actor: str
    decision_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    geometry_qualification: GeometryQualificationPayload | None = None

    @classmethod
    def from_domain(cls, value: ImageGeometryGuardDecision) -> "ImageGeometryGuardDecisionResponse":
        return cls(
            id=value.id,
            source_checksum_sha256=value.source_checksum_sha256,
            source_relative_path=value.source_relative_path,
            position_index=value.position_index,
            sequence_number=value.sequence_number,
            revision=value.revision,
            disposition=value.disposition.value,
            symbol_grid_quad=(
                None
                if value.symbol_grid_quad is None
                else [ManualSourceGeometryPoint(**point) for point in value.symbol_grid_quad]
            ),
            unavailable_cell_indices=list(value.unavailable_cell_indices),
            geometry_qualification=(
                None
                if value.geometry_qualification is None
                else GeometryQualificationPayload.model_validate(
                    value.geometry_qualification.to_client_dict()
                )
            ),
            reason=value.reason,
            actor=value.actor,
            decision_checksum_sha256=value.decision_checksum_sha256,
            created_at=value.created_at,
        )


class ImageGeometryGuardResolutionManifestResponse(ApiModel):
    id: UUID
    guard_job_id: UUID
    guard_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_geometry_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_relative_path: str
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_count: int = Field(ge=1)
    sealed_by: str
    created_at: datetime

    @classmethod
    def from_domain(
        cls, value: ImageGeometryGuardResolutionManifest
    ) -> "ImageGeometryGuardResolutionManifestResponse":
        return cls(
            id=value.id,
            guard_job_id=value.guard_job_id,
            guard_report_checksum_sha256=value.guard_report_checksum_sha256,
            source_manifest_checksum_sha256=value.source_manifest_checksum_sha256,
            page_geometry_manifest_checksum_sha256=(value.page_geometry_manifest_checksum_sha256),
            manifest_relative_path=value.manifest_relative_path,
            manifest_checksum_sha256=value.manifest_checksum_sha256,
            decision_count=value.decision_count,
            sealed_by=value.sealed_by,
            created_at=value.created_at,
        )


class ImageGeometryGuardQueueResponse(ApiModel):
    game_id: UUID
    browser_selection_id: UUID
    guard_job_id: UUID
    guard_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_geometry_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    unresolved_count: int = Field(ge=0)
    boards: list[ImageGeometryGuardBoardContextResponse]
    targets: list[ImageGeometryGuardBoardTargetResponse]
    decisions: list[ImageGeometryGuardDecisionResponse]
    page_geometry_preflight_job: JobResponse | None
    current_resolution_manifest: ImageGeometryGuardResolutionManifestResponse | None


class ImageGeometryGuardDecisionItemCreate(ApiModel):
    expected_decision_revision: int | None = Field(default=None, ge=0)
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_index: int = Field(ge=0, le=8)
    sequence_number: int = Field(ge=1)
    disposition: Literal["corrected_full", "partial", "rejected"]
    symbol_grid_quad: (
        tuple[
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
        ]
        | None
    ) = None
    unavailable_cell_indices: list[int] = Field(default_factory=list, max_length=15)
    geometry_qualification: GeometryQualificationPayload | None = None
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_qualification_for_signed_quad(self) -> "ImageGeometryGuardDecisionItemCreate":
        if self.symbol_grid_quad is not None:
            _validate_guard_signed_quad(self.symbol_grid_quad, self.geometry_qualification)
        return self


class ImageGeometryGuardDecisionBatchCreate(ApiModel):
    game_id: UUID
    expected_guard_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1, max_length=200)
    decisions: list[ImageGeometryGuardDecisionItemCreate] = Field(min_length=1, max_length=9)


class ImageGeometryGuardDecisionBatchResponse(ApiModel):
    decisions: list[ImageGeometryGuardDecisionResponse]


class ImageGeometryGuardPreviewCreate(ApiModel):
    game_id: UUID
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_index: int = Field(ge=0, le=8)
    symbol_grid_quad: tuple[
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
        ManualSourceGeometryPoint,
    ]
    unavailable_cell_indices: list[int] = Field(default_factory=list, max_length=15)
    geometry_qualification: GeometryQualificationPayload | None = None

    @model_validator(mode="after")
    def require_qualification_for_empty_preview(self) -> "ImageGeometryGuardPreviewCreate":
        _validate_guard_signed_quad(self.symbol_grid_quad, self.geometry_qualification)
        if len(self.unavailable_cell_indices) == 15 and self.geometry_qualification is None:
            raise ValueError("All-missing preview requires geometry qualification.")
        return self


def _validate_guard_signed_quad(
    points: tuple[ManualSourceGeometryPoint, ...],
    qualification: GeometryQualificationPayload | None,
) -> None:
    if any(point.x < 0 or point.y < 0 for point in points) and (
        qualification is None or qualification.completeness_status != "pending_partial"
    ):
        raise ValueError("Signed corners require explicitly partial geometry.")


class ImageGeometryGuardCellPreviewResponse(ApiModel):
    cell_index: int = Field(ge=0, le=14)
    source_unavailable: bool
    current_data_url: str | None
    proposed_data_url: str | None


class ImageGeometryGuardPreviewResponse(ApiModel):
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    cells: list[ImageGeometryGuardCellPreviewResponse] = Field(min_length=15, max_length=15)


class ImageGeometryGuardReportReconstructionCreate(ApiModel):
    game_id: UUID


class ImageGeometryGuardReportReconstructionResponse(ApiModel):
    created: bool
    job: JobResponse


class ImageGeometryGuardManifestSealCreate(ApiModel):
    game_id: UUID
    expected_guard_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1, max_length=200)


class PageGeometryRegistrationAttemptDiagnostic(ApiModel):
    reason_code: str = Field(min_length=1, max_length=128)
    feature_count: int = Field(ge=0, le=10000)
    anchor_source_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    target_feature_count: int | None = Field(default=None, ge=0)
    match_count: int | None = Field(default=None, ge=0)
    inlier_count: int | None = Field(default=None, ge=0)
    inlier_ratio: float | None = Field(default=None, ge=0, le=1)
    p95_reprojection_error: float | None = Field(default=None, ge=0)
    mean_red_edge_coverage: float | None = Field(default=None, ge=0, le=1)
    minimum_board_red_edge_coverage: float | None = Field(default=None, ge=0, le=1)


class PageGeometryRegistrationDiagnostics(ApiModel):
    version: Literal["page-registration-diagnostics-v1"]
    best_attempt: PageGeometryRegistrationAttemptDiagnostic | None = None
    attempts: list[PageGeometryRegistrationAttemptDiagnostic] = Field(max_length=3)


class AutomaticPageGeometryProposalPayload(ApiModel):
    """Read-only editor prefill hint; never a materialized decision."""

    origin: Literal[
        "lateral_source_support", "frame_support_review", "standalone_frame_lines"
    ]
    quads: list[list[ManualSourceGeometryPoint]] = Field(min_length=1, max_length=9)
    review_slots: list[Annotated[StrictInt, Field(ge=0, le=8)]] = Field(
        default_factory=list, max_length=9
    )


class BrowserPageGeometryReviewSourceResponse(ApiModel):
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str = Field(min_length=1, max_length=2048)
    sequence_range_start: int | None = Field(default=None, ge=1)
    sequence_range_end: int | None = Field(default=None, ge=1)
    expected_board_count: int = Field(ge=1, le=9)
    review_reason: Literal[
        "manual_override", "review_required", "operator_inspection"
    ] = "review_required"
    geometry_origin: Literal["automatic", "manual_override", "manual_template"]
    rejection_reason_code: str | None = Field(default=None, min_length=1, max_length=128)
    registration_diagnostics: PageGeometryRegistrationDiagnostics | None = None
    existing_final_quads: list[list[ManualSourceGeometryPoint]] | None = None
    existing_board_frame_quads: list[list[ManualSourceGeometryPoint]] | None = None
    existing_symbol_grid_quads: list[list[ManualSourceGeometryPoint]] | None = None
    existing_override_revision: int | None = Field(default=None, ge=1)
    existing_slot_qualifications: list[GeometryQualificationPayload] | None = None
    saved_since_preflight: bool = False
    automatic_partial_proposals: list[AutomaticPartialGeometryProposalPayload] | None = Field(
        default=None, max_length=9, exclude_if=lambda value: value is None
    )
    automatic_page_proposal: AutomaticPageGeometryProposalPayload | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class BrowserPageGeometryReviewSourcesResponse(ApiModel):
    job: JobResponse
    geometry_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_source_count: int = Field(ge=0)
    review_required_source_count: int = Field(ge=0)
    skipped_human_resolved_source_count: int = Field(ge=0)
    operator_excluded_source_count: int = Field(default=0, ge=0)
    partial_grid_training_sample_count: int = Field(default=0, ge=0)
    partial_grid_training_source_count: int = Field(default=0, ge=0)
    partial_grid_ready_pattern_count: int = Field(default=0, ge=0)
    sources: list[BrowserPageGeometryReviewSourceResponse]


class BrowserPageGeometryOverrideCreate(ApiModel):
    expected_override_revision: int | None = Field(default=None, ge=0)
    game_id: UUID
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    final_quads: list[
        tuple[
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
        ]
    ] = Field(min_length=1, max_length=9)
    actor: str = Field(min_length=1, max_length=200)
    slot_qualifications: list[GeometryQualificationPayload] | None = Field(
        default=None, min_length=1, max_length=9
    )
    board_frame_quads: list[
        tuple[
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
        ]
    ] | None = Field(default=None, min_length=1, max_length=9)
    symbol_grid_quads: list[
        tuple[
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
            ManualSourceGeometryPoint,
        ]
    ] | None = Field(default=None, min_length=1, max_length=9)

    @model_validator(mode="after")
    def require_complete_v12_pair(self) -> "BrowserPageGeometryOverrideCreate":
        if (self.board_frame_quads is None) != (self.symbol_grid_quads is None):
            raise ValueError("V1.2 requires both boardFrameQuads and symbolGridQuads.")
        if self.symbol_grid_quads is not None and self.final_quads != self.symbol_grid_quads:
            raise ValueError("finalQuads must equal symbolGridQuads for V1.2.")
        return self


class BrowserPageGeometryOverrideResponse(ApiModel):
    created: bool
    id: UUID
    revision: int = Field(ge=1)
    decision_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_qualifications: list[GeometryQualificationPayload] | None = None


class BrowserPageSourceExclusionCreate(ApiModel):
    game_id: UUID
    geometry_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_relative_path: str = Field(min_length=1, max_length=1000)
    actor: str = Field(min_length=1, max_length=200)


class BrowserPageSourceExclusionResponse(ApiModel):
    created: bool
    id: UUID
    decision_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_excluded_source_count: int = Field(ge=1)


class BrowserImageImportStart(ApiModel):
    geometry_engine_variant: GeometryEngineVariant = Field(
        default=GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1,
        description="Engine pinned for this import; defaults to v1.1.",
    )

    @field_validator("geometry_engine_variant", mode="before")
    @classmethod
    def default_engine(cls, value: object) -> object:
        return value or GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1

    game_id: UUID
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_mode: Literal["reuse_exact", "rerun_current_models"] = "reuse_exact"
    symbol_model_inference_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    symbol_model_snapshot_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    grid_profile_inference_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    geometry_preflight_job_id: UUID | None = None
    geometry_manifest_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    geometry_guard_resolution_manifest_id: UUID | None = None
    geometry_guard_resolution_manifest_checksum_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    board_cell_processing_mode: (
        Literal[
            "verified_v19",
            "structured_shadow",
            "structured_default",
            "structured_lattice_v3",
        ]
        | None
    ) = None
    image_engine_policy: ImageImportEnginePolicy | None = None
    image_engine_policy_revision: int | None = Field(default=None, ge=0)


class BrowserImageImportStartResponse(ApiModel):
    created: bool
    job: JobResponse
    preflight: BrowserImageImportPreflightResponse


class BrowserImageSelectionCreate(ApiModel):
    display_name: str = Field(min_length=1, max_length=200)
    expected_file_count: int = Field(ge=1, le=1_000_000)
    expected_total_bytes: int = Field(ge=1)
    purpose: ImageSelectionPurpose = ImageSelectionPurpose.LAYOUT_IMPORT
    game_id: UUID | None = None
    upload_plan_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    skipped_canonical_ranges: list[BrowserCanonicalRange] = Field(
        default_factory=list,
        max_length=1_000_000,
    )


class BrowserImageUploadPlanSourceCreate(ApiModel):
    source_index: int = Field(ge=0, le=999_999)
    relative_path: str = Field(min_length=1, max_length=1000)
    size_bytes: int = Field(ge=1)


class BrowserImageUploadPlanCreate(ApiModel):
    game_id: UUID
    files: list[BrowserImageUploadPlanSourceCreate] = Field(
        min_length=1,
        max_length=1_000_000,
    )


class BrowserImageUploadPlanFileResponse(ApiModel):
    source_index: int = Field(ge=0)
    upload_index: int = Field(ge=0)
    relative_path: str
    size_bytes: int = Field(ge=1)


class BrowserImageUploadPlanSkippedSourceResponse(ApiModel):
    source_index: int = Field(ge=0)
    relative_path: str
    sequence_range_start: int = Field(ge=1)
    sequence_range_end: int = Field(ge=1)


class BrowserImageUploadPlanResponse(ApiModel):
    game_id: UUID
    plan_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_file_count: int = Field(ge=0)
    selected_total_bytes: int = Field(ge=0)
    upload_file_count: int = Field(ge=0)
    upload_total_bytes: int = Field(ge=0)
    skipped_complete_source_count: int = Field(ge=0)
    reused_sequence_count: int = Field(ge=0)
    missing_sequence_count: int = Field(ge=0)
    partial_source_count: int = Field(ge=0)
    files_to_upload: list[BrowserImageUploadPlanFileResponse]
    skipped_complete_sources: list[BrowserImageUploadPlanSkippedSourceResponse]

    @classmethod
    def from_domain(cls, value: BrowserImageUploadPlan) -> "BrowserImageUploadPlanResponse":
        preflight = value.preflight
        return cls(
            game_id=value.game_id,
            plan_checksum_sha256=value.plan_checksum_sha256,
            selected_file_count=preflight.source_file_count,
            selected_total_bytes=value.selected_total_bytes,
            upload_file_count=len(value.files_to_upload),
            upload_total_bytes=value.upload_total_bytes,
            skipped_complete_source_count=preflight.skipped_source_count,
            reused_sequence_count=preflight.reused_sequence_count,
            missing_sequence_count=preflight.new_sequence_count,
            partial_source_count=preflight.partial_source_count,
            files_to_upload=[
                BrowserImageUploadPlanFileResponse(
                    source_index=item.source_index,
                    upload_index=index,
                    relative_path=item.relative_path,
                    size_bytes=item.size_bytes,
                )
                for index, item in enumerate(value.files_to_upload)
            ],
            skipped_complete_sources=[
                BrowserImageUploadPlanSkippedSourceResponse(
                    source_index=item.source_index,
                    relative_path=item.relative_path,
                    sequence_range_start=item.sequence_range_start,
                    sequence_range_end=item.sequence_range_end,
                )
                for item in value.skipped_complete_sources
            ],
        )


class BrowserImageSelectionUploadResponse(ApiModel):
    upload_id: UUID
    expected_file_count: int
    uploaded_file_count: int
    uploaded_file_indexes: list[int]
    expected_total_bytes: int
    uploaded_bytes: int
    purpose: ImageSelectionPurpose
    game_id: UUID | None


class BrowserImageSelectionFileUploadResponse(ApiModel):
    upload_id: UUID
    expected_file_count: int
    uploaded_file_count: int
    expected_total_bytes: int
    uploaded_bytes: int


class CuratedImageImportSourceCreate(ApiModel):
    game_id: UUID
    image_selection_run_id: UUID


class CuratedImageImportBatchCreate(ApiModel):
    image_count: int = Field(default=10, ge=1, le=100_000)


class CuratedImageImportBatchResponse(ApiModel):
    id: UUID
    batch_number: int
    start_index: int
    end_index: int
    image_count: int
    job: JobResponse
    created_at: datetime


class CuratedImageImportSourceResponse(ApiModel):
    id: UUID
    game_id: UUID
    image_selection_run_id: UUID
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_entries: int
    reserved_entries: int
    processed_entries: int
    failed_entries: int
    remaining_entries: int
    next_entry_index: int
    batches: list[CuratedImageImportBatchResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        progress: CuratedImageImportProgress,
    ) -> "CuratedImageImportSourceResponse":
        source = progress.source
        return cls(
            id=source.id,
            game_id=source.game_id,
            image_selection_run_id=source.image_selection_run_id,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
            total_entries=source.total_entries,
            reserved_entries=progress.reserved_entries,
            processed_entries=progress.processed_entries,
            failed_entries=progress.failed_entries,
            remaining_entries=progress.remaining_entries,
            next_entry_index=source.next_entry_index,
            batches=[
                CuratedImageImportBatchResponse(
                    id=batch.id,
                    batch_number=batch.batch_number,
                    start_index=batch.start_index,
                    end_index=batch.end_index,
                    image_count=batch.image_count,
                    job=JobResponse.from_domain(batch.job),
                    created_at=batch.created_at,
                )
                for batch in progress.batches
            ],
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
