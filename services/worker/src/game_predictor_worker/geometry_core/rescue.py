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


class BoardCropGeometryV2(ClosedGeometry):
    """Content experiment raster; V1's preset-sized crop remains unchanged."""

    margin: float = Field(gt=0, le=0.5, allow_inf_nan=False)
    canvas: tuple[StrictInt, StrictInt]

    @model_validator(mode="after")
    def paired(self) -> BoardCropGeometryV2:
        if (self.canvas, self.margin) not in (((320, 192), 0.15), ((480, 288), 0.30)):
            raise ValueError("CONTENT_BOARD_GEOMETRY_PAIR_INVALID")
        return self


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


class GridRescueVariantV2(ClosedGeometry):
    """One declared, trained content rescue route, never a V1 reinterpretation."""

    contractVersion: Literal["grid-content-rescue-variant-v1"] = "grid-content-rescue-variant-v1"
    preprocessingContract: Literal["neural-grid-content-preprocessing-v1"] = (
        "neural-grid-content-preprocessing-v1"
    )
    screen: ScreenInputGeometryV1 = ScreenInputGeometryV1(longSide=1280, trainCanvas=(1280, 960))
    board: BoardCropGeometryV2 = BoardCropGeometryV2(margin=0.30, canvas=(480, 288))

    @model_validator(mode="after")
    def fixed(self) -> GridRescueVariantV2:
        if self.screen.longSide != 1280 or self.screen.trainCanvas != (1280, 960):
            raise ValueError("CONTENT_SCREEN_GEOMETRY_INVALID")
        if self.board.canvas != (480, 288) or self.board.margin != 0.30:
            raise ValueError("CONTENT_RESCUE_GEOMETRY_INVALID")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def paths(self) -> tuple[str, ...]:
        return ("combined",)

    def require_baseline(self, margin: float) -> None:
        if not math.isfinite(margin) or margin != 0.15:
            raise ValueError("CONTENT_BASELINE_MARGIN_INVALID")
