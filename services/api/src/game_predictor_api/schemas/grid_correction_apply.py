"""Closed contract for explicitly applying a correction-learning candidate."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, StrictBool, field_validator

from game_predictor_api.domain.jobs import JobStatus

from .grid_correction_learning import CorrectionLearningClosedModel, Sha256


class GridCorrectionApplyTarget(CorrectionLearningClosedModel):
    gameId: UUID
    gameLabel: str
    assignmentRevision: int = Field(ge=0)
    assignedVersionId: UUID | None
    requiresComparison: bool


class GridCorrectionApplyPreview(CorrectionLearningClosedModel):
    gameId: UUID
    learningId: UUID
    versionId: UUID | None
    versionLabel: str | None
    defaultRevision: int = Field(ge=0)
    defaultVersionId: UUID | None
    baseVersionId: UUID
    additionalGameIds: list[UUID]
    requiredGameIds: list[UUID]
    targets: list[GridCorrectionApplyTarget]
    excludedGameIds: list[UUID]
    limitations: list[str]
    evidenceLevel: Literal["photo-only"]
    blockers: list[str]
    canApply: bool
    previewSha256: Sha256


class GridCorrectionApplyStartCommand(CorrectionLearningClosedModel):
    idempotencyKey: UUID
    previewSha256: Sha256
    additionalGameIds: list[UUID] = Field(default_factory=list, max_length=7)
    confirmLimitedEvidence: StrictBool

    @field_validator("additionalGameIds")
    @classmethod
    def unique_games(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Additional games must be distinct.")
        return value


class GridCorrectionApplyStep(CorrectionLearningClosedModel):
    kind: Literal["publish", "set_default", "comparison", "activate"]
    gameId: UUID | None
    status: Literal["pending", "waiting", "completed"]
    receipt: dict[str, Any] | None = None


class GridCorrectionApplyView(CorrectionLearningClosedModel):
    applyId: UUID
    gameId: UUID
    learningId: UUID
    versionId: UUID
    status: JobStatus
    stage: str | None
    errorCode: str | None
    steps: list[GridCorrectionApplyStep]
    createdAt: str
    updatedAt: str


class GridCorrectionApplyList(CorrectionLearningClosedModel):
    items: list[GridCorrectionApplyView]
