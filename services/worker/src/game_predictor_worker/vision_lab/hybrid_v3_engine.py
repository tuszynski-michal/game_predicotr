"""TASK-0803 ``hybrid_v3`` engine: reference grids + ``neural_grid`` behind ``GeometryEngine``.

The reference grids are an input of the photo (``ReferenceSource``), not a call into the
production engine: in the application (TASK-0805) the source returns the production
engine's output for the same photo; in the lab it returns the snapshot labels (level B
labels are the production output, level S labels are corrections). ``reference_from_engine``
adapts any lab ``GeometryEngine`` to a source.

``detect`` maps the gate to the shared contract: a confident board is ``complete`` with no
reason, a ``needs_review`` board keeps its gate reasons, a board without any grid is
``unreadable`` with its reasons. The photo state is the first entry of
``GeometryResult.reasons`` (``HYBRID_V3_PHOTO_CONFIDENT`` or
``HYBRID_V3_PHOTO_NEEDS_REVIEW`` followed by the photo reasons). Per D-461 the result is
review/shadow output only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from .contracts import Board, GeometryEngine, GeometryResult, Point, Topology
from .hybrid_v3_gate import (
    GATE_VERSION,
    GateThresholds,
    NetworkBoard,
    PhotoDecision,
    ReferenceBoard,
    gate_photo,
)
from .neural_grid_data import ByteImage, FloatArray
from .neural_grid_inference import BoardDetection

MODEL_VERSION: Final = "hybrid-v3"
PHOTO_CONFIDENT: Final = "HYBRID_V3_PHOTO_CONFIDENT"
PHOTO_NEEDS_REVIEW: Final = "HYBRID_V3_PHOTO_NEEDS_REVIEW"
_FIT_FAILED: Final = "NEURAL_GRID_FIT_FAILED"

# Selected by the TASK-0803 calibration (development role = calibration set, run 1 ONNX
# export 2cd19738...-round3, ai_docs/quality/GRID_V3_HYBRID_GATE_20261002.md). Bound to that
# model: another neural_grid model needs its own calibration; freezing is TASK-0804's call.
RUN1_DEVELOPMENT_THRESHOLDS: Final = GateThresholds(
    min_quad_iou=0.90, max_node_error=0.04, max_fit_residual=0.005
)

ReferenceSource = Callable[[str, ByteImage, Topology], list[ReferenceBoard]]


class NetworkAnalyser(Protocol):
    model_version: str

    def analyse(self, rgb: ByteImage) -> list[BoardDetection]: ...


def network_boards(detections: list[BoardDetection]) -> list[NetworkBoard]:
    return [
        NetworkBoard(
            nodes=None if detection.nodes is None else np.asarray(detection.nodes, np.float32),
            fit_residual=detection.fit_residual,
            fit_inliers=detection.fit_inliers,
            fit_failed=_FIT_FAILED in detection.reasons or detection.nodes is None,
            score=detection.score,
            reasons=tuple(detection.reasons),
        )
        for detection in detections
    ]


def reference_from_geometry(result: GeometryResult) -> list[ReferenceBoard]:
    """Every reference board, in its position order; a board without 24 nodes has no grid."""

    boards = []
    for board in result.boards:
        nodes = (
            np.array([(p.x, p.y) for p in board.nodes], np.float32)
            if len(board.nodes) == 24
            else None
        )
        boards.append(ReferenceBoard(board.position_index, nodes))
    return boards


def reference_from_engine(engine: GeometryEngine) -> ReferenceSource:
    def source(source_id: str, rgb: ByteImage, topology: Topology) -> list[ReferenceBoard]:
        return reference_from_geometry(engine.detect(source_id, rgb, topology))

    return source


def _reading_order(quads: list[FloatArray]) -> list[int]:
    """Rows by centre y (half the median board height apart), then x (as neural_grid)."""

    if not quads:
        return []
    centres = np.array([q.mean(axis=0) for q in quads])
    heights = np.array([np.linalg.norm(q[3] - q[0]) for q in quads], dtype=float)
    tolerance = max(1.0, float(np.median(heights)) * 0.5)
    rows: list[list[int]] = []
    for index in sorted(range(len(quads)), key=lambda i: (centres[i, 1], centres[i, 0])):
        if rows and abs(centres[index, 1] - np.mean([centres[i, 1] for i in rows[-1]])) <= (
            tolerance
        ):
            rows[-1].append(index)
        else:
            rows.append([index])
    return [i for row in rows for i in sorted(row, key=lambda i: centres[i, 0])]


def geometry_from_decision(
    source_id: str,
    decision: PhotoDecision,
    topology: Topology,
    width: int,
    height: int,
    model_version: str,
) -> GeometryResult:
    with_grid = [d for d in decision.boards if d.nodes is not None]
    without_grid = [d for d in decision.boards if d.nodes is None]
    corners = [np.asarray(d.nodes)[[0, 5, 23, 18]] for d in with_grid]
    ordered = [with_grid[i] for i in _reading_order(corners)] + without_grid
    boards = []
    for position, item in enumerate(ordered):
        provenance = "model" if item.node_source == "network" else "baseline_proposal"
        if item.nodes is None:
            boards.append(
                Board(
                    position_index=position,
                    status="unreadable",
                    nodes=[],
                    reasons=list(item.reasons),
                )
            )
            continue
        boards.append(
            Board(
                position_index=position,
                status="complete" if item.state == "confident" else "needs_review",
                nodes=[
                    Point(x=float(x), y=float(y), provenance=provenance)  # type: ignore[arg-type]
                    for x, y in np.asarray(item.nodes)
                ],
                reasons=list(item.reasons),
            )
        )
    photo = PHOTO_CONFIDENT if decision.state == "confident" else PHOTO_NEEDS_REVIEW
    return GeometryResult(
        source_id=source_id,
        topology=topology,
        model_version=model_version,
        status="detected" if boards else "failed",
        boards=boards,
        reasons=[photo, *decision.reasons],
        width=width,
        height=height,
    )


class HybridV3Engine:
    """``GeometryEngine``: gate of reference grids against ``neural_grid`` grids."""

    def __init__(
        self,
        network: NetworkAnalyser,
        reference: ReferenceSource,
        thresholds: GateThresholds,
    ) -> None:
        self.network = network
        self.reference = reference
        self.thresholds = thresholds
        self.model_version = f"{MODEL_VERSION}:{GATE_VERSION}:{network.model_version}"

    def decide(self, source_id: str, rgb: ByteImage, topology: Topology) -> PhotoDecision:
        reference = self.reference(source_id, rgb, topology)
        network = network_boards(self.network.analyse(rgb))
        return gate_photo(reference, network, self.thresholds)

    def detect(self, source_id: str, rgb: NDArray[np.uint8], topology: Topology) -> GeometryResult:
        if topology.columns != 5 or topology.rows != 3:
            return GeometryResult(
                source_id=source_id,
                topology=topology,
                model_version=self.model_version,
                status="unsupported",
                reasons=["HYBRID_V3_TOPOLOGY_UNSUPPORTED"],
                width=int(rgb.shape[1]),
                height=int(rgb.shape[0]),
            )
        image = np.asarray(rgb, np.uint8)
        decision = self.decide(source_id, image, topology)
        return geometry_from_decision(
            source_id,
            decision,
            topology,
            int(image.shape[1]),
            int(image.shape[0]),
            self.model_version,
        )


__all__ = [
    "MODEL_VERSION",
    "PHOTO_CONFIDENT",
    "PHOTO_NEEDS_REVIEW",
    "RUN1_DEVELOPMENT_THRESHOLDS",
    "HybridV3Engine",
    "ReferenceSource",
    "geometry_from_decision",
    "network_boards",
    "reference_from_engine",
    "reference_from_geometry",
]
