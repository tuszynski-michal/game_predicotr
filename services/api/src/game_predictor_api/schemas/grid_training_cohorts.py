"""Closed HTTP commands and metadata-only cohort views for D-556."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal["TRAIN", "VALIDATION", "REGRESSION"]
Qualification = Literal["eligible", "blocked", "unresolved"]


class CohortClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GridCohortSelector(CohortClosedModel):
    source_ids: list[UUID] | None = Field(None, alias="sourceIds", min_length=1, max_length=200)
    import_job_id: UUID | None = Field(None, alias="importJobId")

    @model_validator(mode="after")
    def exact_selection(self) -> "GridCohortSelector":
        if (self.source_ids is None) == (self.import_job_id is None):
            raise ValueError("Choose source IDs or one import.")
        if self.source_ids and len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Source IDs must be unique.")
        return self


class GridCohortRecording(CohortClosedModel):
    group_id: UUID = Field(alias="groupId")
    role: Role


class GridCohortPrepareCommand(CohortClosedModel):
    idempotency_key: UUID = Field(alias="idempotencyKey")
    mode: Literal["grid-only", "screen+grid"]
    family_id: UUID = Field(alias="familyId")
    base_version_id: UUID = Field(alias="baseVersionId")
    selector: GridCohortSelector
    recordings: list[GridCohortRecording] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_recordings(self) -> "GridCohortPrepareCommand":
        if len({item.group_id for item in self.recordings}) != len(self.recordings):
            raise ValueError("Each recording group has exactly one role.")
        return self


class GridCohortRevisionCommand(CohortClosedModel):
    idempotency_key: UUID = Field(alias="idempotencyKey")
    expected_revision: int = Field(alias="expectedRevision", ge=0)


class GridCohortPageCommand(GridCohortRevisionCommand):
    cursor: int = Field(ge=0)


class GridCohortFreezeCommand(GridCohortRevisionCommand):
    expected_preview_sha256: str = Field(alias="expectedPreviewSha256", pattern="^[0-9a-f]{64}$")
    expected_manifest_sha256: str = Field(alias="expectedManifestSha256", pattern="^[0-9a-f]{64}$")


class GridSourceIdentityPin(CohortClosedModel):
    source_id: UUID = Field(alias="sourceId")
    expected_source_sha256: str = Field(alias="expectedSourceSha256", pattern="^[0-9a-f]{64}$")
    expected_source_geometry_revision_id: UUID = Field(alias="expectedSourceGeometryRevisionId")
    expected_geometry_sha256: str = Field(alias="expectedGeometrySha256", pattern="^[0-9a-f]{64}$")


class GridSourceIdentityCompleteCommand(CohortClosedModel):
    idempotency_key: UUID = Field(alias="idempotencyKey")
    sources: list[GridSourceIdentityPin] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_sources(self) -> "GridSourceIdentityCompleteCommand":
        if len({item.source_id for item in self.sources}) != len(self.sources):
            raise ValueError("Source IDs must be unique.")
        return self


class GridCohortRoleSummary(CohortClosedModel):
    role: Role
    requiredBoards: int
    requiredPhotos: int
    requiredFullPhotos: int
    eligibleBoards: int
    eligiblePhotos: int
    eligibleFullPhotos: int
    materializedBoards: int = 0
    materializedPhotos: int = 0
    materializedFullPhotos: int = 0
    missingBoards: int
    missingPhotos: int
    missingFullPhotos: int
    recordingRequired: bool


class GridCohortSummary(CohortClosedModel):
    roles: list[GridCohortRoleSummary]
    reasonCounts: dict[str, int]


class GridCohortHeader(CohortClosedModel):
    id: UUID
    gameId: UUID
    revision: int
    status: Literal[
        "preparing",
        "preview_ready",
        "materializing",
        "ready_to_freeze",
        "frozen",
        "failed",
        "canceled",
    ]
    mode: Literal["grid-only", "screen+grid"]
    familyId: UUID
    baseVersionId: UUID
    previewSha256: str | None
    manifestSha256: str | None
    summary: GridCohortSummary
    nextCaptureCursor: int | None
    nextMaterializationCursor: int | None
    createdAt: str


class GridCohortMember(CohortClosedModel):
    sourceId: UUID
    ordinal: int
    role: Role | None
    qualification: Qualification
    reasons: list[str]
    boardEligibleCount: int
    screenEligible: bool
    metadataMissing: bool


class GridCohortList(CohortClosedModel):
    items: list[GridCohortHeader]
    nextCursor: UUID | None


class GridCohortMembers(CohortClosedModel):
    items: list[GridCohortMember]
    nextCursor: int | None


class GridCohortEligibility(CohortClosedModel):
    qualification: Qualification
    reasons: list[str]
    manifestSha256: str | None
    humanLabelWithdrawn: bool | None
    liveSourceLinked: bool | None
    snapshotBytesAvailable: bool | None


class GridCohortReceipt(CohortClosedModel):
    idempotencyKey: UUID
    kind: Literal["prepare", "prepare-page", "materialize-page", "freeze", "cancel"]
    revision: int
    outcome: str


class GridCohortCommandResponse(CohortClosedModel):
    cohort: GridCohortHeader
    receipt: GridCohortReceipt


class GridSourceIdentityResult(CohortClosedModel):
    sourceId: UUID
    outcome: Literal["completed", "already_complete"]


class GridSourceIdentityReceipt(CohortClosedModel):
    idempotencyKey: UUID
    kind: Literal["complete_identities"]
    outcome: Literal["completed"]
    results: list[GridSourceIdentityResult]


class GridSourceIdentityResponse(CohortClosedModel):
    receipt: GridSourceIdentityReceipt


class GridTrainingEarlyStopping(CohortClosedModel):
    metric: str
    direction: Literal["maximize", "minimize"]
    evaluationIntervalSeconds: float
    patience: int
    minDelta: float
    minEvaluations: int


class GridTrainingRuntimeRequirement(CohortClosedModel):
    torch: str
    torchvision: str
    cuda: str


class GridTrainingPresetView(CohortClosedModel):
    presetId: str
    version: int
    policy: str
    fingerprint: str
    mode: Literal["grid-only", "screen+grid"]
    approved: bool
    approvalBasis: str
    batchItems: int
    boardsPerItem: int
    frozenModules: list[str]
    learningRate: float
    trainSecondsPerTrainPhoto: float
    minTrainSeconds: float
    maxTrainSeconds: float
    maxSteps: int
    maxRunSeconds: float
    stepsPerSecondEstimate: float
    minTotalVramBytes: int
    minFreeVramBytes: int
    earlyStopping: GridTrainingEarlyStopping
    runtime: GridTrainingRuntimeRequirement


class GridTrainingRunCost(CohortClosedModel):
    trainItems: int
    stepsPerEpoch: int
    plannedTrainSeconds: float
    plannedSteps: int
    epochsPlanned: float
    evaluationsPlanned: int
    estimatedRunSeconds: float
    withinBudget: bool


class GridTrainingLeaseView(CohortClosedModel):
    state: Literal["free", "held", "stale", "unknown"]
    runKind: Literal["train", "smoke"] | None


class GridTrainingSmokeLimits(CohortClosedModel):
    maxSteps: int
    trainSeconds: float
    startupSeconds: float
    maxSeconds: float


class GridTrainingRunPreview(CohortClosedModel):
    policy: str
    gameId: UUID
    cohortId: UUID
    cohortStatus: str
    cohortMode: Literal["grid-only", "screen+grid"]
    cohortQualification: Qualification
    cohortReasons: list[str]
    presets: list[GridTrainingPresetView]
    selectedPresetId: str | None
    cost: GridTrainingRunCost | None
    apiBlockers: list[str]
    pendingWorkerChecks: list[str]
    lease: GridTrainingLeaseView
    smoke: GridTrainingSmokeLimits


class GridTrainingRunCreate(CohortClosedModel):
    idempotencyKey: UUID
    cohortId: UUID
    presetId: str = Field(min_length=1, max_length=64)
    presetFingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class GridTrainingRunBudget(CohortClosedModel):
    maxSteps: int
    maxSeconds: float
    reservedSteps: int
    usedSeconds: float


class GridTrainingRunView(CohortClosedModel):
    runId: UUID
    gameId: UUID
    status: Literal[
        "created", "processing", "waiting_for_review", "completed", "failed", "cancelled"
    ]
    stage: str | None
    cohortId: UUID
    mode: Literal["grid-only", "screen+grid"]
    presetId: str
    presetFingerprint: str
    baseVersionId: UUID
    plannedSteps: int
    progressCurrent: int
    progressTotal: int | None
    attempt: int
    budget: GridTrainingRunBudget | None
    checkpointStep: int | None
    candidateVersionId: UUID | None
    cancelRequested: bool
    errorCode: str | None
    createdAt: str
    updatedAt: str


class GridTrainingRunList(CohortClosedModel):
    items: list[GridTrainingRunView]
