"""Closed HTTP contract for the durable correction-learning workflow."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.schemas.grid_model_evaluations import GridModelEvaluationCohortPin
from game_predictor_api.schemas.grid_training_cohorts import GridTrainingRunCost

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CorrectionLearningClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GridCorrectionLearningExclusion(CorrectionLearningClosedModel):
    gameId: UUID
    reason: str = Field(min_length=1, max_length=500)
    confirmed: StrictBool

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("An exclusion requires a nonblank reason.")
        return value


class GridCorrectionLearningPreviewCommand(CorrectionLearningClosedModel):
    importJobIds: list[UUID] = Field(default_factory=list, max_length=100)
    exclusions: list[GridCorrectionLearningExclusion] = Field(default_factory=list, max_length=100)

    @field_validator("importJobIds")
    @classmethod
    def unique_imports(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Import jobs must be distinct.")
        return value

    @field_validator("exclusions")
    @classmethod
    def unique_exclusions(
        cls, value: list[GridCorrectionLearningExclusion]
    ) -> list[GridCorrectionLearningExclusion]:
        if len({item.gameId for item in value}) != len(value):
            raise ValueError("Excluded games must be distinct.")
        return sorted(value, key=lambda item: str(item.gameId))


class GridCorrectionLearningStartCommand(GridCorrectionLearningPreviewCommand):
    idempotencyKey: UUID
    previewSha256: Sha256


class GridCorrectionLearningRoleCount(CorrectionLearningClosedModel):
    role: Literal["TRAIN", "VALIDATION", "REGRESSION"]
    photos: int = Field(ge=0)
    boards: int = Field(ge=0)


class GridCorrectionDataAvailability(CorrectionLearningClosedModel):
    """Deduplicated annotated population before buffers; deficits are aggregate lower bounds."""

    photos: int = Field(ge=0)
    boards: int = Field(ge=0)
    minimumPhotos: Literal[20]
    minimumBoards: Literal[60]
    photoDeficit: int = Field(ge=0)
    boardDeficit: int = Field(ge=0)
    splitStatus: Literal["minima", "infeasible", "ready"]


class GridCorrectionLearningCount(CorrectionLearningClosedModel):
    photos: int = Field(ge=0)
    boards: int = Field(ge=0)


class GridCorrectionLearningExclusionCount(GridCorrectionLearningCount):
    reason: str


class GridCorrectionLearningProgressCounts(CorrectionLearningClosedModel):
    """Boards partition TRAIN; used/new photos may overlap on different positions."""

    approved: GridCorrectionLearningCount
    availableTrain: GridCorrectionLearningCount
    usedTrain: GridCorrectionLearningCount
    newTrain: GridCorrectionLearningCount
    validation: GridCorrectionLearningCount
    regression: GridCorrectionLearningCount
    validationReserve: GridCorrectionLearningCount
    regressionReserve: GridCorrectionLearningCount
    buffers: GridCorrectionLearningCount
    excluded: GridCorrectionLearningCount
    exclusionReasons: list[GridCorrectionLearningExclusionCount]


class GridCorrectionLearningPreview(CorrectionLearningClosedModel):
    gameId: UUID
    baseVersionId: UUID | None
    baseManifestSha256: Sha256 | None
    defaultRevision: int | None = Field(ge=0)
    importJobIds: list[UUID]
    roleCounts: list[GridCorrectionLearningRoleCount]
    dataAvailability: GridCorrectionDataAvailability | None
    progressCounts: GridCorrectionLearningProgressCounts | None = None
    bufferPhotos: int = Field(ge=0)
    priorScopeDocumented: bool
    priorGameIds: list[UUID]
    historicalCohorts: list[GridModelEvaluationCohortPin]
    exclusions: list[GridCorrectionLearningExclusion]
    requiredGameIds: list[UUID]
    presetId: str
    presetFingerprint: Sha256
    cost: GridTrainingRunCost | None
    blockers: list[str]
    pendingWorkerChecks: list[str]
    canStart: bool
    evidenceLevel: Literal["photo-only"]
    limitations: list[str]
    previewSha256: Sha256


class GridCorrectionLearningView(CorrectionLearningClosedModel):
    learningId: UUID
    gameId: UUID
    status: JobStatus
    stage: str | None
    baseVersionId: UUID
    defaultRevision: int = Field(ge=0)
    cohortId: UUID | None
    trainingRunId: UUID | None
    candidateVersionId: UUID | None
    evaluationId: UUID | None
    reportId: UUID | None
    verdict: Literal["PASS", "REVISE", "NOT_EVALUABLE"] | None
    previewSha256: Sha256
    requiredGameIds: list[UUID]
    exclusions: list[GridCorrectionLearningExclusion]
    cancelRequested: bool
    errorCode: str | None
    createdAt: str
    updatedAt: str


class GridCorrectionLearningList(CorrectionLearningClosedModel):
    items: list[GridCorrectionLearningView]
