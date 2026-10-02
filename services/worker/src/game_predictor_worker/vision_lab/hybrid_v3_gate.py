"""TASK-0803 hybrid_v3 agreement gate: two grid sets of one photo -> per-board decisions.

Pure and engine independent. The *reference* grids are an input (in the application the
production engine's output for the same photo; in the lab the snapshot labels), the
*network* grids come from ``neural_grid``. Nothing here runs an engine or assumes a number
of boards.

Rules (recorded before calibration, TASK-0803):

* Pairing: Hungarian assignment maximising corner-quad IoU (corners = nodes 0, 5, 23, 18)
  over pairs with IoU >= ``PAIRING_MIN_IOU`` (0.5, the D-483 matching threshold). A pair
  below the calibrated ``min_quad_iou`` is a quad disagreement, not two lone boards.
* Node agreement: the largest node distance between the two grids over the reference
  TL-BR diagonal (the D-483 normalisation) must be <= ``max_node_error``.
* A board is ``confident`` only when it is paired, both grids are structurally valid, the
  network fit did not fail, the quads agree and the nodes agree. Every other board is
  ``needs_review`` with every applicable reason from the closed list ``BOARD_REASONS``.
  A board found only by the network (including a duplicate detection) is never confident.
* Weak network fit = the ``neural_grid`` fit failed (fewer RANSAC inliers than the preset
  minimum, ``NEURAL_GRID_FIT_FAILED``), no grid, or a non-finite residual. It is fixed, not
  calibrated.
* Node choice for a confident board: network nodes when the network fit residual is
  < ``max_fit_residual``, otherwise the reference nodes. A ``needs_review`` board keeps the
  reference nodes when it has a finite reference grid, otherwise the network nodes.
* The photo is the unit (D-484): it is ``confident`` only when it has at least one board,
  every board is confident and both sources returned the same number of boards.

``compare`` (threshold independent: pairing, IoU, node errors, validity) and ``decide``
(thresholds) are split so a calibration sweep pairs each photo once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np

from .neural_grid_data import CORNERS, FloatArray
from .neural_grid_inference import structurally_valid
from .neural_grid_metrics import board_errors, hungarian, quad_iou
from .neural_grid_protocol import METRIC_DEFINITION

GATE_VERSION: Final = "hybrid-v3-gate-v1"
PAIRING_MIN_IOU: Final[float] = float(METRIC_DEFINITION["match_min_iou"])
_UNPAIRABLE: Final = 1e9

# Closed list of board reasons (every needs_review board carries at least one).
QUAD_DISAGREEMENT: Final = "HYBRID_V3_QUAD_DISAGREEMENT"
NODE_DISAGREEMENT: Final = "HYBRID_V3_NODE_DISAGREEMENT"
NETWORK_ONLY: Final = "HYBRID_V3_NETWORK_ONLY"
REFERENCE_ONLY: Final = "HYBRID_V3_REFERENCE_ONLY"
NETWORK_FIT_WEAK: Final = "HYBRID_V3_NETWORK_FIT_WEAK"
BOARD_INVALID: Final = "HYBRID_V3_BOARD_INVALID"
BOARD_REASONS: Final = (
    QUAD_DISAGREEMENT,
    NODE_DISAGREEMENT,
    NETWORK_ONLY,
    REFERENCE_ONLY,
    NETWORK_FIT_WEAK,
    BOARD_INVALID,
)

# Closed list of photo reasons.
BOARD_COUNT_MISMATCH: Final = "HYBRID_V3_BOARD_COUNT_MISMATCH"
BOARD_NEEDS_REVIEW: Final = "HYBRID_V3_BOARD_NEEDS_REVIEW"
NO_BOARDS: Final = "HYBRID_V3_NO_BOARDS"
PHOTO_REASONS: Final = (BOARD_COUNT_MISMATCH, BOARD_NEEDS_REVIEW, NO_BOARDS)

State = Literal["confident", "needs_review"]
NodeSource = Literal["network", "reference"]


@dataclass(frozen=True, slots=True)
class GateThresholds:
    min_quad_iou: float
    max_node_error: float  # largest node distance / reference TL-BR diagonal
    max_fit_residual: float  # network nodes are chosen below this RMS residual / diagonal

    def __post_init__(self) -> None:
        if not PAIRING_MIN_IOU <= self.min_quad_iou <= 1:
            raise ValueError("HYBRID_V3_THRESHOLD_IOU_INVALID")
        if not 0 < self.max_node_error <= 1:
            raise ValueError("HYBRID_V3_THRESHOLD_NODES_INVALID")
        if not 0 <= self.max_fit_residual <= 1:
            raise ValueError("HYBRID_V3_THRESHOLD_RESIDUAL_INVALID")

    def as_dict(self) -> dict[str, float]:
        return {
            "min_quad_iou": self.min_quad_iou,
            "max_node_error": self.max_node_error,
            "max_fit_residual": self.max_fit_residual,
        }


@dataclass(frozen=True, slots=True)
class ReferenceBoard:
    """One reference board: 24 nodes in source pixels (``None`` = no grid) and its position."""

    position_index: int
    nodes: FloatArray | None


@dataclass(frozen=True, slots=True)
class NetworkBoard:
    """One ``neural_grid`` detection (``BoardDetection`` reduced to what the gate reads)."""

    nodes: FloatArray | None
    fit_residual: float | None
    fit_inliers: int
    fit_failed: bool
    score: float = 1.0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Pair:
    network_index: int
    reference_index: int
    quad_iou: float
    node_error_mean: float
    node_error_max: float


@dataclass(frozen=True, slots=True)
class Comparison:
    """Threshold-independent comparison of the two grid sets of one photo."""

    reference_nodes: tuple[FloatArray | None, ...]
    network_nodes: tuple[FloatArray | None, ...]
    reference_valid: tuple[bool, ...]
    network_valid: tuple[bool, ...]
    network_weak: tuple[bool, ...]
    network_residual: tuple[float | None, ...]
    pairs: tuple[Pair, ...]


@dataclass(frozen=True, slots=True)
class BoardDecision:
    state: State
    reasons: tuple[str, ...]
    reference_index: int | None  # index in the reference list
    network_index: int | None  # index in the network list
    nodes: FloatArray | None  # output nodes
    node_source: NodeSource | None
    quad_iou: float | None = None
    node_error_max: float | None = None
    node_error_mean: float | None = None
    fit_residual: float | None = None


@dataclass(frozen=True, slots=True)
class PhotoDecision:
    state: State
    reasons: tuple[str, ...]
    boards: tuple[BoardDecision, ...]
    reference_count: int
    network_count: int


def _finite(nodes: FloatArray | None) -> FloatArray | None:
    if nodes is None:
        return None
    values = np.asarray(nodes, dtype=np.float32)
    if values.size != 48:
        return None
    values = values.reshape(24, 2)
    return values if np.isfinite(values).all() else None


def _weak(board: NetworkBoard, nodes: FloatArray | None) -> bool:
    residual = board.fit_residual
    return board.fit_failed or nodes is None or residual is None or not math.isfinite(residual)


def _ordered(reasons: set[str]) -> tuple[str, ...]:
    return tuple(reason for reason in BOARD_REASONS if reason in reasons)


def compare(reference: list[ReferenceBoard], network: list[NetworkBoard]) -> Comparison:
    ref_nodes = tuple(_finite(board.nodes) for board in reference)
    net_nodes = tuple(_finite(board.nodes) for board in network)
    ious = np.zeros((len(net_nodes), len(ref_nodes)))
    for i, net in enumerate(net_nodes):
        for j, ref in enumerate(ref_nodes):
            if net is not None and ref is not None:
                ious[i, j] = quad_iou(net[list(CORNERS)], ref[list(CORNERS)])
    cost = np.where(ious >= PAIRING_MIN_IOU, 1.0 - ious, _UNPAIRABLE)
    pairs = []
    for i, j in hungarian(cost):
        if ious[i, j] < PAIRING_MIN_IOU:
            continue
        net, ref = net_nodes[i], ref_nodes[j]
        assert net is not None and ref is not None
        mean_error, max_error = board_errors(net, ref)
        pairs.append(Pair(i, j, float(ious[i, j]), mean_error, max_error))
    return Comparison(
        reference_nodes=ref_nodes,
        network_nodes=net_nodes,
        reference_valid=tuple(n is not None and structurally_valid(n) for n in ref_nodes),
        network_valid=tuple(n is not None and structurally_valid(n) for n in net_nodes),
        network_weak=tuple(_weak(b, n) for b, n in zip(network, net_nodes, strict=True)),
        network_residual=tuple(board.fit_residual for board in network),
        pairs=tuple(pairs),
    )


def decide(comparison: Comparison, thresholds: GateThresholds) -> PhotoDecision:
    """Decide every board of one photo; no board of either source is dropped."""

    c = comparison
    decisions: list[BoardDecision] = []
    for pair in c.pairs:
        i, j = pair.network_index, pair.reference_index
        reasons: set[str] = set()
        if not (c.network_valid[i] and c.reference_valid[j]):
            reasons.add(BOARD_INVALID)
        if c.network_weak[i]:
            reasons.add(NETWORK_FIT_WEAK)
        if pair.quad_iou < thresholds.min_quad_iou:
            reasons.add(QUAD_DISAGREEMENT)
        if not pair.node_error_max <= thresholds.max_node_error:
            reasons.add(NODE_DISAGREEMENT)
        state: State = "needs_review" if reasons else "confident"
        residual = c.network_residual[i]
        source: NodeSource = (
            "network"
            if state == "confident"
            and residual is not None
            and residual < thresholds.max_fit_residual
            else "reference"
        )
        decisions.append(
            BoardDecision(
                state=state,
                reasons=_ordered(reasons),
                reference_index=j,
                network_index=i,
                nodes=c.network_nodes[i] if source == "network" else c.reference_nodes[j],
                node_source=source,
                quad_iou=pair.quad_iou,
                node_error_max=pair.node_error_max,
                node_error_mean=pair.node_error_mean,
                fit_residual=residual,
            )
        )
    paired_reference = {pair.reference_index for pair in c.pairs}
    paired_network = {pair.network_index for pair in c.pairs}
    for j, ref in enumerate(c.reference_nodes):
        if j in paired_reference:
            continue
        reasons = {REFERENCE_ONLY}
        if not c.reference_valid[j]:
            reasons.add(BOARD_INVALID)
        decisions.append(
            BoardDecision(
                state="needs_review",
                reasons=_ordered(reasons),
                reference_index=j,
                network_index=None,
                nodes=ref,
                node_source="reference" if ref is not None else None,
            )
        )
    for i, net in enumerate(c.network_nodes):
        if i in paired_network:
            continue
        reasons = {NETWORK_ONLY}
        if not c.network_valid[i]:
            reasons.add(BOARD_INVALID)
        if c.network_weak[i]:
            reasons.add(NETWORK_FIT_WEAK)
        decisions.append(
            BoardDecision(
                state="needs_review",
                reasons=_ordered(reasons),
                reference_index=None,
                network_index=i,
                nodes=net,
                node_source="network" if net is not None else None,
                fit_residual=c.network_residual[i],
            )
        )
    references = len(c.reference_nodes)
    decisions.sort(
        key=lambda d: (
            d.reference_index if d.reference_index is not None else references,
            d.network_index if d.network_index is not None else -1,
        )
    )
    photo_reasons: list[str] = []
    if references != len(c.network_nodes):
        photo_reasons.append(BOARD_COUNT_MISMATCH)
    if any(decision.state != "confident" for decision in decisions):
        photo_reasons.append(BOARD_NEEDS_REVIEW)
    if not decisions:
        photo_reasons.append(NO_BOARDS)
    return PhotoDecision(
        state="needs_review" if photo_reasons else "confident",
        reasons=tuple(photo_reasons),
        boards=tuple(decisions),
        reference_count=references,
        network_count=len(c.network_nodes),
    )


def gate_photo(
    reference: list[ReferenceBoard], network: list[NetworkBoard], thresholds: GateThresholds
) -> PhotoDecision:
    return decide(compare(reference, network), thresholds)


__all__ = [
    "BOARD_REASONS",
    "GATE_VERSION",
    "PHOTO_REASONS",
    "BoardDecision",
    "Comparison",
    "GateThresholds",
    "NetworkBoard",
    "PhotoDecision",
    "ReferenceBoard",
    "compare",
    "decide",
    "gate_photo",
]
