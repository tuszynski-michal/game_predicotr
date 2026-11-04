"""Public metadata only: no internal operation pins or artifact paths."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecognitionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["qualified", "unqualified", "stale", "unavailable"]
    reasonCodes: list[str]


class RecognitionCapabilities(BaseModel):
    boardRows: int
    boardColumns: int
    pageRows: int
    pageColumns: int


class GameRecognitionStatus(BaseModel):
    scope: Literal["current_game"]
    capabilities: RecognitionCapabilities | None
    evaluation: RecognitionDecision
    automatic: RecognitionDecision


class RescueExecutionStatus(BaseModel):
    state: Literal["completed", "consumed_without_result", "foreign_scope", "unavailable"]
    completedAttempts: int = Field(ge=0)
    consumedAttempts: int = Field(ge=0)
    reasonCodes: list[str]


class FrozenRecognitionStatus(BaseModel):
    scope: Literal["frozen_operation"]
    evaluation: RecognitionDecision
    automatic: RecognitionDecision
    reasonCodes: list[str]
    rescue: RescueExecutionStatus
    completeness: "CompletenessStatus"


class CompletenessStatus(BaseModel):
    state: Literal["measured", "unavailable"]
    measuredTargets: int = Field(ge=0)
    reasonCodes: list[str]
