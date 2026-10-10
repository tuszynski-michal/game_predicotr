"""Validated commands for independent saved stake selections."""

from enum import IntEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from game_predictor_api.domain.board_search import BoardSearchScope
from game_predictor_api.domain.management import ManagementCommand, ManagementValue

MANAGEMENT_STAKES = (2000, 1000, 600, 400, 200, 120)


class ManagementStake(IntEnum):
    TWENTY = 2000
    TEN = 1000
    SIX = 600
    FOUR = 400
    TWO = 200
    ONE_TWENTY = 120


class ManagementQueryCell(ManagementValue):
    cell_index: int = Field(ge=0, le=14)
    symbol_code: str | None = Field(default=None, max_length=64)


class ManagementSearchCommand(ManagementCommand):
    expected_revision: int = 0
    stake_grosze: ManagementStake
    cells: tuple[ManagementQueryCell, ...] = Field(min_length=1, max_length=15)
    scope: BoardSearchScope = BoardSearchScope.ALL_SEARCHABLE
    limit: int = Field(default=10, ge=1, le=100)


class ManagementSaveCommand(ManagementCommand):
    search_context_id: UUID
    start_sequence_number: int = Field(ge=1)
    spin_count: int = Field(ge=1, le=100000)
    pinned_spin_positions: tuple[int, ...] = Field(default=(), max_length=6)

    @field_validator("pinned_spin_positions")
    @classmethod
    def pins(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(type(value) is not int or not 0 <= value <= 100000 for value in values):
            raise ValueError("Pins must be spin positions between 0 and 100000.")
        if len(set(values)) != len(values):
            raise ValueError("Pins must be unique.")
        return tuple(sorted(values))


class ManagementClearCommand(ManagementCommand):
    confirmed: Literal[True]


class ManagementRefreshCommand(ManagementCommand):
    pass


class ManagementCorrectionCommand(ManagementCommand):
    expected_revision: int = 0
    expected_cell_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: Literal["approve", "reassign", "mark_unreadable", "mark_grid_issue"]
    target_symbol_code: str | None = Field(default=None, max_length=64)
    search_context_id: UUID | None = None
    start_sequence_number: int | None = Field(default=None, ge=1)
    spin_count: int | None = Field(default=None, ge=1, le=100000)
