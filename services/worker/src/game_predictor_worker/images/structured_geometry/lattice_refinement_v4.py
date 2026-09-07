"""Opt-in lateral partial proposals, after the unchanged complete v3 path."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Literal, cast

import cv2
import numpy as np
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    unavailable_source_cell_indices,
)
from numpy.typing import NDArray

from ..board_cell_geometry_contract import BoardCellTopology
from ..board_cell_geometry_estimator import BoardCellGeometryEstimate, _failure, _fit_axis_lattice
from ..global_symbol_lattice import GlobalSymbolCandidate, detect_global_symbol_candidates
from ..lateral_partial_contract import (
    AUTOMATIC_PARTIAL_PROPOSAL_VERSION,
    LATERAL_PARTIAL_POLICY_VERSION,
    LateralPartialGeometrySnapshot,
)
from ..page_geometry_registration import LateralPageRegistrationCandidate
from ..symbol_grid_refinement import SymbolGridRefinementError
from .lattice_refinement_v3 import (
    LatticeContentSafetyResult,
    StructuredLatticeRefinementV3,
    _deferred,
    evaluate_lattice_content_safety,
    refine_structured_symbol_lattice_v3,
)

# Frozen lateral-partial-v1 parameters. A change requires a new policy version.
_WIDTH, _HEIGHT = 500, 300
_MAX_CANDIDATES = 96
_MIN_INLIERS = 9
_RANSAC_THRESHOLD = 12.0
_MAX_P95_RESIDUAL = 10.0
_MAX_ORIGIN_SHIFT_PX = 45.0


@dataclass(frozen=True, slots=True)
class LateralLatticeProposal:
    symbol_grid_quad: SourceQuad
    qualification: GeometryQualification
    source_checksum_sha256: str
    position_index: int
    policy_checksum_sha256: str
    inlier_slots: tuple[tuple[int, int], ...]
    p95_residual_px: float
    column_offset: int
    content_safety: LatticeContentSafetyResult

    def __post_init__(self) -> None:
        if (
            self.qualification.completeness_status != "pending_partial"
            or not self.qualification.exclude_from_geometry_training
            or self.policy_checksum_sha256 != LateralPartialGeometrySnapshot().checksum_sha256
            or type(self.position_index) is not int
            or not 0 <= self.position_index < 9
            or len(self.source_checksum_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_checksum_sha256)
            or len(set(self.inlier_slots)) < _MIN_INLIERS
            or {row for row, _ in self.inlier_slots} != {0, 1, 2}
            or not 3 <= len({column for _, column in self.inlier_slots}) <= 5
            or any(not 0 <= column < 5 for _, column in self.inlier_slots)
            or not 0 <= self.p95_residual_px <= _MAX_P95_RESIDUAL
            or self.content_safety.status != "passed"
            or self.content_safety.protected_candidate_count < _MIN_INLIERS
        ):
            raise ValueError("An automatic lateral proposal requires complete guarded evidence.")

    def metadata_payload(self) -> dict[str, object]:
        """The automatic provenance contract is separate from manual decisions."""
        return {
            "version": AUTOMATIC_PARTIAL_PROPOSAL_VERSION,
            "origin": "automatic_proposal",
            "sourceChecksumSha256": self.source_checksum_sha256,
            "positionIndex": self.position_index + 1,
            "policyVersion": LATERAL_PARTIAL_POLICY_VERSION,
            "policyChecksumSha256": self.policy_checksum_sha256,
            "requiresManualConfirmation": True,
            "geometryQualification": self.qualification.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class StructuredLatticeRefinementV4:
    status: Literal["full", "pending_partial", "needs_review", "source_preparation_error"]
    baseline: StructuredLatticeRefinementV3
    proposal: LateralLatticeProposal | None = None
    reason_code: str | None = None
    additional_passes: int = 0
    hypothesis_count: int = 0

    def __post_init__(self) -> None:
        if (self.status == "full") != (self.baseline.status == "estimated"):
            raise ValueError("A complete v4 result must retain the accepted v3 baseline.")
        if (self.status == "pending_partial") != (self.proposal is not None):
            raise ValueError("Only an unconfirmed partial result can expose a lateral proposal.")
        if self.additional_passes not in (0, 1) or not 0 <= self.hypothesis_count <= 3:
            raise ValueError("The bounded lateral analysis budget was exceeded.")

    def to_payload(self) -> dict[str, object]:
        if self.status == "full":
            # Full boards retain the exact serialized v3 semantics as well.
            return self.baseline.to_payload()
        return {
            "localLatticeVersion": LATERAL_PARTIAL_POLICY_VERSION,
            "localLatticeStatus": self.status,
            "analysisQuad": self.baseline.analysis_quad.to_dict(),
            "symbolGridQuad": None
            if self.proposal is None
            else self.proposal.symbol_grid_quad.to_dict(),
            "automaticPartialProposal": None
            if self.proposal is None
            else self.proposal.metadata_payload(),
            "reasonCode": self.reason_code,
            "additionalPasses": self.additional_passes,
            "hypothesisCount": self.hypothesis_count,
            "excludeFromPageAnchors": self.proposal is not None,
            "baseline": self.baseline.to_payload(),
            "inlierSlots": []
            if self.proposal is None
            else [list(slot) for slot in self.proposal.inlier_slots],
            "p95ResidualPx": None if self.proposal is None else self.proposal.p95_residual_px,
            "columnOffset": None if self.proposal is None else self.proposal.column_offset,
            "contentSafety": None
            if self.proposal is None
            else self.proposal.content_safety.to_payload(),
        }


def refine_structured_symbol_lattice_v4(
    source_rgb: NDArray[np.uint8],
    *,
    analysis_quad: SourceQuad,
    board_frame_quad: SourceQuad | None,
    topology: BoardCellTopology,
    source_checksum_sha256: str,
    position_index: int,
    lateral_candidate: LateralPageRegistrationCandidate | None,
    policy: LateralPartialGeometrySnapshot,
) -> StructuredLatticeRefinementV4:
    try:
        baseline = refine_structured_symbol_lattice_v3(
            source_rgb,
            analysis_quad=analysis_quad,
            board_frame_quad=board_frame_quad,
            topology=topology,
        )
    except SymbolGridRefinementError as error:
        if error.code != "SYMBOL_GRID_QUAD_OUT_OF_BOUNDS":
            raise
        # Preserve the exact old rejection: no clamped v3 quad or fake estimate.
        baseline = _deferred(
            analysis_quad, board_frame_quad, _failure(error.code, candidate_count=0), error.code
        )
    if baseline.status == "estimated":
        return StructuredLatticeRefinementV4("full", baseline)
    height, width = source_rgb.shape[:2]
    if _vertical_clip(analysis_quad, height):
        return StructuredLatticeRefinementV4(
            "source_preparation_error", baseline, reason_code="source_vertical_crop_defect"
        )
    if lateral_candidate is None:
        return StructuredLatticeRefinementV4(
            "needs_review", baseline, reason_code="lateral_registration_unavailable"
        )
    if lateral_candidate.policy_checksum_sha256 != policy.checksum_sha256:
        raise ValueError("Lateral registration belongs to a different pinned policy.")
    initialization = lateral_candidate.initialization
    if position_index not in initialization.active_board_slots:
        raise ValueError("The lateral proposal does not attest this source slot.")
    quad = initialization.initialization_quads[
        initialization.active_board_slots.index(position_index)
    ]
    if tuple((point.x, point.y) for point in analysis_quad.corners) != tuple(
        (point.x, point.y) for point in quad
    ):
        raise ValueError("Lateral analysis quad differs from the attested registration proposal.")
    if not any(point.x < 0 or point.x > width - 1 for point in analysis_quad.corners):
        return StructuredLatticeRefinementV4(
            "needs_review", baseline, reason_code="lateral_source_support_required"
        )
    proposals, reason, hypotheses = _fit_lateral_lattice(
        source_rgb,
        analysis_quad=analysis_quad,
        source_checksum_sha256=source_checksum_sha256,
        position_index=position_index,
        policy=policy,
    )
    if len(proposals) != 1:
        return StructuredLatticeRefinementV4(
            "source_preparation_error"
            if reason == "source_vertical_crop_defect"
            else "needs_review",
            baseline,
            reason_code="ambiguous_column_indices" if len(proposals) > 1 else reason,
            additional_passes=1,
            hypothesis_count=hypotheses,
        )
    return StructuredLatticeRefinementV4(
        "pending_partial",
        baseline,
        proposal=proposals[0],
        additional_passes=1,
        hypothesis_count=hypotheses,
    )


def _supported_analysis(
    source_rgb: NDArray[np.uint8], analysis_quad: SourceQuad
) -> tuple[NDArray[np.uint8], NDArray[np.bool_], NDArray[np.float64]]:
    source_points = np.asarray([(p.x, p.y) for p in analysis_quad.corners], dtype=np.float32)
    target = np.asarray(
        [(0, 0), (_WIDTH - 1, 0), (_WIDTH - 1, _HEIGHT - 1), (0, _HEIGHT - 1)], dtype=np.float32
    )
    source_to_analysis = cv2.getPerspectiveTransform(source_points, target)
    inverse = np.linalg.inv(source_to_analysis)
    ys, xs = np.indices((_HEIGHT, _WIDTH), dtype=np.float32)
    points = np.stack([xs, ys], axis=-1).reshape(-1, 1, 2)
    mapped = cv2.perspectiveTransform(points, inverse).reshape(_HEIGHT, _WIDTH, 2)
    height, width = source_rgb.shape[:2]
    supported = (
        np.isfinite(mapped).all(axis=2)
        & (mapped[:, :, 0] >= 0)
        & (mapped[:, :, 0] <= width - 1)
        & (mapped[:, :, 1] >= 0)
        & (mapped[:, :, 1] <= height - 1)
    )
    analysis = cv2.remap(
        source_rgb,
        mapped[:, :, 0],
        mapped[:, :, 1],
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )
    analysis[~supported] = 0
    return (
        cast(NDArray[np.uint8], analysis),
        cast(NDArray[np.bool_], supported),
        cast(NDArray[np.float64], inverse),
    )


def _supported_candidates(
    analysis: NDArray[np.uint8], support: NDArray[np.bool_]
) -> tuple[GlobalSymbolCandidate, ...]:
    candidates = detect_global_symbol_candidates(analysis)
    selected = []
    for candidate in candidates:
        if candidate.touches_border or candidate.left is None or candidate.top is None:
            continue
        x, y = candidate.left, candidate.top
        # Include an extra sample ring: a component clipped against the source
        # mask is not a reliable symbol centre or complete content bbox.
        box = support[
            max(0, y - 1) : y + candidate.height + 1, max(0, x - 1) : x + candidate.width + 1
        ]
        if box.size and bool(box.all()):
            selected.append(candidate)
    return tuple(
        sorted(selected, key=lambda value: (-value.weight, value.candidate_index))[:_MAX_CANDIDATES]
    )


def _visible_assignments(
    candidates: tuple[GlobalSymbolCandidate, ...],
) -> tuple[tuple[tuple[int, int, GlobalSymbolCandidate], ...], int] | None:
    rows = _fit_axis_lattice(
        candidates,
        axis="y",
        count=3,
        limit=_HEIGHT,
        minimum_spacing=45,
        maximum_spacing=145,
        tolerance=25,
        maximum_support_per_line=5,
    )
    if rows is None:
        return None
    choices = []
    for count in (3, 4, 5):
        columns = _fit_axis_lattice(
            candidates,
            axis="x",
            count=count,
            limit=_WIDTH,
            minimum_spacing=45,
            maximum_spacing=135,
            tolerance=22,
            maximum_support_per_line=3,
        )
        if columns is None:
            continue
        assigned: dict[tuple[int, int], tuple[float, GlobalSymbolCandidate]] = {}
        for candidate in candidates:
            row = min(range(3), key=lambda index: abs(rows.bases[index] - candidate.y))
            column = min(range(count), key=lambda index: abs(columns.bases[index] - candidate.x))
            dx, dy = abs(columns.bases[column] - candidate.x), abs(rows.bases[row] - candidate.y)
            if dx > 25 or dy > 36:
                continue
            distance = dx / 25 + dy / 36 - 0.30 * candidate.weight
            current = assigned.get((row, column))
            if current is None or (distance, candidate.candidate_index) < (
                current[0],
                current[1].candidate_index,
            ):
                assigned[(row, column)] = (distance, candidate)
        values = tuple((row, column, value[1]) for (row, column), value in sorted(assigned.items()))
        if (
            len(values) >= _MIN_INLIERS
            and {r for r, _, _ in values} == {0, 1, 2}
            and len({c for _, c, _ in values}) == count
        ):
            choices.append((values, count, sum(value[0] for value in assigned.values())))
    if not choices:
        return None
    values, count, _ = min(choices, key=lambda choice: (-len(choice[0]), -choice[1], choice[2]))
    return values, count


def _fit_lateral_lattice(
    source_rgb: NDArray[np.uint8],
    *,
    analysis_quad: SourceQuad,
    source_checksum_sha256: str,
    position_index: int,
    policy: LateralPartialGeometrySnapshot,
) -> tuple[list[LateralLatticeProposal], str, int]:
    analysis, support, analysis_to_source = _supported_analysis(source_rgb, analysis_quad)
    candidates = _supported_candidates(analysis, support)
    assignments = _visible_assignments(candidates) if len(candidates) >= _MIN_INLIERS else None
    if assignments is None:
        return [], "insufficient_lateral_lattice_evidence", 0
    values, count = assignments
    ideal = np.asarray(
        [((column + 0.5) * 100, (row + 0.5) * 100) for row, column, _ in values], dtype=np.float64
    )
    observed = np.asarray(
        [(candidate.x, candidate.y) for _, _, candidate in values], dtype=np.float64
    )
    matrix, inlier_mask = _deterministic_lateral_fit(ideal, observed)
    if (
        matrix is None
        or inlier_mask is None
        or not np.isfinite(matrix).all()
        or abs(float(np.linalg.det(matrix))) < 1e-9
    ):
        return [], "lateral_homography_invalid", 0
    selected = tuple(index for index, keep in enumerate(inlier_mask.reshape(-1)) if keep)
    if (
        len(selected) < _MIN_INLIERS
        or {values[index][0] for index in selected} != {0, 1, 2}
        or len({values[index][1] for index in selected}) < 3
    ):
        return [], "insufficient_lateral_inliers", 0
    projected = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    p95 = float(
        np.percentile(
            np.linalg.norm(projected[list(selected)] - observed[list(selected)], axis=1), 95
        )
    )
    if not np.isfinite(p95) or p95 > _MAX_P95_RESIDUAL:
        return [], "lateral_residual_excessive", 0
    proposals = []
    reason = "lateral_index_origin_unconfirmed"
    for offset in range(6 - count):
        shifted = matrix @ np.asarray(
            [[1.0, 0.0, -offset * 100.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        )
        proposal, rejection = _evaluate_origin(
            shifted,
            values=values,
            selected=selected,
            offset=offset,
            candidates=candidates,
            analysis_to_source=analysis_to_source,
            source_shape=source_rgb.shape,
            p95=p95,
            policy=policy,
            source_checksum_sha256=source_checksum_sha256,
            position_index=position_index,
        )
        if proposal is not None:
            proposals.append(proposal)
        elif rejection is not None:
            priority = {
                "lateral_index_origin_unconfirmed": 0,
                "lateral_homography_invalid": 1,
                "lateral_source_geometry_invalid": 2,
                "lateral_source_support_required": 3,
                "content_boundary_conflict": 4,
                "insufficient_protected_lateral_content": 4,
                "source_vertical_crop_defect": 5,
            }
            if priority.get(rejection, 4) >= priority.get(reason, 0):
                reason = rejection
    return proposals, reason, 6 - count


def _deterministic_lateral_fit(
    ideal: NDArray[np.float64], observed: NDArray[np.float64]
) -> tuple[NDArray[np.float64] | None, NDArray[np.uint8] | None]:
    """One bounded RANSAC with local sampling; never change OpenCV's global RNG.

    At most 15 assignments produce 1,365 four-point subsets. Evaluate at most
    256 of them in fixed order, then refit the winning consensus once. This
    keeps retries stable without changing randomness of the next full v3 board.
    """
    subsets = tuple(combinations(range(len(ideal)), 4))
    if len(subsets) > 256:
        indices = np.random.default_rng(512).choice(len(subsets), size=256, replace=False)
        subsets = tuple(subsets[int(index)] for index in sorted(indices))
    winner: NDArray[np.bool_] | None = None
    best: tuple[int, float, float, tuple[int, ...]] | None = None
    for subset in subsets:
        matrix = cv2.getPerspectiveTransform(
            np.asarray(ideal[list(subset)], dtype=np.float32),
            np.asarray(observed[list(subset)], dtype=np.float32),
        )
        if not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-9:
            continue
        projected = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), matrix).reshape(-1, 2)
        residual = np.linalg.norm(projected - observed, axis=1)
        inliers = np.isfinite(residual) & (residual <= _RANSAC_THRESHOLD)
        count = int(inliers.sum())
        if count < _MIN_INLIERS:
            continue
        key = (
            -count,
            round(float(np.percentile(residual[inliers], 95)), 8),
            round(float(residual[inliers].sum()), 8),
            subset,
        )
        if best is None or key < best:
            best, winner = key, inliers
    if winner is None:
        return None, None
    matrix, _ = cv2.findHomography(ideal[winner], observed[winner], 0)
    if matrix is None or not np.isfinite(matrix).all():
        return None, None
    projected = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    residual = np.linalg.norm(projected - observed, axis=1)
    mask = (np.isfinite(residual) & (residual <= _RANSAC_THRESHOLD)).astype(np.uint8)
    return cast(NDArray[np.float64], matrix), mask.reshape(-1, 1)


def _evaluate_origin(
    matrix: NDArray[np.float64],
    *,
    values: tuple[tuple[int, int, GlobalSymbolCandidate], ...],
    selected: tuple[int, ...],
    offset: int,
    candidates: tuple[GlobalSymbolCandidate, ...],
    analysis_to_source: NDArray[np.float64],
    source_shape: tuple[int, ...],
    p95: float,
    policy: LateralPartialGeometrySnapshot,
    source_checksum_sha256: str,
    position_index: int,
) -> tuple[LateralLatticeProposal | None, str | None]:
    corners = np.asarray([(0.0, 0.0), (500.0, 0.0), (500.0, 300.0), (0.0, 300.0)])
    denominator = np.column_stack([corners, np.ones(4)]) @ matrix[2]
    if not (np.all(denominator > 1e-9) or np.all(denominator < -1e-9)):
        return None, "lateral_homography_invalid"
    analysis_corners = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    # Registration is an index anchor, not a fallback lattice. More than half
    # a cell of uncertainty cannot distinguish column origins safely.
    if (
        not np.isfinite(analysis_corners).all()
        or np.max(np.abs(analysis_corners - corners)) > _MAX_ORIGIN_SHIFT_PX
    ):
        return None, "lateral_index_origin_unconfirmed"
    area_ratio = abs(float(cv2.contourArea(analysis_corners.astype(np.float32)))) / (
        _WIDTH * _HEIGHT
    )
    if not 0.55 <= area_ratio <= 1.15:
        return None, "lateral_grid_area_invalid"
    source_corners = cv2.perspectiveTransform(
        corners.reshape(-1, 1, 2), analysis_to_source @ matrix
    ).reshape(-1, 2)
    try:
        quad = SourceQuad(
            corners=cast(
                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                tuple(SourcePoint(float(x), float(y)) for x, y in source_corners),
            )
        )
        quad.require_manual_edit_bounds(
            SourceImageBounds(width=source_shape[1], height=source_shape[0])
        )
    except ImageGeometryContractError:
        return None, "lateral_source_geometry_invalid"
    if _vertical_clip(quad, source_shape[0]):
        return None, "source_vertical_crop_defect"
    missing = unavailable_source_cell_indices(
        quad,
        source=SourceImageBounds(width=source_shape[1], height=source_shape[0]),
        topology=LEGACY_IMAGE_BOARD_TOPOLOGY,
    )
    if not missing or len(missing) == 15:
        return None, "lateral_source_support_required"
    assigned: list[int | None] = [None] * 15
    for row, column, candidate in values:
        assigned[row * 5 + column + offset] = candidate.candidate_index
    slots = tuple((values[index][0], values[index][1] + offset) for index in selected)
    ideal_centres = np.asarray(
        [((column + 0.5) * 100, (row + 0.5) * 100) for row in range(3) for column in range(5)],
        dtype=np.float64,
    )
    observed_centres = cv2.perspectiveTransform(ideal_centres.reshape(-1, 1, 2), matrix).reshape(
        3, 5, 2
    )
    column_bases = tuple(float(np.median(observed_centres[:, index, 0])) for index in range(5))
    row_bases = tuple(float(np.median(observed_centres[index, :, 1])) for index in range(3))
    if any(
        not 45 <= right - left <= 135
        for left, right in zip(column_bases[:-1], column_bases[1:], strict=True)
    ) or any(
        not 45 <= bottom - top <= 145
        for top, bottom in zip(row_bases[:-1], row_bases[1:], strict=True)
    ):
        return None, "lateral_grid_spacing_invalid"
    # The same bbox protection as v3, with no synthetic assigned centres.
    estimate = BoardCellGeometryEstimate(
        status="estimated",
        lattice_bounds_quad=None,
        cells=(),
        evidence=None,
        candidate_center_count=len(candidates),
        assigned_candidate_count=len(values),
        reliable_center_count=len(selected),
        inlier_slots=slots,
        inlier_p95_residual_px=p95,
        fallback_reason=None,
        rectified_candidates=candidates,
        assigned_candidate_indices=tuple(assigned),
        global_column_bases=column_bases,
        global_row_bases=row_bases,
        ideal_to_observed_matrix=cast(
            tuple[
                tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
            ],
            tuple(tuple(float(value) for value in row) for row in matrix),
        ),
    )
    safety = evaluate_lattice_content_safety(estimate)
    if safety.status != "passed" or safety.protected_candidate_count < _MIN_INLIERS:
        return None, safety.reason_code or "insufficient_protected_lateral_content"
    return LateralLatticeProposal(
        quad,
        GeometryQualification("pending_partial", missing, True, "missing_pixels"),
        source_checksum_sha256,
        position_index,
        policy.checksum_sha256,
        slots,
        p95,
        offset,
        safety,
    ), None


def _vertical_clip(quad: SourceQuad, height: int) -> bool:
    return any(point.y < -1e-6 or point.y > height - 1 + 1e-6 for point in quad.corners)
