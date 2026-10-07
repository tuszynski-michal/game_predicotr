"""Management value objects and validation, independent of HTTP and persistence."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from game_predictor_api.domain.catalog import GameStatus


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ManagementValue(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel, extra="forbid", from_attributes=True, populate_by_name=True
    )


class ManagementError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ManagementCommand(ManagementValue):
    operation_id: UUID
    expected_revision: int = Field(ge=0)


class ManagementPointCommand(ManagementCommand):
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=200)
    street: str = Field(min_length=1, max_length=200)
    archived: bool = False

    @field_validator("name", "city", "street")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value


class ManagementMachineCommand(ManagementCommand):
    name: str = Field(min_length=1, max_length=200)
    archived: bool = False

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value


class ManagementAssignmentCommand(ManagementCommand):
    game_ids: list[UUID] = Field(max_length=200)

    @field_validator("game_ids")
    @classmethod
    def unique_games(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Game assignments must be unique.")
        return sorted(values, key=str)


class ManagementAssignmentResponse(ManagementValue):
    game_id: UUID
    game_name: str
    game_status: GameStatus
    attached: bool


class ManagementMachineResponse(ManagementValue):
    id: UUID
    point_id: UUID
    name: str
    archived: bool
    revision: int
    updated_at: datetime
    assignments: list[ManagementAssignmentResponse]


class ManagementPointResponse(ManagementValue):
    id: UUID
    name: str
    city: str
    street: str
    archived: bool
    revision: int
    updated_at: datetime
    machines: list[ManagementMachineResponse]


class ManagementGameResponse(ManagementValue):
    id: UUID
    name: str


class ManagementSnapshotResponse(ManagementValue):
    points: list[ManagementPointResponse]
    active_games: list[ManagementGameResponse]
