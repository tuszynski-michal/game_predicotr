"""OpenAPI schemas for rules versions."""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from game_predictor_api.domain.rules import MAX_SPIN_COST, RulesVersionStatus
from game_predictor_api.schemas.catalog import ApiModel


class RulesVersionCreate(ApiModel):
    rows: int = Field(ge=1, le=32767)
    columns: int = Field(ge=1, le=32767)
    spin_cost: int = Field(ge=0, le=MAX_SPIN_COST)


class RulesVersionUpdate(ApiModel):
    rows: int | None = Field(default=None, ge=1, le=32767)
    columns: int | None = Field(default=None, ge=1, le=32767)
    spin_cost: int | None = Field(default=None, ge=0, le=MAX_SPIN_COST)

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field_name in ("rows", "columns", "spin_cost"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null.")
        return self


class RulesVersionResponse(ApiModel):
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    spin_cost: int
    status: RulesVersionStatus
    created_at: datetime
    published_at: datetime | None


class PaylineCreate(ApiModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    row_path: list[int] = Field(min_length=1, max_length=32767)
    display_order: int = Field(ge=0, le=2_147_483_647)
    is_active: bool = True


class PaylineUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    row_path: list[int] | None = Field(
        default=None,
        min_length=1,
        max_length=32767,
    )
    display_order: int | None = Field(
        default=None,
        ge=0,
        le=2_147_483_647,
    )
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        for field_name in ("name", "row_path", "display_order", "is_active"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null.")
        return self


class PaylineResponse(ApiModel):
    id: UUID
    rules_version_id: UUID
    code: str
    name: str
    row_path: list[int]
    display_order: int
    is_active: bool
