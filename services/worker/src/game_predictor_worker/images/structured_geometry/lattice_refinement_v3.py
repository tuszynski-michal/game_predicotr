"""Frame-conditioned, fail-closed refinement of one 3 x 5 symbol lattice."""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass, replace
from typing import Literal, cast

import cv2
import numpy as np
from game_predictor_api.domain.image_geometry_v2 import (
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
)
from numpy.typing import NDArray

from ..board_cell_geometry_contract import (
    BoardCellGeometryContractError,
    BoardCellTopology,
    derive_board_cell_quads,
)
from ..board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    BoardCellGeometryEstimate,
    estimate_board_cell_geometry,
)
from ..geometry import Point as DetectorPoint
from ..global_symbol_lattice import GlobalSymbolCandidate
from ..normalization import CanonicalSourceFrame
from ..rectification import BOARD_COLUMNS, BOARD_HEIGHT, BOARD_ROWS, BOARD_WIDTH
from ..symbol_grid_refinement import rectify_board
from .geometry_engine import SourceGeometryResult

STRUCTURED_LATTICE_REFINEMENT_V3_VERSION = (
    "structured-opencv-independent-board-refinement-v3-frame-conditioned-lattice-v1"
)
LATTICE_CONTENT_SAFETY_VERSION = "lattice-content-safety-v1"
STRUCTURED_LATTICE_CANDIDATE_CONFIG_VERSION = "structured-lattice-candidate-v3-config-v1"
STRUCTURED_LATTICE_ACTIVE_CONFIG_VERSION = "structured-lattice-active-v3-config-v1"
STRUCTURED_LATTICE_ACCEPTANCE_REPORT_CHECKSUM_SHA256 = (
    "6aeffdc182f04183fd0ae0f96721248531787169ff146aedfe5f2c29ee81a34c"
)
UNSUPPORTED_TOPOLOGY_CODE = "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED"
MINIMUM_CONTENT_MARGIN_PX = 4.0
CONTENT_MARGIN_SPACING_FRACTION = 0.05


class StructuredLatticeRefinementError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LatticeContentSafetyResult:
    status: Literal["passed", "failed", "unavailable"]
    version: str
    protected_candidate_count: int
    margin_x_px: float | None
    margin_y_px: float | None
    minimum_clearance_px: float | None
    reason_code: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "marginXPx": self.margin_x_px,
            "marginYPx": self.margin_y_px,
            "minimumClearancePx": self.minimum_clearance_px,
            "protectedCandidateCount": self.protected_candidate_count,
            "reasonCode": self.reason_code,
            "status": self.status,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class StructuredLatticeRefinementV3:
    status: Literal["estimated", "needs_review"]
    analysis_quad: SourceQuad
    board_frame_quad: SourceQuad | None
    symbol_grid_quad: SourceQuad | None
    final_quad: SourceQuad | None
    estimator_version: str
    local_lattice_version: str
    estimate: BoardCellGeometryEstimate
    content_safety: LatticeContentSafetyResult
    reason_code: str | None

    def __post_init__(self) -> None:
        if self.final_quad != self.symbol_grid_quad:
            raise ValueError("finalQuad must remain an alias of symbolGridQuad.")
        if self.status == "estimated" and self.symbol_grid_quad is None:
            raise ValueError("An estimated v3 lattice requires symbolGridQuad.")
        if self.status == "needs_review" and self.symbol_grid_quad is not None:
            raise ValueError("A deferred v3 lattice cannot expose fallback geometry.")

    def to_payload(self) -> dict[str, object]:
        return {
            "analysisQuad": self.analysis_quad.to_dict(),
            "boardFrameQuad": (
                None if self.board_frame_quad is None else self.board_frame_quad.to_dict()
            ),
            "contentSafety": self.content_safety.to_payload(),
            "estimatorDiagnostics": self.estimate.to_dict(),
            "estimatorVersion": self.estimator_version,
            "finalQuad": None if self.final_quad is None else self.final_quad.to_dict(),
            "localLatticeStatus": self.status,
            "localLatticeVersion": self.local_lattice_version,
            "reasonCode": self.reason_code,
            "symbolGridQuad": (
                None if self.symbol_grid_quad is None else self.symbol_grid_quad.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class StructuredLatticeShadowResultV3:
    source_checksum_sha256: str
    normalized_pixel_checksum_sha256: str
    upstream_result_checksum_sha256: str
    config_checksum_sha256: str
    boards: tuple[dict[str, object], ...]

    def _payload(self) -> dict[str, object]:
        return {
            "activationAllowed": False,
            "boards": list(self.boards),
            "candidateRole": "measurement_only",
            "configChecksumSha256": self.config_checksum_sha256,
            "configVersion": STRUCTURED_LATTICE_CANDIDATE_CONFIG_VERSION,
            "geometryOriginPolicy": "frame_conditioned_symbol_lattice_without_crop_authority",
            "normalizedPixelChecksumSha256": self.normalized_pixel_checksum_sha256,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "upstreamResultChecksumSha256": self.upstream_result_checksum_sha256,
        }

    @property
    def result_checksum_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self._payload())).hexdigest()

    def to_payload(self) -> dict[str, object]:
        payload = self._payload()
        payload["resultChecksumSha256"] = self.result_checksum_sha256
        return payload


