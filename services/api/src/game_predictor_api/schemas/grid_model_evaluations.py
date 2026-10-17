"""HTTP contract of grid model evaluations (TASK-0997, D-559).

The report is returned exactly as stored: structural keys are camelCase, metric
names keep the frozen ``neural-grid-metrics-v1`` snake_case spelling.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_SHA = r"^[0-9a-f]{64}$"
Decision = Literal["pass", "fail", "not_evaluable"]
Verdict = Literal["PASS", "REVISE", "NOT_EVALUABLE"]


class EvaluationClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GridModelEvaluationCohortRef(EvaluationClosedModel):
    gameId: UUID
    cohortId: UUID


class GridModelEvaluationCreate(EvaluationClosedModel):
    idempotencyKey: UUID
    versionId: UUID
    cohorts: list[GridModelEvaluationCohortRef] = Field(min_length=1, max_length=100)


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
    report: GridModelEvaluationReport | None
    currentness: list[GridModelEvaluationCurrentness]


class GridModelEvaluationList(EvaluationClosedModel):
    items: list[GridModelEvaluationView]


class GridModelEvaluationProofFailure(EvaluationClosedModel):
    gameId: UUID
    code: str


class GridModelEvaluationCurrentnessResult(EvaluationClosedModel):
    reportId: UUID
    currentness: list[GridModelEvaluationCurrentness]
    failures: list[GridModelEvaluationProofFailure]
