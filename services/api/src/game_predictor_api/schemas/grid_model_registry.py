"""Closed catalogue transport generated into OpenAPI and the Admin client."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from game_predictor_api.schemas.catalog import ApiModel


class GridModelTopology(ApiModel):
    model_config = ConfigDict(extra="forbid")
    screen_rows: int = Field(ge=1, le=20)
    screen_columns: int = Field(ge=1, le=20)
    board_rows: int = Field(ge=1, le=20)
    board_columns: int = Field(ge=1, le=20)


class GridModelArtifact(ApiModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)


class GridModelProvenance(ApiModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=100)
    export_id: str = Field(min_length=1, max_length=100)
    preset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class GridModelHistoricalReport(ApiModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(min_length=1, max_length=200)
    result: str = Field(min_length=1, max_length=1000)


class GridInferenceManifest(ApiModel):
    schema_version: Literal["grid-engine-model-manifest-v1"]
    profile: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    model_kind: Literal["neural_grid"]
    model_version: str = Field(min_length=1, max_length=64)
    bundle_format: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=100)
    export_id: str = Field(min_length=1, max_length=100)
    preset: str = Field(min_length=1, max_length=100)
    preset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_on: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    selection_reason: str = Field(min_length=1, max_length=1000)
    report: str = Field(min_length=1, max_length=300)
    report_results: list[GridModelHistoricalReport] = Field(max_length=20)
    files: list[GridModelArtifact] = Field(min_length=4, max_length=4)


class GridModelManifest(ApiModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["grid-model-catalogue-v1"]
    family_id: UUID
    family_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    family_label: str = Field(min_length=1, max_length=200)
    version_id: UUID
    version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    model_kind: Literal["neural_grid"]
    model_version: str = Field(min_length=1, max_length=64)
    bundle_format: str = Field(min_length=1, max_length=64)
    preprocessing_version: str = Field(min_length=1, max_length=64)
    decoding_policy_version: str = Field(min_length=1, max_length=64)
    topology: GridModelTopology
    capabilities: list[Literal["screen_detector", "grid_detector"]] = Field(
        min_length=1, max_length=2
    )
    base_version_id: UUID | None
    cohort_id: UUID | None
    admission: Literal["historical_baseline", "not_evaluated"]
    provenance: GridModelProvenance
    historical_reports: list[GridModelHistoricalReport] = Field(max_length=20)
    managed_directory: str = Field(min_length=1, max_length=300)
    inference_manifest: GridInferenceManifest
    files: list[GridModelArtifact] = Field(min_length=4, max_length=4)
    training_artifacts: list[GridModelArtifact] = Field(min_length=4, max_length=4)


class GridModelRegisterRequest(ApiModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    manifest: GridModelManifest


class GridModelVersionResponse(ApiModel):
    manifest: GridModelManifest
    manifest_sha256: str
    available: bool
    reason_code: str
    published: bool = False
    eligible: bool = False
    eligibility_reason_code: str = "GRID_MODEL_NOT_PUBLISHED"


class GameGridModelAssignmentResponse(ApiModel):
    game_id: UUID
    revision: int | None
    version: GridModelVersionResponse | None
    event_count: int


class GridModelPublishCommand(ApiModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)
    evaluation_id: UUID | None = None


class GridModelAssignmentCommand(ApiModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    expected_revision: int = Field(ge=0)
    version_id: UUID


class GridModelControlReceipt(ApiModel):
    kind: Literal["publish", "set_default", "activate", "rollback"]
    idempotency_key: UUID
    expected_revision: int
    version_id: UUID
    game_id: UUID | None
    evaluation_id: UUID | None
    actor: str
    revision: int
    command_sha256: str
    manifest_sha256: str
    evidence_kind: Literal["historical_admission", "evaluated_candidate"]
    evidence_sha256: str


class GridModelDefaultResponse(ApiModel):
    revision: int
    version: GridModelVersionResponse | None
    eligible: bool
    reason_code: str


class GridModelHistoryEvent(ApiModel):
    kind: Literal["publish", "set_default", "activate", "rollback", "historical_assignment"]
    game_id: UUID | None
    version_id: UUID
    revision: int
    actor: str
    created_at: datetime
    # Historical migration events have no command receipt.
    idempotency_key: UUID | None = None
    expected_revision: int | None = None
    evaluation_id: UUID | None = None
    command_sha256: str | None = None
    manifest_sha256: str | None = None
    evidence_kind: Literal["historical_admission", "evaluated_candidate"] | None = None
    evidence_sha256: str | None = None
