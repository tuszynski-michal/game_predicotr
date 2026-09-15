"""Opt-in lateral partial proposals, after the unchanged complete v3 path."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Literal, cast

import cv2
import numpy as np
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.geometry_qualification import (
    GEOMETRY_QUALIFICATION_VERSION,
    GEOMETRY_QUALIFICATION_VERSION_V1,
    GeometryQualification,
)
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
    AUTOMATIC_FRAME_PROPOSAL_VERSION,
    AUTOMATIC_PARTIAL_PROPOSAL_VERSION,
    AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V2,
    AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V3,
    LATERAL_PARTIAL_POLICY_VERSION,
    LATERAL_PARTIAL_POLICY_VERSION_V2,
    LATERAL_PARTIAL_POLICY_VERSION_V3,
    LateralPartialGeometrySnapshot,
)
from ..page_geometry_registration import LateralPageRegistrationCandidate
from ..partial_grid_learning import PartialGridTrainingProfile
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
    policy_version: str = LATERAL_PARTIAL_POLICY_VERSION
    proposal_version: str = AUTOMATIC_PARTIAL_PROPOSAL_VERSION
    training_profile_checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        modern = self.policy_version == LATERAL_PARTIAL_POLICY_VERSION_V3
        learned = self.training_profile_checksum_sha256 is not None
        expected_proposal_version = (
            AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V3
            if modern
            else (
                AUTOMATIC_PARTIAL_PROPOSAL_VERSION_V2
                if learned
                else AUTOMATIC_PARTIAL_PROPOSAL_VERSION
            )
        )
        expected_qualification_version = (
            GEOMETRY_QUALIFICATION_VERSION
            if modern or learned
            else GEOMETRY_QUALIFICATION_VERSION_V1
        )
        if (
            self.qualification.completeness_status != "pending_partial"
            or not self.qualification.exclude_from_geometry_training
            or self.policy_version
            not in {
                LATERAL_PARTIAL_POLICY_VERSION,
                LATERAL_PARTIAL_POLICY_VERSION_V2,
                LATERAL_PARTIAL_POLICY_VERSION_V3,
            }
            or self.proposal_version != expected_proposal_version
            or self.qualification.version != expected_qualification_version
            or (
                self.policy_version == LATERAL_PARTIAL_POLICY_VERSION_V2
                and not learned
            )
            or (
                self.policy_version == LATERAL_PARTIAL_POLICY_VERSION
                and learned
            )
            or len(self.policy_checksum_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.policy_checksum_sha256)
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
            or (
                self.training_profile_checksum_sha256 is not None
                and (
                    len(self.training_profile_checksum_sha256) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in self.training_profile_checksum_sha256
                    )
                )
            )
        ):
            raise ValueError("An automatic lateral proposal requires complete guarded evidence.")

    def metadata_payload(self) -> dict[str, object]:
        """The automatic provenance contract is separate from manual decisions."""
        payload: dict[str, object] = {
            "version": self.proposal_version,
            "origin": "automatic_proposal",
            "sourceChecksumSha256": self.source_checksum_sha256,
            "positionIndex": self.position_index + 1,
            "policyVersion": self.policy_version,
            "policyChecksumSha256": self.policy_checksum_sha256,
            "requiresManualConfirmation": True,
            "geometryQualification": self.qualification.to_dict(),
        }
        if self.training_profile_checksum_sha256 is not None:
            payload["trainingProfileChecksumSha256"] = self.training_profile_checksum_sha256
        return payload


@dataclass(frozen=True, slots=True)
class FrameLatticeProposal:
    symbol_grid_quad: SourceQuad
    qualification: GeometryQualification
    source_checksum_sha256: str
    position_index: int
    policy_checksum_sha256: str
    inlier_slots: tuple[tuple[int, int], ...]
    p95_residual_px: float
    content_safety: LatticeContentSafetyResult
    policy_version: str = LATERAL_PARTIAL_POLICY_VERSION_V3
    proposal_version: str = AUTOMATIC_FRAME_PROPOSAL_VERSION
    training_profile_checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            self.policy_version != LATERAL_PARTIAL_POLICY_VERSION_V3
            or self.proposal_version != AUTOMATIC_FRAME_PROPOSAL_VERSION
            or self.qualification.completeness_status != "complete"
            or self.qualification.unavailable_cell_indices
            or not self.qualification.exclude_from_geometry_training
            or self.qualification.exclusion_reason != "manual_exclusion"
            or self.qualification.version != GEOMETRY_QUALIFICATION_VERSION
            or self.content_safety.status != "passed"
            or len(set(self.inlier_slots)) < _MIN_INLIERS
            or {row for row, _ in self.inlier_slots} != {0, 1, 2}
            or {column for _, column in self.inlier_slots} != {0, 1, 2, 3, 4}
            or not 0 <= self.p95_residual_px <= _MAX_P95_RESIDUAL
            or len(self.policy_checksum_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.policy_checksum_sha256
            )
            or type(self.position_index) is not int
            or not 0 <= self.position_index < 9
            or len(self.source_checksum_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.source_checksum_sha256
            )
        ):
            raise ValueError("An automatic frame proposal requires complete guarded evidence.")

    def metadata_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "version": self.proposal_version,
            "origin": "automatic_proposal",
            "sourceChecksumSha256": self.source_checksum_sha256,
            "positionIndex": self.position_index + 1,
            "policyVersion": self.policy_version,
            "policyChecksumSha256": self.policy_checksum_sha256,
            "requiresManualConfirmation": True,
            "reasonCode": "board_frame_support_incomplete",
            "geometryQualification": self.qualification.to_dict(),
        }
        if self.training_profile_checksum_sha256 is not None:
            payload["trainingProfileChecksumSha256"] = self.training_profile_checksum_sha256
        return payload


@dataclass(frozen=True, slots=True)
class StructuredLatticeRefinementV4:
    status: Literal[
        "full", "pending_partial", "pending_review", "needs_review", "source_preparation_error"
    ]
    baseline: StructuredLatticeRefinementV3
    proposal: LateralLatticeProposal | None = None
    frame_proposal: FrameLatticeProposal | None = None
    reason_code: str | None = None
    additional_passes: int = 0
    hypothesis_count: int = 0
    policy_version: str = LATERAL_PARTIAL_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.status == "full" and self.baseline.status != "estimated":
            raise ValueError("A complete v4 result must retain the accepted v3 baseline.")
        if (self.status == "pending_partial") != (self.proposal is not None):
            raise ValueError("Only an unconfirmed partial result can expose a lateral proposal.")
        if (self.status == "pending_review") != (self.frame_proposal is not None):
            raise ValueError("Only a frame-review result can expose a complete proposal.")
        if self.additional_passes not in (0, 1) or not 0 <= self.hypothesis_count <= 3:
            raise ValueError("The bounded lateral analysis budget was exceeded.")

    def to_payload(self) -> dict[str, object]:
        if self.status == "full":
            # Full boards retain the exact serialized v3 semantics as well.
            return self.baseline.to_payload()
        return {
            "localLatticeVersion": self.policy_version,
            "localLatticeStatus": self.status,
            "analysisQuad": self.baseline.analysis_quad.to_dict(),
            "symbolGridQuad": (
                self.proposal.symbol_grid_quad.to_dict()
                if self.proposal is not None
                else (
                    self.frame_proposal.symbol_grid_quad.to_dict()
                    if self.frame_proposal is not None
                    else None
                )
            ),
            "automaticPartialProposal": None
            if self.proposal is None
            else self.proposal.metadata_payload(),
            "automaticFrameProposal": None
            if self.frame_proposal is None
            else self.frame_proposal.metadata_payload(),
            "reasonCode": self.reason_code,
            "additionalPasses": self.additional_passes,
            "hypothesisCount": self.hypothesis_count,
            "excludeFromPageAnchors": self.proposal is not None or self.frame_proposal is not None,
            "baseline": self.baseline.to_payload(),
            "inlierSlots": (
                [list(slot) for slot in self.proposal.inlier_slots]
                if self.proposal is not None
                else (
                    [list(slot) for slot in self.frame_proposal.inlier_slots]
                    if self.frame_proposal is not None
                    else []
                )
            ),
            "p95ResidualPx": (
                self.proposal.p95_residual_px
                if self.proposal is not None
                else (
                    self.frame_proposal.p95_residual_px
                    if self.frame_proposal is not None
                    else None
                )
            ),
            "columnOffset": None if self.proposal is None else self.proposal.column_offset,
            "contentSafety": (
                self.proposal.content_safety.to_payload()
                if self.proposal is not None
                else (
                    self.frame_proposal.content_safety.to_payload()
                    if self.frame_proposal is not None
                    else None
                )
            ),
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
    height, width = source_rgb.shape[:2]
    if lateral_candidate is not None:
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
            raise ValueError(
                "Lateral analysis quad differs from the attested registration proposal."
            )
    frame_review = (
        lateral_candidate is not None
        and lateral_candidate.recovery_kind == "frame_support_review"
        and position_index in lateral_candidate.review_required_slots
    )
    if baseline.status == "estimated":
        if not frame_review:
            return StructuredLatticeRefinementV4("full", baseline)
        assert baseline.symbol_grid_quad is not None
        return StructuredLatticeRefinementV4(
            "pending_review",
            baseline,
            frame_proposal=FrameLatticeProposal(
                baseline.symbol_grid_quad,
                GeometryQualification(
                    "complete",
                    (),
                    True,
                    "manual_exclusion",
                    False,
                    GEOMETRY_QUALIFICATION_VERSION,
                ),
                source_checksum_sha256,
                position_index,
                policy.checksum_sha256,
                baseline.estimate.inlier_slots,
                cast(float, baseline.estimate.inlier_p95_residual_px),
                baseline.content_safety,
                training_profile_checksum_sha256=(
                    None
                    if policy.training_profile is None
                    else policy.training_profile.checksum_sha256
                ),
            ),
            reason_code="board_frame_support_incomplete",
            policy_version=policy.policy_version,
        )
    if _vertical_clip(analysis_quad, height):
        return StructuredLatticeRefinementV4(
            "source_preparation_error",
            baseline,
            reason_code="source_vertical_crop_defect",
            policy_version=policy.policy_version,
        )
    if lateral_candidate is None:
        return StructuredLatticeRefinementV4(
            "needs_review",
            baseline,
            reason_code="lateral_registration_unavailable",
            policy_version=policy.policy_version,
        )
    is_frame_recovery = lateral_candidate.recovery_kind == "frame_support_review"
    if not is_frame_recovery and not any(
        point.x < 0 or point.x > width - 1 for point in analysis_quad.corners
    ):
        return StructuredLatticeRefinementV4(
            "needs_review",
            baseline,
            reason_code="lateral_source_support_required",
            policy_version=policy.policy_version,
        )
    if is_frame_recovery and frame_review:
        frame_proposals, frame_reason, frame_hypotheses = _fit_frame_lattice(
            source_rgb,
            analysis_quad=analysis_quad,
            source_checksum_sha256=source_checksum_sha256,
            position_index=position_index,
            policy=policy,
        )
        if len(frame_proposals) == 1:
            return StructuredLatticeRefinementV4(
                "pending_review",
                baseline,
                frame_proposal=frame_proposals[0],
                reason_code="board_frame_support_incomplete",
                additional_passes=1,
                hypothesis_count=frame_hypotheses,
                policy_version=policy.policy_version,
            )
        return StructuredLatticeRefinementV4(
            "needs_review",
            baseline,
            reason_code=(
                "ambiguous_frame_lattice"
                if len(frame_proposals) > 1
                else frame_reason
            ),
            additional_passes=1,
            hypothesis_count=frame_hypotheses,
            policy_version=policy.policy_version,
        )
    proposals, reason, hypotheses = _fit_lateral_lattice(
        source_rgb,
        analysis_quad=analysis_quad,
        source_checksum_sha256=source_checksum_sha256,
        position_index=position_index,
        policy=policy,
    )
    if len(proposals) > 1 and policy.training_profile is not None:
        proposals = _select_learned_proposals(proposals, policy.training_profile)
    if len(proposals) == 1:
        return StructuredLatticeRefinementV4(
            "pending_partial",
            baseline,
            proposal=proposals[0],
            additional_passes=1,
            hypothesis_count=hypotheses,
            policy_version=policy.policy_version,
        )
    if len(proposals) > 1:
        return StructuredLatticeRefinementV4(
            "needs_review",
            baseline,
            reason_code="ambiguous_column_indices",
            additional_passes=1,
            hypothesis_count=hypotheses,
            policy_version=policy.policy_version,
        )
    return StructuredLatticeRefinementV4(
        "source_preparation_error"
        if reason == "source_vertical_crop_defect"
        else "needs_review",
        baseline,
        reason_code=reason,
        additional_passes=1,
        hypothesis_count=hypotheses,
        policy_version=policy.policy_version,
    )


def _select_learned_proposals(
    proposals: list[LateralLatticeProposal],
    profile: PartialGridTrainingProfile,
) -> list[LateralLatticeProposal]:
    selected_mask = profile.select_mask(
        tuple(proposal.qualification.unavailable_cell_indices for proposal in proposals)
    )
    if selected_mask is None:
        return proposals
    selected = [
        proposal
        for proposal in proposals
        if proposal.qualification.unavailable_cell_indices == selected_mask
    ]
    return selected if len(selected) == 1 else proposals


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
        if isinstance(proposal, LateralLatticeProposal):
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


def _fit_frame_lattice(
    source_rgb: NDArray[np.uint8],
    *,
    analysis_quad: SourceQuad,
    source_checksum_sha256: str,
    position_index: int,
    policy: LateralPartialGeometrySnapshot,
) -> tuple[list[FrameLatticeProposal], str, int]:
    """Recover one complete grid when page registration already fixes its slot.

    The fit intentionally reuses the bounded lateral detector.  Unlike a
    lateral partial, a frame recovery requires evidence in all five columns,
    so there is only one admissible column origin and no best-score choice.
    """

    analysis, support, analysis_to_source = _supported_analysis(source_rgb, analysis_quad)
    candidates = _supported_candidates(analysis, support)
    assignments = _visible_assignments(candidates) if len(candidates) >= _MIN_INLIERS else None
    if assignments is None:
        return [], "insufficient_frame_lattice_evidence", 0
    values, count = assignments
    if count != 5:
        return [], "frame_lattice_columns_incomplete", 1
    ideal = np.asarray(
        [((column + 0.5) * 100, (row + 0.5) * 100) for row, column, _ in values],
        dtype=np.float64,
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
        return [], "frame_lattice_homography_invalid", 1
    selected = tuple(index for index, keep in enumerate(inlier_mask.reshape(-1)) if keep)
    if (
        len(selected) < _MIN_INLIERS
        or {values[index][0] for index in selected} != {0, 1, 2}
        or {values[index][1] for index in selected} != {0, 1, 2, 3, 4}
    ):
        return [], "insufficient_frame_lattice_inliers", 1
    projected = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    p95 = float(
        np.percentile(
            np.linalg.norm(projected[list(selected)] - observed[list(selected)], axis=1), 95
        )
    )
    if not np.isfinite(p95) or p95 > _MAX_P95_RESIDUAL:
        return [], "frame_lattice_residual_excessive", 1
    proposal, reason = _evaluate_origin(
        matrix,
        values=values,
        selected=selected,
        offset=0,
        candidates=candidates,
        analysis_to_source=analysis_to_source,
        source_shape=source_rgb.shape,
        p95=p95,
        policy=policy,
        source_checksum_sha256=source_checksum_sha256,
        position_index=position_index,
        complete_frame_review=True,
    )
    return (
        [proposal] if isinstance(proposal, FrameLatticeProposal) else [],
        reason or "frame_symbol_grid_unavailable",
        1,
    )


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
    complete_frame_review: bool = False,
) -> tuple[LateralLatticeProposal | FrameLatticeProposal | None, str | None]:
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
    if len(missing) == 15:
        return None, "lateral_source_support_required"
    if complete_frame_review and missing:
        return None, "frame_lattice_source_support_incomplete"
    if not complete_frame_review and not missing:
        return None, "lateral_source_support_required"
    if not complete_frame_review:
        missing_by_row = tuple(
            tuple(column for column in range(5) if row * 5 + column in missing) for row in range(3)
        )
        available_columns = tuple(column for column in range(5) if column not in missing_by_row[0])
        if (
            len(set(missing_by_row)) != 1
            or len(available_columns) < 3
            or available_columns != tuple(range(available_columns[0], available_columns[-1] + 1))
        ):
            return None, "lateral_unavailable_mask_inconsistent"
    assigned: list[int | None] = [None] * 15
    for row, column, candidate in values:
        assigned[row * 5 + column + offset] = candidate.candidate_index
    slots = tuple((values[index][0], values[index][1] + offset) for index in selected)
    if any(row * 5 + column in missing for row, column in slots):
        return None, "lateral_inlier_source_support_inconsistent"
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
    if complete_frame_review:
        return FrameLatticeProposal(
            quad,
            GeometryQualification(
                "complete",
                (),
                True,
                "manual_exclusion",
                False,
                GEOMETRY_QUALIFICATION_VERSION,
            ),
            source_checksum_sha256,
            position_index,
            policy.checksum_sha256,
            slots,
            p95,
            safety,
            training_profile_checksum_sha256=(
                None
                if policy.training_profile is None
                else policy.training_profile.checksum_sha256
            ),
        ), None
    return LateralLatticeProposal(
        quad,
        GeometryQualification(
            "pending_partial",
            missing,
            True,
            "missing_pixels",
            False,
            (
                GEOMETRY_QUALIFICATION_VERSION
                if policy.training_profile is not None or policy.frame_support_review
                else GEOMETRY_QUALIFICATION_VERSION_V1
            ),
        ),
        source_checksum_sha256,
        position_index,
        policy.checksum_sha256,
        slots,
        p95,
        offset,
        safety,
        policy.policy_version,
        policy.proposal_version,
        None if policy.training_profile is None else policy.training_profile.checksum_sha256,
    ), None


def _vertical_clip(quad: SourceQuad, height: int) -> bool:
    return any(point.y < -1e-6 or point.y > height - 1 + 1e-6 for point in quad.corners)
