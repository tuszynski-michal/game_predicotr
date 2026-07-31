"""OpenAPI schemas for games, symbols, and stable API errors."""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from game_predictor_api.domain.catalog import (
    DEFAULT_EXPECTED_LAYOUT_COUNT,
    MAX_EXPECTED_LAYOUT_COUNT,
    GameStatus,
    SymbolStatus,
)


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
    )


class ErrorResponse(ApiModel):
    code: str
    message: str
    details: dict[str, object]


class GameCreate(ApiModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    status: GameStatus = GameStatus.DRAFT
    expected_layout_count: int = Field(
        default=DEFAULT_EXPECTED_LAYOUT_COUNT,
        ge=1,
        le=MAX_EXPECTED_LAYOUT_COUNT,
    )


class GameUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: GameStatus | None = None
    expected_layout_count: int | None = Field(
        default=None,
        ge=1,
        le=MAX_EXPECTED_LAYOUT_COUNT,
    )

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null.")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null.")
        if (
            "expected_layout_count" in self.model_fields_set
            and self.expected_layout_count is None
        ):
            raise ValueError("expectedLayoutCount cannot be null.")
        return self


class GameResponse(ApiModel):
    id: UUID
    code: str
    name: str
    status: GameStatus
    expected_layout_count: int
    created_at: datetime
    updated_at: datetime


class SymbolCreate(ApiModel):
    mobile_code: int = Field(ge=1, le=32767)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    image_path: str | None = Field(default=None, max_length=500)
    is_wildcard: bool = False
    display_order: int = Field(ge=0)
    status: SymbolStatus = SymbolStatus.ACTIVE


class SymbolUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    image_path: str | None = Field(default=None, max_length=500)
    is_wildcard: bool | None = None
    display_order: int | None = Field(default=None, ge=0)
    status: SymbolStatus | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field_name in ("name", "is_wildcard", "display_order", "status"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{_to_camel(field_name)} cannot be null.")
        return self


class SymbolResponse(ApiModel):
    id: UUID
    game_id: UUID
    mobile_code: int
    code: str
    name: str
    image_path: str | None
    is_wildcard: bool
    display_order: int
    status: SymbolStatus