def structured_lattice_candidate_config_payload() -> dict[str, object]:
    return {
        "activationAllowed": False,
        "configVersion": STRUCTURED_LATTICE_CANDIDATE_CONFIG_VERSION,
        "contentMarginSpacingFraction": CONTENT_MARGIN_SPACING_FRACTION,
        "contentSafetyVersion": LATTICE_CONTENT_SAFETY_VERSION,
        "estimatorVersion": ESTIMATOR_VERSION,
        "localLatticeVersion": STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
        "maturity": "experimental_measurement_only",
        "minimumContentMarginPx": MINIMUM_CONTENT_MARGIN_PX,
        "requireDisjointTuningAndEvaluation": True,
        "topology": {"columns": BOARD_COLUMNS, "rows": BOARD_ROWS},
    }


def structured_lattice_active_config_payload() -> dict[str, object]:
    return {
        **structured_lattice_candidate_config_payload(),
        "acceptanceReportChecksumSha256": (STRUCTURED_LATTICE_ACCEPTANCE_REPORT_CHECKSUM_SHA256),
        "activationAllowed": True,
        "configVersion": STRUCTURED_LATTICE_ACTIVE_CONFIG_VERSION,
        "maturity": "accepted_primary",
    }


def evaluate_structured_lattice_shadow_v3(
    frame: CanonicalSourceFrame,
    upstream: SourceGeometryResult,
    *,
    config_checksum_sha256: str,
    topology: BoardCellTopology,
) -> StructuredLatticeShadowResultV3:
    if (
        upstream.source_checksum_sha256 != frame.source.source_checksum_sha256
        or upstream.normalized_pixel_checksum_sha256
        != frame.source.normalized_pixel_checksum_sha256
    ):
        raise ValueError("The v3 shadow source differs from its structured upstream result.")
    boards: list[dict[str, object]] = []
    for board in upstream.boards:
        analysis_quad = board.final_quad
        if analysis_quad is None:
            boards.append(
                {
                    "analysisQuad": None,
                    "boardFrameQuad": None,
                    "contentSafety": _safety_unavailable().to_payload(),
                    "finalQuad": None,
                    "localLatticeStatus": "needs_review",
                    "localLatticeVersion": STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
                    "positionIndex": board.slot.position_index,
                    "reasonCode": "insufficient_lattice_evidence",
                    "sequenceNumber": board.slot.sequence_number,
                    "symbolGridQuad": None,
                }
            )
            continue
        refined = refine_structured_symbol_lattice_v3(
            frame.rgb,
            analysis_quad=analysis_quad,
            board_frame_quad=analysis_quad,
            topology=topology,
        )
        boards.append(
            {
                **refined.to_payload(),
                "positionIndex": board.slot.position_index,
                "sequenceNumber": board.slot.sequence_number,
            }
        )
    return StructuredLatticeShadowResultV3(
        source_checksum_sha256=frame.source.source_checksum_sha256,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        upstream_result_checksum_sha256=upstream.result_checksum_sha256,
        config_checksum_sha256=config_checksum_sha256,
        boards=tuple(boards),
    )


