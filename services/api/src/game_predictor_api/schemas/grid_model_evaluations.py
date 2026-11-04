"""HTTP contract of grid model evaluations (TASK-0997, D-559).

The report is returned exactly as stored: structural keys are camelCase, metric
names keep the frozen ``neural-grid-metrics-v1`` snake_case spelling.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from game_predictor_api.domain.full_board_calibration_report import AutomaticCalibration

_SHA = r"^[0-9a-f]{64}$"
Decision = Literal["pass", "fail", "not_evaluable"]
Verdict = Literal["PASS", "REVISE", "NOT_EVALUABLE"]


class EvaluationClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GridModelEvaluationCohortRef(EvaluationClosedModel):
    gameId: UUID
    cohortId: UUID


class GridModelEvaluationExclusion(EvaluationClosedModel):
    gameId: UUID
    reason: str = Field(min_length=1, max_length=500)
    confirmed: StrictBool

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("An exclusion requires a nonblank reason.")
        return value


class GridModelEvaluationCreate(EvaluationClosedModel):
    idempotencyKey: UUID
    versionId: UUID
    cohorts: list[GridModelEvaluationCohortRef] = Field(min_length=1, max_length=100)
    exclusions: list[GridModelEvaluationExclusion] = Field(default_factory=list, max_length=100)

    @field_validator("exclusions")
    @classmethod
    def canonical_exclusions(
        cls, value: list[GridModelEvaluationExclusion]
    ) -> list[GridModelEvaluationExclusion]:
        if len({item.gameId for item in value}) != len(value):
            raise ValueError("Excluded games must be distinct.")
        return sorted(value, key=lambda item: str(item.gameId))


class GridAssignedComparisonCreate(EvaluationClosedModel):
    idempotencyKey: UUID
    versionId: UUID
    gameId: UUID
    cohortId: UUID


class GridModelEvaluationMetrics(EvaluationClosedModel):
    photos: int
    photo_complete_correct: int
    photo_complete_correct_rate: float | None
    boards_expected: int
    boards_correct: int
    board_correct_rate: float | None
    boards_matched: int
    detection_recall: float | None
    false_boards: int
    duplicate_predictions: int
    image_macro: float | None
    nme_p95: float | None
    max_node_error_p95: float | None


class GridModelEvaluationRecording(EvaluationClosedModel):
    groupId: UUID
    base: GridModelEvaluationMetrics
    candidate: GridModelEvaluationMetrics


class GridModelEvaluationDetail(EvaluationClosedModel):
    path: str
    sha256: str = Field(pattern=_SHA)


class GridModelEvaluationRole(EvaluationClosedModel):
    photos: int
    inputSha256: str = Field(pattern=_SHA)
    base: GridModelEvaluationMetrics
    candidate: GridModelEvaluationMetrics
    recordings: list[GridModelEvaluationRecording]
    detail: GridModelEvaluationDetail


class GridModelEvaluationRoles(EvaluationClosedModel):
    VALIDATION: GridModelEvaluationRole
    REGRESSION: GridModelEvaluationRole


class GridModelEvaluationGame(EvaluationClosedModel):
    gameId: UUID
    cohortId: UUID
    mode: Literal["grid-only", "screen+grid"]
    targetMetric: str
    validation: Decision
    regression: Decision
    coverage: Literal["complete", "incomplete"]
    reasons: list[str]
    roles: GridModelEvaluationRoles


class GridModelEvaluationCohortPin(EvaluationClosedModel):
    gameId: UUID
    cohortId: UUID
    manifestSha256: str = Field(pattern=_SHA)


class GridModelEvaluationParity(EvaluationClosedModel):
    passed: bool
    bundleSha256: str = Field(pattern=_SHA)


class GridModelEvaluationReport(EvaluationClosedModel):
    schemaVersion: Literal["grid-model-evaluation-read-v2"]
    producer: str
    policyVersion: str
    policy: dict[str, Any]
    versionId: UUID
    manifestSha256: str = Field(pattern=_SHA)
    baseVersionId: UUID
    baseManifestSha256: str = Field(pattern=_SHA)
    familyId: UUID
    trainingGameId: UUID
    parity: GridModelEvaluationParity
    cohorts: list[GridModelEvaluationCohortPin]
    requiredGameIds: list[UUID]
    games: list[GridModelEvaluationGame]
    verdict: Verdict


class GridCorrectionEvaluationMetrics(EvaluationClosedModel):
    photos: int = Field(ge=0)
    full_photos: int = Field(ge=0)
    partial_photos: int = Field(ge=0)
    boards_expected: int = Field(ge=0)
    boards_matched: int = Field(ge=0)
    boards_correct: int = Field(ge=0)
    board_correct_rate: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    detection_recall: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    normalized_error: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    photo_complete_correct: int | None = Field(ge=0)
    photo_complete_correct_rate: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    false_boards: int | None = Field(ge=0)
    duplicate_predictions: int | None = Field(ge=0)


class GridCorrectionEvaluationRecording(EvaluationClosedModel):
    groupId: UUID
    base: GridCorrectionEvaluationMetrics
    candidate: GridCorrectionEvaluationMetrics


class GridCorrectionEvaluationRole(EvaluationClosedModel):
    photos: int = Field(ge=0)
    inputSha256: str = Field(pattern=_SHA)
    base: GridCorrectionEvaluationMetrics
    candidate: GridCorrectionEvaluationMetrics
    recordings: list[GridCorrectionEvaluationRecording]
    detail: GridModelEvaluationDetail


class GridCorrectionEvaluationRoles(EvaluationClosedModel):
    VALIDATION: GridCorrectionEvaluationRole
    REGRESSION: GridCorrectionEvaluationRole


class GridCorrectionEvaluationDecision(EvaluationClosedModel):
    validation: Decision
    regression: Decision
    coverage: Literal["complete", "incomplete"]
    reasons: list[str]


class GridCorrectionEvaluationGame(GridCorrectionEvaluationDecision):
    gameId: UUID
    cohortId: UUID
    mode: Literal["grid-only"]
    targetMetric: Literal["boards_correct_or_normalized_error"]
    roles: GridCorrectionEvaluationRoles


class GridCorrectionEvaluationPolicy(EvaluationClosedModel):
    policyVersion: Literal["grid-model-per-game-gate-v2"]
    metricsVersion: Literal["grid-correction-metrics-v1"]
    minimumControlPhotos: Literal[5]
    minimumControlBoards: Literal[15]
    nonRegression: list[Literal["boards_matched", "boards_correct", "normalized_error"]]
    fullPhotoNonRegression: list[
        Literal["false_boards", "duplicate_predictions", "photo_complete_correct"]
    ]
    currentGameImprovementRole: Literal["REGRESSION"]
    minimumCorrectBoardGain: Literal[1]
    minimumRelativeErrorReduction: float = Field(ge=0, le=1, allow_inf_nan=False)
    minimumAbsoluteErrorReduction: float = Field(ge=0, le=1, allow_inf_nan=False)
    epsilon: float = Field(ge=0, allow_inf_nan=False)
    checkpointRule: Literal["validation-board-correct-photo-macro-error-earliest-v1"]


class GridCorrectionEvaluationScope(EvaluationClosedModel):
    currentGameId: UUID
    trainingGameIds: list[UUID]
    priorVerifiedGameIds: list[UUID]
    priorScopeDocumented: bool
    exclusions: list[GridModelEvaluationExclusion]


class GridCorrectionCheckpointMetrics(EvaluationClosedModel):
    boardCorrectRate: float = Field(ge=0, le=1, allow_inf_nan=False)
    normalizedError: float = Field(ge=0, le=1, allow_inf_nan=False)


class GridCorrectionEarlyStopping(EvaluationClosedModel):
    patience: int = Field(ge=1)
    evaluationsWithoutImprovement: int = Field(ge=0)
    stopped: bool


class GridCorrectionCheckpointSelection(EvaluationClosedModel):
    rule: Literal["validation-board-correct-photo-macro-error-earliest-v1"]
    role: Literal["VALIDATION"]
    step: int = Field(ge=0)
    metrics: GridCorrectionCheckpointMetrics
    earlyStopping: GridCorrectionEarlyStopping


class GridCorrectionEvaluationReport(EvaluationClosedModel):
    schemaVersion: Literal["grid-model-evaluation-read-v3"]
    producer: Literal["server:grid-model-evaluator-v1"]
    policyVersion: Literal["grid-model-per-game-gate-v2"]
    policy: GridCorrectionEvaluationPolicy
    versionId: UUID
    manifestSha256: str = Field(pattern=_SHA)
    baseVersionId: UUID
    baseManifestSha256: str = Field(pattern=_SHA)
    familyId: UUID
    trainingGameId: UUID
    parity: GridModelEvaluationParity
    cohorts: list[GridModelEvaluationCohortPin]
    requiredGameIds: list[UUID]
    games: list[GridCorrectionEvaluationGame]
    verdict: Verdict
    scope: GridCorrectionEvaluationScope
    evidenceLevel: Literal["photo-only"]
    limitations: list[str]
    checkpointSelection: GridCorrectionCheckpointSelection


class GridScreenCorrectionEvaluationGame(GridCorrectionEvaluationDecision):
    gameId: UUID
    cohortId: UUID
    mode: Literal["screen+grid"]
    targetMetric: Literal["boards_correct_or_normalized_error"]
    roles: GridCorrectionEvaluationRoles


class GridScreenCorrectionEvaluationPolicy(EvaluationClosedModel):
    policyVersion: Literal["grid-model-per-game-gate-v3"]
    metricsVersion: Literal["grid-correction-metrics-v1"]
    minimumControlPhotos: Literal[5]
    minimumControlBoards: Literal[15]
    nonRegression: list[Literal["boards_matched", "boards_correct", "normalized_error"]]
    fullPhotoNonRegression: list[
        Literal["false_boards", "duplicate_predictions", "photo_complete_correct"]
    ]
    currentGameImprovementRole: Literal["REGRESSION"]
    minimumCorrectBoardGain: Literal[1]
    minimumRelativeErrorReduction: float = Field(ge=0, le=1, allow_inf_nan=False)
    minimumAbsoluteErrorReduction: float = Field(ge=0, le=1, allow_inf_nan=False)
    epsilon: float = Field(ge=0, allow_inf_nan=False)
    checkpointRule: Literal["validation-photo-board-correct-photo-macro-error-earliest-v1"]

    validationAssessment: Literal["full-photos-v1"]
    regressionAssessment: Literal["human-labeled-targets-v1"]


class GridScreenCorrectionCheckpointMetrics(EvaluationClosedModel):
    boardCorrectRate: float = Field(ge=0, le=1, allow_inf_nan=False)
    normalizedError: float = Field(ge=0, le=1, allow_inf_nan=False)

    photoCorrectRate: float = Field(ge=0, le=1, allow_inf_nan=False)


class GridScreenCorrectionCheckpointSelection(EvaluationClosedModel):
    rule: Literal["validation-photo-board-correct-photo-macro-error-earliest-v1"]
    role: Literal["VALIDATION"]
    step: int = Field(ge=0)
    metrics: GridScreenCorrectionCheckpointMetrics
    earlyStopping: GridCorrectionEarlyStopping

    selectionInputSha256: str = Field(pattern=_SHA)
    metricStateVersion: Literal["photo-board-checkpoint-state-v1"]


class GridScreenCorrectionEvaluationReport(EvaluationClosedModel):
    schemaVersion: Literal["grid-model-evaluation-read-v4"]
    producer: Literal["server:grid-model-evaluator-v1"]
    policyVersion: Literal["grid-model-per-game-gate-v3"]
    policy: GridScreenCorrectionEvaluationPolicy
    versionId: UUID
    manifestSha256: str = Field(pattern=_SHA)
    baseVersionId: UUID
    baseManifestSha256: str = Field(pattern=_SHA)
    familyId: UUID
    trainingGameId: UUID
    parity: GridModelEvaluationParity
    cohorts: list[GridModelEvaluationCohortPin]
    requiredGameIds: list[UUID]
    games: list[GridScreenCorrectionEvaluationGame]
    verdict: Verdict
    scope: GridCorrectionEvaluationScope
    evidenceLevel: Literal["photo-only"]
    limitations: list[str]
    checkpointSelection: GridScreenCorrectionCheckpointSelection


class GridCalibratedEvaluationReport(EvaluationClosedModel):
    schemaVersion: Literal["grid-model-evaluation-read-v5"]
    rawQualitySchemaVersion: Literal[
        "grid-model-evaluation-read-v3", "grid-model-evaluation-read-v4"
    ]
    producer: Literal["server:grid-model-evaluator-v1"]
    policyVersion: Literal["grid-model-per-game-gate-v2", "grid-model-per-game-gate-v3"]
    policy: GridCorrectionEvaluationPolicy | GridScreenCorrectionEvaluationPolicy
    versionId: UUID
    manifestSha256: str = Field(pattern=_SHA)
    baseVersionId: UUID
    baseManifestSha256: str = Field(pattern=_SHA)
    familyId: UUID
    trainingGameId: UUID
    parity: GridModelEvaluationParity
    cohorts: list[GridModelEvaluationCohortPin]
    requiredGameIds: list[UUID]
    games: list[GridCorrectionEvaluationGame | GridScreenCorrectionEvaluationGame]
    verdict: Verdict
    scope: GridCorrectionEvaluationScope
    evidenceLevel: Literal["photo-only"]
    limitations: list[str]
    checkpointSelection: GridCorrectionCheckpointSelection | GridScreenCorrectionCheckpointSelection
    automaticCalibration: list[AutomaticCalibration]


class GridAssignedComparisonReport(EvaluationClosedModel):
    schemaVersion: Literal["grid-model-assigned-comparison-v1"]
    producer: Literal["server:grid-model-evaluator-v1"]
    policyVersion: Literal["grid-model-assigned-nonregression-v1"]
    versionId: UUID
    manifestSha256: str = Field(pattern=_SHA)
    baselineVersionId: UUID
    baselineManifestSha256: str = Field(pattern=_SHA)
    gameId: UUID
    assignmentRevision: int = Field(ge=0)
    cohort: GridModelEvaluationCohortPin
    parity: GridModelEvaluationParity
    roles: GridCorrectionEvaluationRoles
    decision: GridCorrectionEvaluationDecision
    verdict: Verdict
    evidenceLevel: Literal["photo-only"]
    limitations: list[str]


class GridModelEvaluationCurrentness(EvaluationClosedModel):
    gameId: UUID
    cohortId: UUID
    state: Literal["current", "stale", "missing", "unavailable"]
    noticeCount: int
    provenNoticeCount: int | None
    provenAt: str | None


class GridModelEvaluationView(EvaluationClosedModel):
    evaluationId: UUID
    reportId: UUID
    status: Literal[
        "created", "processing", "waiting_for_review", "completed", "failed", "cancelled"
    ]
    stage: str | None
    versionId: UUID
    baseVersionId: UUID
    trainingGameId: UUID
    cohorts: list[GridModelEvaluationCohortRef]
    progressCurrent: int
    progressTotal: int | None
    verdict: Verdict | None
    cancelRequested: bool
    errorCode: str | None
    createdAt: str
    updatedAt: str
    report: (
        Annotated[
            GridModelEvaluationReport
            | GridCorrectionEvaluationReport
            | GridScreenCorrectionEvaluationReport
            | GridCalibratedEvaluationReport
            | GridAssignedComparisonReport,
            Field(discriminator="schemaVersion"),
        ]
        | None
    )
    currentness: list[GridModelEvaluationCurrentness]
    assignedBaselineVersionId: UUID | None = None
    assignmentRevision: int | None = Field(default=None, ge=0)


class GridModelEvaluationList(EvaluationClosedModel):
    items: list[GridModelEvaluationView]


class GridModelEvaluationProofFailure(EvaluationClosedModel):
    gameId: UUID
    code: str


class GridModelEvaluationCurrentnessResult(EvaluationClosedModel):
    reportId: UUID
    currentness: list[GridModelEvaluationCurrentness]
    failures: list[GridModelEvaluationProofFailure]
