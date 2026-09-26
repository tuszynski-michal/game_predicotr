"""Engine-independent laboratory contracts in EXIF-transposed source pixels."""

from typing import Literal, Protocol, Self

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, json_schema_serialization_defaults_required=True
    )


class Topology(Contract):
    columns: Literal[3, 5] = 5
    rows: Literal[3] = 3


class Point(Contract):
    x: float
    y: float
    provenance: Literal["baseline_proposal", "human", "model"] = "baseline_proposal"


class Cell(Contract):
    index: int
    asset_id: str | None = None
    status: Literal["available", "outside_source", "geometry_invalid"]


class Board(Contract):
    position_index: int
    status: Literal["complete", "partial", "needs_review", "absent", "occluded", "unreadable"]
    nodes: list[Point]
    reasons: list[str] = Field(default_factory=list)
    cells: list[Cell] = Field(default_factory=list)


class GeometryResult(Contract):
    source_id: str
    topology: Topology
    model_version: str
    status: Literal["detected", "failed", "unsupported", "invalid_image"]
    boards: list[Board] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    width: int = 0
    height: int = 0

    @model_validator(mode="after")
    def validate_grid_shape(self) -> Self:
        positions = [board.position_index for board in self.boards]
        if positions != sorted(set(positions)) or any(position < 0 for position in positions):
            raise ValueError("BOARD_ORDER_INVALID")
        expected = (self.topology.rows + 1) * (self.topology.columns + 1)
        for board in self.boards:
            no_geometry = board.status in {"absent", "occluded", "unreadable"} and not board.nodes
            if not no_geometry and len(board.nodes) != expected:
                raise ValueError("GRID_NODE_COUNT_INVALID")
            if no_geometry and board.cells:
                raise ValueError("GRID_CELLS_WITHOUT_GEOMETRY")
            if board.cells and [cell.index for cell in board.cells] != list(
                range(self.topology.rows * self.topology.columns)
            ):
                raise ValueError("GRID_CELL_ORDER_INVALID")
        return self


class GeometryEngine(Protocol):
    def detect(
        self, source_id: str, rgb: NDArray[np.uint8], topology: Topology
    ) -> GeometryResult: ...


class SymbolPrediction(Contract):
    symbol_id: str | None
    confidence: float = Field(ge=0, le=1)
    model_version: str
    preprocessing_version: str
    status: Literal["suggestion", "unknown", "unreadable", "grid_issue"]


class SymbolRecognizer(Protocol):
    def recognize(self, rgb: NDArray[np.uint8]) -> SymbolPrediction: ...


class Source(Contract):
    id: str
    game_id: str
    game_name: str
    filename: str
    sha256: str
    asset_id: str
    source_kind: Literal["folder", "database"]
    family_candidate: str
    family_verified: bool = False
    role: Literal["data", "comparison_only", "777_v2_declared"]
    training_eligible: Literal[False] = False
    duplicate_count: int = 1


class SourcePage(Contract):
    sources: list[Source]
    total: int
    games: dict[str, str]


class DetectRequest(Contract):
    source_id: str
    topology: Topology = Field(default_factory=Topology)
    preview_board: Board | None = None