def refine_structured_symbol_lattice_v3(
    source_rgb: NDArray[np.uint8],
    *,
    analysis_quad: SourceQuad,
    board_frame_quad: SourceQuad | None,
    topology: BoardCellTopology,
) -> StructuredLatticeRefinementV3:
    if not topology.is_legacy_3x5:
        raise StructuredLatticeRefinementError(
            UNSUPPORTED_TOPOLOGY_CODE,
            "Structured lattice refinement v3 supports only a 3 x 5 topology.",
        )
    estimate = estimate_board_cell_geometry(source_rgb, _detector_quad(analysis_quad))
    if estimate.status != "estimated" or estimate.lattice_bounds_quad is None:
        return _deferred(
            analysis_quad,
            board_frame_quad,
            estimate,
            estimate.fallback_reason or "insufficient_lattice_evidence",
        )
    safety = evaluate_lattice_content_safety(estimate)
    if safety.status == "failed":
        estimate = _adjust_lattice_to_content(
            source_rgb,
            analysis_quad=analysis_quad,
            estimate=estimate,
        )
        safety = evaluate_lattice_content_safety(estimate)
    if safety.status != "passed":
        return _deferred(
            analysis_quad,
            board_frame_quad,
            estimate,
            safety.reason_code or "content_safety_unavailable",
            safety=safety,
        )
    if estimate.lattice_bounds_quad is None:
        return _deferred(
            analysis_quad,
            board_frame_quad,
            estimate,
            "source_support_incomplete",
            safety=safety,
        )
    symbol_grid_quad = _source_quad(estimate.lattice_bounds_quad)
    return StructuredLatticeRefinementV3(
        status="estimated",
        analysis_quad=analysis_quad,
        board_frame_quad=board_frame_quad,
        symbol_grid_quad=symbol_grid_quad,
        final_quad=symbol_grid_quad,
        estimator_version=ESTIMATOR_VERSION,
        local_lattice_version=STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
        estimate=estimate,
        content_safety=safety,
        reason_code=None,
    )


def evaluate_lattice_content_safety(
    estimate: BoardCellGeometryEstimate,
) -> LatticeContentSafetyResult:
    matrix = estimate.ideal_to_observed_matrix
    if (
        estimate.status != "estimated"
        or matrix is None
        or len(estimate.assigned_candidate_indices) != BOARD_ROWS * BOARD_COLUMNS
        or len(estimate.global_column_bases) != BOARD_COLUMNS
        or len(estimate.global_row_bases) != BOARD_ROWS
    ):
        return _safety_unavailable()
    observed_to_ideal = np.linalg.inv(np.asarray(matrix, dtype=np.float64))
    column_spacing = statistics.median(
        estimate.global_column_bases[index + 1] - estimate.global_column_bases[index]
        for index in range(BOARD_COLUMNS - 1)
    )
    row_spacing = statistics.median(
        estimate.global_row_bases[index + 1] - estimate.global_row_bases[index]
        for index in range(BOARD_ROWS - 1)
    )
    margin_x = max(MINIMUM_CONTENT_MARGIN_PX, CONTENT_MARGIN_SPACING_FRACTION * column_spacing)
    margin_y = max(MINIMUM_CONTENT_MARGIN_PX, CONTENT_MARGIN_SPACING_FRACTION * row_spacing)
    candidates = {
        candidate.candidate_index: candidate for candidate in estimate.rectified_candidates
    }
    clearances: list[float] = []
    protected_count = 0
    inlier_slots = set(estimate.inlier_slots)
    for row, column in sorted(inlier_slots):
        candidate_index = estimate.assigned_candidate_indices[row * BOARD_COLUMNS + column]
        if candidate_index is None or candidate_index not in candidates:
            continue
        candidate = candidates[candidate_index]
        if not _is_reliable_content_candidate(
            candidate,
            column_spacing=column_spacing,
            row_spacing=row_spacing,
            margin_x=margin_x,
            margin_y=margin_y,
        ):
            continue
        protected_count += 1
        ideal_bbox = _protected_bbox_in_ideal(
            candidate,
            observed_to_ideal,
            margin_x=margin_x,
            margin_y=margin_y,
        )
        left, top, right, bottom = ideal_bbox
        cell_left = column * (BOARD_WIDTH / BOARD_COLUMNS)
        cell_right = (column + 1) * (BOARD_WIDTH / BOARD_COLUMNS)
        cell_top = row * (BOARD_HEIGHT / BOARD_ROWS)
        cell_bottom = (row + 1) * (BOARD_HEIGHT / BOARD_ROWS)
        # The outer lattice boundary is deliberately allowed to include extra
        # background.  This guard protects only separators shared by adjacent
        # cells; treating the four outer edges as separators rejects valid
        # edge symbols and defeats the wider-analysis-quad contract.
        internal_clearances: list[float] = []
        if column > 0:
            internal_clearances.append(left - cell_left)
        if column < BOARD_COLUMNS - 1:
            internal_clearances.append(cell_right - right)
        if row > 0:
            internal_clearances.append(top - cell_top)
        if row < BOARD_ROWS - 1:
            internal_clearances.append(cell_bottom - bottom)
        clearance = min(internal_clearances)
        clearances.append(clearance)
        if clearance < 0:
            return LatticeContentSafetyResult(
                status="failed",
                version=LATTICE_CONTENT_SAFETY_VERSION,
                protected_candidate_count=protected_count,
                margin_x_px=round(margin_x, 4),
                margin_y_px=round(margin_y, 4),
                minimum_clearance_px=round(clearance, 4),
                reason_code="content_boundary_conflict",
            )
    if protected_count == 0 or not clearances:
        return _safety_unavailable()
    return LatticeContentSafetyResult(
        status="passed",
        version=LATTICE_CONTENT_SAFETY_VERSION,
        protected_candidate_count=protected_count,
        margin_x_px=round(margin_x, 4),
        margin_y_px=round(margin_y, 4),
        minimum_clearance_px=round(min(clearances), 4),
        reason_code=None,
    )


