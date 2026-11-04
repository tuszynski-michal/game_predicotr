"""Explicit geometry overrides; historical preset contracts remain unchanged."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class ClosedGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScreenInputGeometryV1(ClosedGeometry):
    longSide: Annotated[StrictInt, Field(gt=768, le=2048, multiple_of=32)]
    trainCanvas: tuple[
        Annotated[StrictInt, Field(ge=64, le=2048, multiple_of=32)],
        Annotated[StrictInt, Field(ge=64, le=2048, multiple_of=32)],
    ]


class BoardCropGeometryV1(ClosedGeometry):
    margin: float = Field(gt=0, le=0.5, allow_inf_nan=False)


class GridRescueVariantV1(ClosedGeometry):
    contractVersion: Literal["grid-rescue-variant-v1"] = "grid-rescue-variant-v1"
    preprocessingContract: Literal["neural-grid-rescue-preprocessing-v1"] = (
        "neural-grid-rescue-preprocessing-v1"
    )
    screen: ScreenInputGeometryV1 | None = None
    board: BoardCropGeometryV1 | None = None

    @model_validator(mode="after")
    def changed(self) -> GridRescueVariantV1:
        if self.screen is None and self.board is None:
            raise ValueError("A rescue variant requires an explicit geometry change.")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def require_baseline(self, margin: float) -> None:
        if not math.isfinite(margin) or (self.board is not None and self.board.margin <= margin):
            raise ValueError("Rescue margin must exceed the pinned baseline margin.")

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, enabled in (
                ("screen_only", self.screen is not None),
                ("board_only", self.board is not None),
                ("combined", self.screen is not None and self.board is not None),
            )
            if enabled
        )
