"""OpenAPI schemas for durable administrative jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self, cast
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.application.jobs import ImageSelectionJobDeletion
from game_predictor_api.application.semi_automatic_image_selections import (
    workflow_mode_for_recognizer_fingerprint,
)
from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.schemas.catalog import ApiModel


class ImportJobCreatePayload(ApiModel):
    schema_version: Literal[1] = 1
    source_path: str = Field(min_length=1, max_length=500)
    contract_version: Literal[1] = 1


class ImportJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    import_kind: Literal["layout_file"]
    source_path: str = Field(min_length=1, max_length=500)
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(ge=1)
    file_format: Literal["csv", "jsonl"]
    contract_version: Literal[1]


class LegacyImageImportJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    import_kind: Literal["image_directory"]
    source_selection_id: UUID | None = None
    source_directory: str | None = Field(default=None, min_length=1, max_length=2048)
    source_display_name: str | None = Field(default=None, min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_selection_run_id: UUID | None = None


class SymbolModelJobSnapshotPayload(ApiModel):
    iteration_id: UUID | None = None
    model_version: str = Field(min_length=1, max_length=255)
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    onnx_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    onnx_relative_path: str = Field(min_length=1, max_length=2048)
    storage_root: Literal["repository", "artifact"]
    class_codes: tuple[str, ...] = Field(min_length=1)
    input_size: int = Field(ge=16)
    temperature: float = Field(gt=0)
    inference_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class BoardCellProcessingJobSnapshotPayload(ApiModel):
    activation_version: Literal["board-cell-processing-v20-verified-v19-v1"]
    audit_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cropper_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cropper_version: str = Field(min_length=1, max_length=255)
    estimator_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimator_version: str = Field(min_length=1, max_length=255)
    geometry_version: str = Field(min_length=1, max_length=255)
    homography_version: str = Field(min_length=1, max_length=255)
    locator_version: str = Field(min_length=1, max_length=255)
    rollout_mode: Literal["explicit_job_only", "default_v19"]
    shadow_benchmark_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thresholds_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thresholds_version: str = Field(min_length=1, max_length=255)
    grid_rows: int | None = Field(default=None, ge=1, le=32767)
    grid_columns: int | None = Field(default=None, ge=1, le=32767)
    topology_rules_version_id: UUID | None = None
    topology_fingerprint_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_topology_snapshot(self) -> Self:
        values = (
            self.grid_rows,
            self.grid_columns,
            self.topology_rules_version_id,
            self.topology_fingerprint_sha256,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("pinned board topology fields must be complete")
        return self


class StructuredGeometryCandidateJobSnapshotPayload(ApiModel):
    schema_version: Literal["structured-geometry-candidate-snapshot-v1"]
    config_version: str = Field(min_length=1, max_length=255)
    config_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config: dict[str, object]


class StructuredGeometryActivationJobSnapshotPayload(ApiModel):
    schema_version: Literal["structured-geometry-activation-snapshot-v1"]
    config_version: str = Field(min_length=1, max_length=255)
    config_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config: dict[str, object]


class ImageGeometryRolloutJobSnapshotPayload(ApiModel):
    schema_version: Literal[
        "virtual-geometry-rollout-snapshot-v1",
        "virtual-geometry-rollout-snapshot-v2",
        "virtual-geometry-rollout-snapshot-v3",
    ]
    geometry_mode: Literal[
        "legacy",
        "structured_shadow",
        "structured_review",
        "structured_default",
        "structured_lattice_v3",
    ]
    cell_asset_mode: Literal[
        "legacy_files",
        "virtual_shadow",
        "virtual_default",
    ]
    geometry_engine_version: str = Field(min_length=1, max_length=255)
    virtual_renderer_version: str = Field(min_length=1, max_length=255)
    preprocessing_version: str = Field(min_length=1, max_length=255)
    rollout_revision: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_geometry: StructuredGeometryCandidateJobSnapshotPayload | None = None
    active_lattice_geometry: StructuredGeometryActivationJobSnapshotPayload | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def validate_candidate_geometry_scope(self) -> Self:
        has_candidate = self.candidate_geometry is not None
        if has_candidate != (self.schema_version == "virtual-geometry-rollout-snapshot-v2"):
            raise ValueError("rollout snapshot v2 requires one candidate geometry config")
        if has_candidate and self.geometry_mode != "structured_shadow":
            raise ValueError("candidate geometry config is allowed only in structured shadow")
        has_activation = self.active_lattice_geometry is not None
        if has_activation != (self.schema_version == "virtual-geometry-rollout-snapshot-v3"):
            raise ValueError("rollout snapshot v3 requires one active lattice config")
        if has_activation and self.geometry_mode != "structured_lattice_v3":
            raise ValueError("active lattice config is allowed only in structured lattice v3")
        return self


class ImageImportJobPayload(ApiModel):
    schema_version: Literal[2]
    import_kind: Literal["image_directory"]
    source_selection_id: UUID | None = None
    source_directory: str | None = Field(default=None, min_length=1, max_length=2048)
    source_display_name: str | None = Field(default=None, min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_adapter_version: str | None = Field(default=None, max_length=150)
    image_selection_run_id: UUID | None = None
    canonical_sequence_numbers: tuple[int, ...] = Field(default=())
    source_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    symbol_model: SymbolModelJobSnapshotPayload
    board_cell_processing: BoardCellProcessingJobSnapshotPayload | None = None
    image_geometry_rollout: ImageGeometryRolloutJobSnapshotPayload | None = None


class GridProfileJobSnapshotPayload(ApiModel):
    profile_id: UUID | None = None
    profile_version: str = Field(min_length=1, max_length=255)
    profile_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_id: UUID | None = None
    profile_payload: dict[str, object]
    page_registration_profile: dict[str, object] | None = None
    inference_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PageGeometryManifestJobPayload(ApiModel):
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=2048)
    preflight_job_id: UUID


class ImageGeometrySystemicGuardPolicyJobPayload(ApiModel):
    policy_version: Literal["image-geometry-systemic-guard-v1"]
    minimum_source_count: Literal[100]
    minimum_active_board_count: Literal[500]
    sample_source_limit: Literal[25]
    minimum_final_cell_grid_ready_rate: Literal[0.98]
    require_zero_invariant_violations: Literal[True]


class ImageGeometryGuardResolutionManifestJobPayload(ApiModel):
    id: UUID
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=2048)
    guard_job_id: UUID
    guard_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_geometry_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BrowserImageImportJobPayload(ApiModel):
    schema_version: Literal[5]
    import_kind: Literal["image_directory"]
    source_selection_id: UUID
    source_directory: str = Field(min_length=1, max_length=2048)
    source_display_name: str = Field(min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_adapter_version: str | None = Field(default=None, max_length=150)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_sequence_numbers: tuple[int, ...] = Field(default=())
    start_mode: Literal["reuse_exact", "rerun_current_models"]
    previous_job_id: UUID | None = None
    image_selection_run_id: UUID | None = None
    symbol_model: SymbolModelJobSnapshotPayload
    grid_profile: GridProfileJobSnapshotPayload
    page_geometry_manifest: PageGeometryManifestJobPayload | None = None
    board_cell_processing: BoardCellProcessingJobSnapshotPayload | None = None
    image_geometry_rollout: ImageGeometryRolloutJobSnapshotPayload | None = None
    geometry_systemic_guard_policy: ImageGeometrySystemicGuardPolicyJobPayload | None = None


class ResolvedBrowserImageImportJobPayload(ApiModel):
    schema_version: Literal[7]
    import_kind: Literal["image_directory"]
    source_selection_id: UUID
    source_directory: str = Field(min_length=1, max_length=2048)
    source_display_name: str = Field(min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_adapter_version: str | None = Field(default=None, max_length=150)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_sequence_numbers: tuple[int, ...] = Field(default=())
    start_mode: Literal["reuse_exact", "rerun_current_models"]
    previous_job_id: UUID | None = None
    image_selection_run_id: UUID | None = None
    symbol_model: SymbolModelJobSnapshotPayload
    grid_profile: GridProfileJobSnapshotPayload
    page_geometry_manifest: PageGeometryManifestJobPayload
    geometry_guard_resolution_manifest: ImageGeometryGuardResolutionManifestJobPayload | None = None
    board_cell_processing: BoardCellProcessingJobSnapshotPayload | None = None
    image_geometry_rollout: ImageGeometryRolloutJobSnapshotPayload | None = None
    geometry_systemic_guard_policy: ImageGeometrySystemicGuardPolicyJobPayload


class CuratedImageImportJobPayload(ApiModel):
    schema_version: Literal[3]
    import_kind: Literal["image_directory"]
    source_selection_id: UUID
    source_directory: str = Field(min_length=1, max_length=2048)
    source_display_name: str = Field(min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_adapter_version: str | None = Field(default=None, max_length=150)
    image_selection_run_id: UUID
    curated_image_import_source_id: UUID
    curated_image_import_batch_id: UUID
    curated_manifest_relative_path: str = Field(min_length=1, max_length=2048)
    curated_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    curated_manifest_entry_start: int = Field(ge=0)
    curated_manifest_entry_count: int = Field(ge=1)
    symbol_model: SymbolModelJobSnapshotPayload
    grid_profile: GridProfileJobSnapshotPayload
    board_cell_processing: BoardCellProcessingJobSnapshotPayload | None = None
    image_geometry_rollout: ImageGeometryRolloutJobSnapshotPayload | None = None


class ManagedImageReprocessJobPayload(ApiModel):
    schema_version: Literal[4]
    import_kind: Literal["image_directory"]
    source_selection_id: UUID | None = None
    source_directory: str = Field(min_length=1, max_length=2048)
    source_display_name: str = Field(min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_adapter_version: str | None = Field(default=None, max_length=150)
    image_selection_run_id: UUID | None = None
    managed_source_job_id: UUID
    symbol_model: SymbolModelJobSnapshotPayload
    grid_profile: GridProfileJobSnapshotPayload
    board_cell_processing: BoardCellProcessingJobSnapshotPayload | None = None
    image_geometry_rollout: ImageGeometryRolloutJobSnapshotPayload | None = None


class PinnedManagedImageReprocessJobPayload(ApiModel):
    schema_version: Literal[6]
    import_kind: Literal["image_directory"]
    source_selection_id: UUID
    source_directory: str = Field(min_length=1, max_length=2048)
    source_display_name: str = Field(min_length=1, max_length=255)
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_adapter_version: str | None = Field(default=None, max_length=150)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_selection_run_id: UUID | None = None
    managed_source_job_id: UUID
    managed_source_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_geometry_manifest: PageGeometryManifestJobPayload
    symbol_model: SymbolModelJobSnapshotPayload
    grid_profile: GridProfileJobSnapshotPayload
    board_cell_processing: BoardCellProcessingJobSnapshotPayload
    image_geometry_rollout: ImageGeometryRolloutJobSnapshotPayload | None = None
    geometry_systemic_guard_policy: ImageGeometrySystemicGuardPolicyJobPayload | None = None


class ImageSelectionJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    source_selection_id: UUID
    input_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selector_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_version: Literal[1]
    sequence_direction: Literal["ascending", "descending"] = "ascending"
    first_sequence_number: int | None = Field(default=None, ge=1)
    last_sequence_number: int | None = Field(default=None, ge=1)
    execution_mode: Literal["full", "range_recovery"] = "full"
    source_run_id: UUID | None = None
    source_snapshot_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class SemiAutomaticImageSelectionJobPayload(ApiModel):
    schema_version: Literal[1, 2] = 1
    selection_kind: Literal["semi_automatic_image_selection"]
    workflow_mode: Literal["selection", "filename_verification"] | None = None
    run_id: UUID
    source_upload_id: UUID
    source_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_count: int = Field(ge=1)
    first_sequence_number: int = Field(ge=1)
    last_sequence_number: int = Field(ge=1)
    direction: Literal["ascending", "descending"]
    range_convention: Literal["seq-inclusive-v1"]
    full_range_size: Literal[9]
    expected_ranges_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    recognizer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    grouping_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_workflow_mode(self) -> Self:
        if self.schema_version == 2 and self.workflow_mode is None:
            raise ValueError("schema v2 requires workflowMode")
        if self.schema_version == 1 and self.workflow_mode is not None:
            raise ValueError("workflowMode is only valid for schema v2")
        return self


class ValidateJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    dataset_version_id: UUID


class LayoutImportValidateJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    validation_kind: Literal["layout_import"]
    import_job_id: UUID
    rules_version_id: UUID


class PageGeometryPreflightJobPayload(ApiModel):
    schema_version: Literal[2]
    validation_kind: Literal["page_geometry_preflight"]
    preflight_policy_version: Literal["page-geometry-preflight-v2-auto-anchor"] | None = None
    source_selection_id: UUID
    source_directory: str = Field(min_length=1, max_length=2048)
    source_display_name: str | None = Field(default=None, min_length=1, max_length=255)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_registration_profile: dict[str, object]
    page_geometry_overrides: dict[str, object] = Field(default_factory=dict)
    canonical_sequence_numbers: tuple[int, ...] = Field(default=())


class PayoutJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    dataset_version_id: UUID
    rules_version_id: UUID
    algorithm_version: str = Field(min_length=1, max_length=100)


class SnapshotJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    mobile_release_id: UUID


class AndroidBuildJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    mobile_release_id: UUID


class SymbolTrainingJobPayload(ApiModel):
    schema_version: Literal[1, 2]
    cohort_id: UUID
    cohort_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration: dict[str, object]
    configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: UUID


class PendingSymbolReinferenceJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    inference_kind: Literal["pending_symbols_only"]
    symbol_model: SymbolModelJobSnapshotPayload


class SymbolCellReviewBulkJobPayload(ApiModel):
    schema_version: Literal[1]
    workflow: Literal["image_symbol_review_bulk"]
    operation_id: UUID


class SymbolCellReviewBackfillJobPayload(ApiModel):
    schema_version: Literal[1]
    workflow: Literal["image_symbol_review_backfill"]
    generation: int = Field(ge=1)
    preserve_ready_projection: bool = False
    table_bytes_before: int | None = Field(default=None, ge=0)
    index_bytes_before: int | None = Field(default=None, ge=0)
    database_free_bytes_before: int | None = Field(default=None, ge=0)


class ImageGeometryRolloutBackfillJobPayload(ApiModel):
    schema_version: Literal[1, 2, 3]
    workflow: Literal["image_geometry_rollout_backfill"]
    contract_backfill_version: Literal["additive-virtual-geometry-v2-backfill-v1"] | None = None
    generation: int = Field(ge=1)
    rollout_revision: int = Field(ge=0)
    geometry_mode: str = Field(min_length=1, max_length=30)
    cell_asset_mode: str = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_contract_backfill_version(self) -> Self:
        if self.schema_version == 3 and self.contract_backfill_version is None:
            raise ValueError("schema v3 requires contractBackfillVersion")
        if self.schema_version != 3 and self.contract_backfill_version is not None:
            raise ValueError("contractBackfillVersion is only valid for schema v3")
        return self


class BoardCellRecropJobSnapshotPayload(ApiModel):
    activation_version: str = Field(min_length=1, max_length=150)
    audit_report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cropper_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cropper_version: str = Field(min_length=1, max_length=150)
    estimator_version: str = Field(min_length=1, max_length=150)
    geometry_version: str = Field(min_length=1, max_length=150)
    homography_version: str = Field(min_length=1, max_length=150)
    locator_version: str = Field(min_length=1, max_length=150)
    thresholds_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thresholds_version: str = Field(min_length=1, max_length=150)


class PendingGridReinferenceJobPayload(ApiModel):
    schema_version: Literal[1, 2]
    inference_kind: Literal["pending_grid_only"]
    cell_output_size: int = Field(default=64, ge=16)
    grid_profile: GridProfileJobSnapshotPayload | None = None
    board_cell_recrop: BoardCellRecropJobSnapshotPayload | None = None

    @model_validator(mode="after")
    def validate_versioned_snapshot(self) -> Self:
        if self.schema_version == 1:
            if self.grid_profile is None or self.board_cell_recrop is not None:
                raise ValueError("schema v1 requires only gridProfile")
        elif self.board_cell_recrop is None or self.grid_profile is not None:
            raise ValueError("schema v2 requires only boardCellRecrop")
        return self


class StorageGcJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    storage_gc_run_id: UUID
    policy_version: str = Field(min_length=1, max_length=64)
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["manual", "automatic"]


class StorageInventoryJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    inventory_kind: Literal["managed_image_storage"]
    requested_at: datetime


class StoragePipelineCompactionJobPayload(ApiModel):
    schema_version: Literal[1] = 1
    compaction_kind: Literal["reproducible_image_pipeline_state"]
    manifest_relative_path: str = Field(min_length=1, max_length=2048)
    manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["observe_only", "execute"]


class ImportJobCreate(ApiModel):
    job_type: Literal[JobType.IMPORT]
    game_id: UUID
    input_payload: ImportJobCreatePayload


class ValidateJobCreate(ApiModel):
    job_type: Literal[JobType.VALIDATE]
    game_id: UUID
    input_payload: (
        ValidateJobPayload | LayoutImportValidateJobPayload | PageGeometryPreflightJobPayload
    )


class PayoutJobCreate(ApiModel):
    job_type: Literal[JobType.PAYOUT]
    game_id: UUID
    input_payload: PayoutJobPayload


class SnapshotJobCreate(ApiModel):
    job_type: Literal[JobType.SNAPSHOT]
    game_id: UUID | None = None
    input_payload: SnapshotJobPayload


class AndroidBuildJobCreate(ApiModel):
    job_type: Literal[JobType.ANDROID_BUILD]
    game_id: UUID | None = None
    input_payload: AndroidBuildJobPayload


JobCreateRequest = Annotated[
    ImportJobCreate
    | ValidateJobCreate
    | PayoutJobCreate
    | SnapshotJobCreate
    | AndroidBuildJobCreate,
    Field(discriminator="job_type"),
]

JobPayloadResponse = (
    ImportJobPayload
    | LegacyImageImportJobPayload
    | ImageImportJobPayload
    | BrowserImageImportJobPayload
    | ResolvedBrowserImageImportJobPayload
    | CuratedImageImportJobPayload
    | ManagedImageReprocessJobPayload
    | PinnedManagedImageReprocessJobPayload
    | ImageSelectionJobPayload
    | SemiAutomaticImageSelectionJobPayload
    | ValidateJobPayload
    | LayoutImportValidateJobPayload
    | PageGeometryPreflightJobPayload
    | PayoutJobPayload
    | SnapshotJobPayload
    | AndroidBuildJobPayload
    | SymbolTrainingJobPayload
    | SymbolCellReviewBulkJobPayload
    | SymbolCellReviewBackfillJobPayload
    | ImageGeometryRolloutBackfillJobPayload
    | StorageGcJobPayload
    | StorageInventoryJobPayload
    | StoragePipelineCompactionJobPayload
    | PendingSymbolReinferenceJobPayload
    | PendingGridReinferenceJobPayload
)


class ImageSelectionRecentWindowResponse(ApiModel):
    from_processed: int
    to_processed: int
    elapsed_seconds: float
    groups_finalized: int
    verifications: int
    manual: int
    range_required: int


class ImageSelectionJobProgressResponse(ApiModel):
    groups: int
    selected: int
    manual: int
    range_required: int
    skipped: int
    errors: int
    verifications: int
    upload_duration_seconds: float | None = None
    processing_duration_seconds: float | None = None
    diagnostic_checksum_sha256: str | None = None
    recent_window: ImageSelectionRecentWindowResponse | None = None
    stage_seconds: dict[str, float] | None = None
    telemetry_counters: dict[str, int] | None = None


class BoardCellGeometryJobProgressResponse(ApiModel):
    status: Literal["processing", "waiting_for_geometry", "complete"]
    total: int = Field(ge=0)
    processed: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    pending: int = Field(ge=0)
    resolved: int = Field(ge=0)
    superseded: int = Field(ge=0)


class ImageGeometrySystemicGuardJobProgressResponse(ApiModel):
    policy_version: Literal["image-geometry-systemic-guard-v1"]
    required: bool
    passed: bool
    report_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_relative_path: str = Field(min_length=1, max_length=2048)
    source_count: int = Field(ge=0)
    active_board_count: int = Field(ge=0)
    sample_source_count: int = Field(ge=0)
    sample_board_count: int = Field(ge=0)
    page_registration_ready_rate: float = Field(ge=0, le=1)
    final_cell_grid_ready_rate: float = Field(ge=0, le=1)
    invariant_violation_count: int = Field(ge=0)
    resolution_applied: bool = False
    resolution_manifest_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    corrected_full_count: int = Field(default=0, ge=0)
    partial_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)


class JobProgressResponse(ApiModel):
    current: int
    total: int | None
    stage: str | None
    succeeded: int
    failed: int
    review: int
    image_selection: ImageSelectionJobProgressResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    page_geometry_preflight: PageGeometryPreflightJobProgressResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    board_cell_geometry: BoardCellGeometryJobProgressResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    geometry_systemic_guard: ImageGeometrySystemicGuardJobProgressResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class PageGeometryPreflightJobProgressResponse(ApiModel):
    complete: bool
    geometry_manifest_checksum_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class JobErrorResponse(ApiModel):
    code: str
    message: str


class ImageSelectionJobDeletionResponse(ApiModel):
    job_id: UUID
    run_id: UUID
    managed_run_files_deleted: bool
    source_staging_deleted: bool
    shared_source_staging_preserved: bool

    @classmethod
    def from_domain(
        cls,
        deletion: ImageSelectionJobDeletion,
    ) -> ImageSelectionJobDeletionResponse:
        return cls(
            job_id=deletion.job_id,
            run_id=deletion.run_id,
            managed_run_files_deleted=deletion.managed_run_files_deleted,
            source_staging_deleted=deletion.source_staging_deleted,
            shared_source_staging_preserved=deletion.shared_source_staging_preserved,
        )


class JobResponse(ApiModel):
    id: UUID
    job_type: JobType
    game_id: UUID | None
    status: JobStatus
    input_payload: JobPayloadResponse
    progress: JobProgressResponse
    error: JobErrorResponse | None
    worker_version: str | None
    attempt_count: int
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
    workflow_mode: Literal["selection", "filename_verification"] | None = None

    @classmethod
    def from_domain(cls, job: Job) -> JobResponse:
        error = None
        if job.error_code is not None and job.error_message is not None:
            error = JobErrorResponse(
                code=job.error_code,
                message=job.error_message,
            )
        return cls(
            id=job.id,
            job_type=job.job_type,
            game_id=job.game_id,
            status=job.status,
            input_payload=_payload_from_domain(job),
            progress=JobProgressResponse(
                current=job.progress_current,
                total=job.progress_total,
                stage=job.stage,
                succeeded=job.success_count,
                failed=job.failure_count,
                review=job.review_count,
                image_selection=_image_selection_progress(job),
                page_geometry_preflight=_page_geometry_preflight_progress(job),
                board_cell_geometry=_board_cell_geometry_progress(job),
                geometry_systemic_guard=_geometry_systemic_guard_progress(job),
            ),
            error=error,
            worker_version=job.worker_version,
            attempt_count=job.attempt_count,
            heartbeat_at=job.heartbeat_at,
            lease_expires_at=job.lease_expires_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            cancel_requested_at=job.cancel_requested_at,
            workflow_mode=_workflow_mode_from_domain(job),
        )


def _page_geometry_preflight_progress(
    job: Job,
) -> PageGeometryPreflightJobProgressResponse | None:
    if job.job_type is not JobType.VALIDATE or job.checkpoint_payload is None:
        return None
    if job.input_payload.get("validation_kind") != "page_geometry_preflight":
        return None
    payload = job.checkpoint_payload
    complete = payload.get("complete") is True
    checksum = payload.get("geometry_manifest_checksum_sha256")
    if checksum is not None and (not isinstance(checksum, str) or len(checksum) != 64):
        return None
    return PageGeometryPreflightJobProgressResponse(
        complete=complete,
        geometry_manifest_checksum_sha256=checksum,
    )


def _board_cell_geometry_progress(job: Job) -> BoardCellGeometryJobProgressResponse | None:
    if job.checkpoint_payload is None:
        return None
    raw = job.checkpoint_payload.get("board_cell_geometry")
    if not isinstance(raw, dict):
        return None
    try:
        status = raw["status"]
        if status not in {"processing", "waiting_for_geometry", "complete"}:
            return None
        return BoardCellGeometryJobProgressResponse(
            status=status,
            total=_progress_integer(raw["total"]),
            processed=_progress_integer(raw["processed"]),
            succeeded=_progress_integer(raw["succeeded"]),
            pending=_progress_integer(raw["pending"]),
            resolved=_progress_integer(raw["resolved"]),
            superseded=_progress_integer(raw["superseded"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _geometry_systemic_guard_progress(
    job: Job,
) -> ImageGeometrySystemicGuardJobProgressResponse | None:
    if job.job_type is not JobType.IMPORT or job.checkpoint_payload is None:
        return None
    raw = job.checkpoint_payload.get("geometry_systemic_guard")
    if not isinstance(raw, dict):
        return None
    try:
        checksum = raw["reportChecksumSha256"]
        relative_path = raw["reportRelativePath"]
        if not isinstance(checksum, str) or not isinstance(relative_path, str):
            return None
        resolution = job.checkpoint_payload.get("geometry_guard_resolution")
        resolution_payload = resolution if isinstance(resolution, dict) else {}
        return ImageGeometrySystemicGuardJobProgressResponse(
            policy_version=raw["policyVersion"],
            required=raw["required"],
            passed=raw["passed"],
            report_checksum_sha256=checksum,
            report_relative_path=relative_path,
            source_count=_progress_integer(raw["sourceCount"]),
            active_board_count=_progress_integer(raw["activeBoardCount"]),
            sample_source_count=_progress_integer(raw["sampleSourceCount"]),
            sample_board_count=_progress_integer(raw["sampleBoardCount"]),
            page_registration_ready_rate=_progress_float(raw["pageRegistrationReadyRate"]),
            final_cell_grid_ready_rate=_progress_float(raw["finalCellGridReadyRate"]),
            invariant_violation_count=_progress_integer(raw["invariantViolationCount"]),
            resolution_applied=resolution_payload.get("passed") is True,
            resolution_manifest_checksum_sha256=cast(
                str | None, resolution_payload.get("manifestChecksumSha256")
            ),
            corrected_full_count=_progress_integer(resolution_payload.get("correctedFullCount", 0)),
            partial_count=_progress_integer(resolution_payload.get("partialCount", 0)),
            rejected_count=_progress_integer(resolution_payload.get("rejectedCount", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _image_selection_progress(job: Job) -> ImageSelectionJobProgressResponse | None:
    if job.job_type is not JobType.IMAGE_SELECTION or job.checkpoint_payload is None:
        return None
    payload = job.checkpoint_payload
    if payload.get("workflow") != "image_selection":
        return None
    diagnostic = payload.get("diagnostic")
    checksum = diagnostic.get("checksumSha256") if isinstance(diagnostic, dict) else None
    processing_seconds_value = payload.get("processing_duration_seconds")
    try:
        return ImageSelectionJobProgressResponse(
            groups=_progress_integer(payload.get("group_count", 0)),
            selected=_progress_integer(payload.get("selected_count", 0)),
            manual=_progress_integer(payload.get("manual_count", 0)),
            range_required=_progress_integer(payload.get("range_required_count", 0)),
            skipped=_progress_integer(payload.get("skipped_count", 0)),
            errors=_progress_integer(payload.get("error_count", 0)),
            verifications=_progress_integer(payload.get("verification_count", 0)),
            upload_duration_seconds=(
                None
                if payload.get("upload_duration_seconds") is None
                else _progress_float(payload["upload_duration_seconds"])
            ),
            processing_duration_seconds=(
                None
                if processing_seconds_value is None
                else _progress_float(processing_seconds_value)
            ),
            diagnostic_checksum_sha256=(checksum if isinstance(checksum, str) else None),
            recent_window=_image_selection_recent_window(payload.get("recent_window")),
            stage_seconds=_image_selection_stage_seconds(payload.get("stage_timing")),
            telemetry_counters=_image_selection_counters(payload.get("stage_timing")),
        )
    except (TypeError, ValueError):
        return None


def _progress_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise TypeError
    return int(value)


def _progress_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise TypeError
    return float(value)


def _image_selection_recent_window(
    value: object,
) -> ImageSelectionRecentWindowResponse | None:
    if not isinstance(value, dict):
        return None
    try:
        return ImageSelectionRecentWindowResponse(
            from_processed=_progress_integer(value["fromProcessed"]),
            to_processed=_progress_integer(value["toProcessed"]),
            elapsed_seconds=_progress_float(value["elapsedSeconds"]),
            groups_finalized=_progress_integer(value["groupsFinalized"]),
            verifications=_progress_integer(value["verifications"]),
            manual=_progress_integer(value["manual"]),
            range_required=_progress_integer(value.get("rangeRequired", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _image_selection_stage_seconds(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict) or not isinstance(value.get("stages"), dict):
        return None
    stages: dict[str, float] = {}
    for name, stage in value["stages"].items():
        if not isinstance(name, str) or not isinstance(stage, dict):
            continue
        try:
            stages[name] = _progress_float(stage["totalSeconds"])
        except (KeyError, TypeError, ValueError):
            continue
    return stages or None


def _image_selection_counters(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict) or not isinstance(value.get("counters"), dict):
        return None
    counters: dict[str, int] = {}
    for name, count in value["counters"].items():
        if not isinstance(name, str):
            continue
        try:
            counters[name] = _progress_integer(count)
        except (TypeError, ValueError):
            continue
    return counters or None


def _payload_from_domain(job: Job) -> JobPayloadResponse:
    if job.job_type is JobType.IMPORT:
        if job.input_payload.get("import_kind") == "image_directory":
            if job.input_payload.get("schema_version") == 1:
                return LegacyImageImportJobPayload.model_validate(job.input_payload)
            if job.input_payload.get("schema_version") == 3:
                return CuratedImageImportJobPayload.model_validate(job.input_payload)
            if job.input_payload.get("schema_version") == 4:
                return ManagedImageReprocessJobPayload.model_validate(job.input_payload)
            if job.input_payload.get("schema_version") == 5:
                return BrowserImageImportJobPayload.model_validate(job.input_payload)
            if job.input_payload.get("schema_version") == 6:
                return PinnedManagedImageReprocessJobPayload.model_validate(job.input_payload)
            if job.input_payload.get("schema_version") == 7:
                return ResolvedBrowserImageImportJobPayload.model_validate(job.input_payload)
            return ImageImportJobPayload.model_validate(job.input_payload)
        return ImportJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.IMAGE_SELECTION:
        return ImageSelectionJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.SEMI_AUTOMATIC_IMAGE_SELECTION:
        return SemiAutomaticImageSelectionJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.VALIDATE:
        if job.input_payload.get("validation_kind") == "layout_import":
            return LayoutImportValidateJobPayload.model_validate(job.input_payload)
        if job.input_payload.get("validation_kind") == "page_geometry_preflight":
            return PageGeometryPreflightJobPayload.model_validate(job.input_payload)
        return ValidateJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.PAYOUT:
        return PayoutJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.SNAPSHOT:
        return SnapshotJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.SYMBOL_TRAINING:
        return SymbolTrainingJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.IMAGE_SYMBOL_REVIEW_BULK:
        return SymbolCellReviewBulkJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.IMAGE_SYMBOL_REVIEW_BACKFILL:
        return SymbolCellReviewBackfillJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL:
        return ImageGeometryRolloutBackfillJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.STORAGE_GC:
        return StorageGcJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.STORAGE_INVENTORY:
        return StorageInventoryJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.STORAGE_PIPELINE_COMPACTION:
        return StoragePipelineCompactionJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.IMAGE_SYMBOL_REINFERENCE:
        return PendingSymbolReinferenceJobPayload.model_validate(job.input_payload)
    if job.job_type is JobType.IMAGE_GRID_REINFERENCE:
        return PendingGridReinferenceJobPayload.model_validate(job.input_payload)
    return AndroidBuildJobPayload.model_validate(job.input_payload)


def _workflow_mode_from_domain(
    job: Job,
) -> Literal["selection", "filename_verification"] | None:
    if job.job_type is not JobType.SEMI_AUTOMATIC_IMAGE_SELECTION:
        return None
    raw_mode = job.input_payload.get("workflow_mode")
    if raw_mode in {"selection", "filename_verification"}:
        return cast(Literal["selection", "filename_verification"], raw_mode)
    raw_recognizer = job.input_payload.get("recognizer_fingerprint")
    return workflow_mode_for_recognizer_fingerprint(
        raw_recognizer if isinstance(raw_recognizer, str) else None
    ).value