def _is_reliable_content_candidate(
    candidate: GlobalSymbolCandidate,
    *,
    column_spacing: float,
    row_spacing: float,
    margin_x: float,
    margin_y: float,
) -> bool:
    """Exclude clipped or merged bright regions from bbox-based safety proof.

    The component locator deliberately uses a permissive value mask to find
    symbol centres.  A region touching the rectified analysis border or wider
    than one protected lattice slot is useful as centre evidence, but its bbox
    is not evidence of one symbol's physical extent (glare and adjacent bright
    artwork commonly merge there).
    """

    return (
        not candidate.touches_border
        and _candidate_width(candidate) + 2.0 * margin_x < column_spacing
        and _candidate_height(candidate) + 2.0 * margin_y < row_spacing
    )


def _adjust_lattice_to_content(
    source_rgb: NDArray[np.uint8],
    *,
    analysis_quad: SourceQuad,
    estimate: BoardCellGeometryEstimate,
) -> BoardCellGeometryEstimate:
    """Find the smallest affine lattice expansion satisfying trusted bboxes.

    RANSAC determines projective orientation from symbol centres.  This bounded
    second step changes only the canonical origin and spacing, independently
    per axis, so separators can move into observed gaps without translating a
    board toward its decorative frame.
    """

    matrix = estimate.ideal_to_observed_matrix
    if matrix is None:
        return estimate
    observed_to_ideal = np.linalg.inv(np.asarray(matrix, dtype=np.float64))
    column_spacing = statistics.median(
        estimate.global_column_bases[index + 1] - estimate.global_column_bases[index]
        for index in range(BOARD_COLUMNS - 1)
    )
    row_spacing = statistics.median(
        estimate.global_row_bases[index + 1] - estimate.global_row_bases[index]
        for index in range(BOARD_ROWS - 1)
    )
    margin_x = max(MINIMUM_CONTENT_MARGIN_PX, CONTENT_MARGIN_SPACING_FRACTION * column_spacing)
    margin_y = max(MINIMUM_CONTENT_MARGIN_PX, CONTENT_MARGIN_SPACING_FRACTION * row_spacing)
    candidates = {
        candidate.candidate_index: candidate for candidate in estimate.rectified_candidates
    }
    protected: list[tuple[int, int, tuple[float, float, float, float]]] = []
    for row, column in sorted(set(estimate.inlier_slots)):
        candidate_index = estimate.assigned_candidate_indices[row * BOARD_COLUMNS + column]
        candidate = None if candidate_index is None else candidates.get(candidate_index)
        if candidate is None or not _is_reliable_content_candidate(
            candidate,
            column_spacing=column_spacing,
            row_spacing=row_spacing,
            margin_x=margin_x,
            margin_y=margin_y,
        ):
            continue
        protected.append(
            (
                row,
                column,
                _protected_bbox_in_ideal(
                    candidate,
                    observed_to_ideal,
                    margin_x=margin_x,
                    margin_y=margin_y,
                ),
            )
        )
    if not protected:
        return estimate
    x_transform = _smallest_feasible_axis_transform(
        count=BOARD_COLUMNS,
        extent=float(BOARD_WIDTH),
        constraints=tuple((column, left, right) for _, column, (left, _, right, _) in protected),
    )
    y_transform = _smallest_feasible_axis_transform(
        count=BOARD_ROWS,
        extent=float(BOARD_HEIGHT),
        constraints=tuple((row, top, bottom) for row, _, (_, top, _, bottom) in protected),
    )
    if x_transform is None or y_transform is None:
        return estimate
    x_offset, x_scale = x_transform
    y_offset, y_scale = y_transform
    new_to_old = np.asarray(
        ((x_scale, 0.0, x_offset), (0.0, y_scale, y_offset), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    adjusted = np.asarray(matrix, dtype=np.float64) @ new_to_old
    _, source_to_analysis = rectify_board(source_rgb, _detector_quad(analysis_quad))
    try:
        analysis_to_source = np.linalg.inv(source_to_analysis)
    except np.linalg.LinAlgError:
        return estimate
    ideal_to_source = analysis_to_source @ adjusted
    canonical_bounds = np.asarray(
        ((0.0, 0.0), (BOARD_WIDTH, 0.0), (BOARD_WIDTH, BOARD_HEIGHT), (0.0, BOARD_HEIGHT)),
        dtype=np.float32,
    )
    projected = cv2.perspectiveTransform(
        canonical_bounds.reshape((-1, 1, 2)), ideal_to_source.astype(np.float64)
    ).reshape((-1, 2))
    if not np.isfinite(projected).all():
        return estimate
    bounds = cast(
        tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
        tuple((round(float(x), 4), round(float(y), 4)) for x, y in projected),
    )
    source_height, source_width = source_rgb.shape[:2]
    try:
        cells = derive_board_cell_quads(
            bounds,
            source_image_width=source_width,
            source_image_height=source_height,
        )
    except BoardCellGeometryContractError:
        return estimate
    return replace(
        estimate,
        lattice_bounds_quad=bounds,
        cells=cells,
        ideal_to_observed_matrix=cast(
            tuple[
                tuple[float, float, float],
                tuple[float, float, float],
                tuple[float, float, float],
            ],
            tuple(tuple(float(value) for value in row) for row in adjusted),
        ),
    )


def _smallest_feasible_axis_transform(
    *,
    count: int,
    extent: float,
    constraints: tuple[tuple[int, float, float], ...],
) -> tuple[float, float] | None:
    step = extent / count
    candidates: list[tuple[float, float, float]] = []
    # At most 8% expansion/contraction; ordered around identity and evaluated
    # deterministically at sub-pixel boundary precision.
    for scale_step in range(-160, 161):
        scale = 1.0 + scale_step * 0.0005
        lower = -math.inf
        upper = math.inf
        for slot, protected_lower, protected_upper in constraints:
            if slot > 0:
                upper = min(upper, protected_lower - slot * step * scale)
            if slot < count - 1:
                lower = max(lower, protected_upper - (slot + 1) * step * scale)
        if lower > upper:
            continue
        offset = min(max(0.0, lower), upper)
        objective = abs(scale - 1.0) * extent + abs(offset)
        candidates.append((round(objective, 8), scale, offset))
    if not candidates:
        return None
    _, scale, offset = min(candidates)
    return (offset, scale)


def _protected_bbox_in_ideal(
    candidate: GlobalSymbolCandidate,
    observed_to_ideal: NDArray[np.float64],
    *,
    margin_x: float,
    margin_y: float,
) -> tuple[float, float, float, float]:
    left = (
        candidate.core_left
        if candidate.core_left is not None
        else float(candidate.left)
        if candidate.left is not None
        else candidate.x - candidate.width / 2
    )
    top = (
        candidate.core_top
        if candidate.core_top is not None
        else float(candidate.top)
        if candidate.top is not None
        else candidate.y - candidate.height / 2
    )
    width = _candidate_width(candidate)
    height = _candidate_height(candidate)
    points = np.asarray(
        [
            [left - margin_x, top - margin_y],
            [left + width + margin_x, top - margin_y],
            [left + width + margin_x, top + height + margin_y],
            [left - margin_x, top + height + margin_y],
        ],
        dtype=np.float64,
    )
    projected = cv2.perspectiveTransform(points.reshape((-1, 1, 2)), observed_to_ideal).reshape(
        (-1, 2)
    )
    if not np.isfinite(projected).all():
        return (-math.inf, -math.inf, math.inf, math.inf)
    return (
        float(np.min(projected[:, 0])),
        float(np.min(projected[:, 1])),
        float(np.max(projected[:, 0])),
        float(np.max(projected[:, 1])),
    )


def _candidate_width(candidate: GlobalSymbolCandidate) -> float:
    return float(candidate.core_width if candidate.core_width is not None else candidate.width)


def _candidate_height(candidate: GlobalSymbolCandidate) -> float:
    return float(candidate.core_height if candidate.core_height is not None else candidate.height)


def _deferred(
    analysis_quad: SourceQuad,
    board_frame_quad: SourceQuad | None,
    estimate: BoardCellGeometryEstimate,
    reason_code: str,
    *,
    safety: LatticeContentSafetyResult | None = None,
) -> StructuredLatticeRefinementV3:
    return StructuredLatticeRefinementV3(
        status="needs_review",
        analysis_quad=analysis_quad,
        board_frame_quad=board_frame_quad,
        symbol_grid_quad=None,
        final_quad=None,
        estimator_version=ESTIMATOR_VERSION,
        local_lattice_version=STRUCTURED_LATTICE_REFINEMENT_V3_VERSION,
        estimate=estimate,
        content_safety=safety or _safety_unavailable(),
        reason_code=reason_code,
    )


def _safety_unavailable() -> LatticeContentSafetyResult:
    return LatticeContentSafetyResult(
        status="unavailable",
        version=LATTICE_CONTENT_SAFETY_VERSION,
        protected_candidate_count=0,
        margin_x_px=None,
        margin_y_px=None,
        minimum_clearance_px=None,
        reason_code="content_safety_unavailable",
    )


def _detector_quad(
    value: SourceQuad,
) -> tuple[DetectorPoint, DetectorPoint, DetectorPoint, DetectorPoint]:
    return cast(
        tuple[DetectorPoint, DetectorPoint, DetectorPoint, DetectorPoint],
        tuple(DetectorPoint(cast(int, point.x), cast(int, point.y)) for point in value.corners),
    )


def _source_quad(value: tuple[tuple[float, float], ...]) -> SourceQuad:
    return SourceQuad(
        corners=cast(
            tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
            tuple(SourcePoint(x, y) for x, y in value),
        )
    )


__all__ = [
    "CONTENT_MARGIN_SPACING_FRACTION",
    "LATTICE_CONTENT_SAFETY_VERSION",
    "MINIMUM_CONTENT_MARGIN_PX",
    "STRUCTURED_LATTICE_REFINEMENT_V3_VERSION",
    "STRUCTURED_LATTICE_CANDIDATE_CONFIG_VERSION",
    "STRUCTURED_LATTICE_ACTIVE_CONFIG_VERSION",
    "STRUCTURED_LATTICE_ACCEPTANCE_REPORT_CHECKSUM_SHA256",
    "LatticeContentSafetyResult",
    "StructuredLatticeRefinementError",
    "StructuredLatticeRefinementV3",
    "StructuredLatticeShadowResultV3",
    "evaluate_lattice_content_safety",
    "refine_structured_symbol_lattice_v3",
    "evaluate_structured_lattice_shadow_v3",
    "structured_lattice_candidate_config_payload",
    "structured_lattice_active_config_payload",
]
