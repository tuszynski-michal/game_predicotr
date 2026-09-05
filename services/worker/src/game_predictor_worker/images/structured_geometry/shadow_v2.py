"""Measurement-only Structured Geometry v2 sidecar for shadow jobs."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Final
from uuid import UUID

import cv2
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import SourceQuad, canonical_json_bytes

from ..normalization import CanonicalSourceFrame
from .configuration_v2 import (
    GeometryCandidateDecisionV2,
    StructuredGeometryConfigV2,
    StructuredGeometryEvidenceV2,
    evaluate_geometry_candidate_v2,
)
from .geometry_engine import BoardGeometryResult, SourceGeometryResult
from .global_initialization import GlobalInitializationMethod
from .signal_probe import StructuredGeometrySignalProbe, probe_board_signals

STRUCTURED_GEOMETRY_SHADOW_V2_VERSION: Final = "structured-geometry-v2-shadow-measurement-v1"


@dataclass(frozen=True, slots=True)
class StructuredGeometryShadowBoardV2:
    position_index: int
    sequence_number: int
    upstream_disposition: str
    evaluation_status: str
    decision: GeometryCandidateDecisionV2 | None
    evidence: StructuredGeometryEvidenceV2 | None
    signal_probe: StructuredGeometrySignalProbe | None
    reason_codes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "candidateDecision": None if self.decision is None else self.decision.to_payload(),
            "evaluationStatus": self.evaluation_status,
            "evidence": None if self.evidence is None else self.evidence.to_payload(),
            "positionIndex": self.position_index,
            "reasonCodes": list(self.reason_codes),
            "sequenceNumber": self.sequence_number,
            "signalProbe": None if self.signal_probe is None else self.signal_probe.to_payload(),
            "upstreamDisposition": self.upstream_disposition,
        }


@dataclass(frozen=True, slots=True)
class StructuredGeometryShadowResultV2:
    config: StructuredGeometryConfigV2
    source_checksum_sha256: str
    normalized_pixel_checksum_sha256: str
    upstream_result_checksum_sha256: str
    upstream_engine_version: str
    analysis_scale: float | None
    boards: tuple[StructuredGeometryShadowBoardV2, ...]
    schema_version: int = 1

    @property
    def result_checksum_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self._payload())).hexdigest()

    def to_payload(self) -> dict[str, object]:
        payload = self._payload()
        payload["resultChecksumSha256"] = self.result_checksum_sha256
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "activationAllowed": False,
            "adaptiveAnalysisAppliedToSignalProbe": self.analysis_scale is not None,
            "analysisScale": self.analysis_scale,
            "boards": [board.to_payload() for board in self.boards],
            "candidateRole": "measurement_only",
            "candidateVersion": STRUCTURED_GEOMETRY_SHADOW_V2_VERSION,
            "configChecksumSha256": self.config.checksum_sha256,
            "configVersion": self.config.to_payload()["configVersion"],
            "geometryOriginEngineVersion": self.upstream_engine_version,
            "geometryOriginPolicy": "reuse_v1_final_quad_without_authority",
            "normalizedPixelChecksumSha256": self.normalized_pixel_checksum_sha256,
            "schemaVersion": self.schema_version,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "upstreamResultChecksumSha256": self.upstream_result_checksum_sha256,
        }


def evaluate_structured_geometry_shadow_v2(
    frame: CanonicalSourceFrame,
    upstream: SourceGeometryResult,
    *,
    config: StructuredGeometryConfigV2,
    game_id: UUID | None,
) -> StructuredGeometryShadowResultV2:
    """Evaluate v2 beside v1; the returned value has no production authority."""

    if (
        frame.source.source_checksum_sha256 != upstream.source_checksum_sha256
        or frame.source.normalized_pixel_checksum_sha256
        != upstream.normalized_pixel_checksum_sha256
        or frame.source.width != upstream.canonical_width
        or frame.source.height != upstream.canonical_height
    ):
        raise ValueError("The shadow candidate source differs from the upstream geometry result.")
    topology = BoardTopology(rows=upstream.topology_rows, columns=upstream.topology_columns)
    final_quads = tuple(
        board.final_quad for board in upstream.boards if board.final_quad is not None
    )
    analysis_scale = (
        None
        if not final_quads
        else config.analysis.resolve_scale(
            source_width=upstream.canonical_width,
            source_height=upstream.canonical_height,
            smallest_roi_short_edge_px=min(_quad_short_edge(quad) for quad in final_quads),
        )
    )
    known_layout_available = (
        upstream.global_initialization.method
        is GlobalInitializationMethod.VERIFIED_PROFILE_ORB_RANSAC
    )
    boards = tuple(
        _evaluate_board(
            frame,
            board,
            topology=topology,
            config=config,
            game_id=game_id,
            analysis_scale=analysis_scale,
            known_layout_available=known_layout_available,
        )
        for board in upstream.boards
    )
    return StructuredGeometryShadowResultV2(
        config=config,
        source_checksum_sha256=upstream.source_checksum_sha256,
        normalized_pixel_checksum_sha256=upstream.normalized_pixel_checksum_sha256,
        upstream_result_checksum_sha256=upstream.result_checksum_sha256,
        upstream_engine_version=upstream.engine_version,
        analysis_scale=analysis_scale,
        boards=boards,
    )


def _evaluate_board(
    frame: CanonicalSourceFrame,
    board: BoardGeometryResult,
    *,
    topology: BoardTopology,
    config: StructuredGeometryConfigV2,
    game_id: UUID | None,
    analysis_scale: float | None,
    known_layout_available: bool,
) -> StructuredGeometryShadowBoardV2:
    if board.final_quad is None or analysis_scale is None:
        return StructuredGeometryShadowBoardV2(
            position_index=board.slot.position_index,
            sequence_number=board.slot.sequence_number,
            upstream_disposition=board.disposition.value,
            evaluation_status="not_evaluated",
            decision=None,
            evidence=None,
            signal_probe=None,
            reason_codes=("final_quad_unavailable",),
        )
    try:
        probe = probe_board_signals(
            frame.rgb,
            board.final_quad,
            topology=topology,
            analysis_scale=analysis_scale,
            coordinate_source="structured_v1_final_quad",
        )
    except (cv2.error, ValueError):
        return StructuredGeometryShadowBoardV2(
            position_index=board.slot.position_index,
            sequence_number=board.slot.sequence_number,
            upstream_disposition=board.disposition.value,
            evaluation_status="not_evaluated",
            decision=None,
            evidence=None,
            signal_probe=None,
            reason_codes=("signal_probe_failed",),
        )
    evidence = StructuredGeometryEvidenceV2(
        homography_available=board.evidence.homography_available,
        padded_cell_source_support_complete=(board.evidence.padded_cell_source_support_complete),
        initialization_alignment_valid=board.evidence.initialization_alignment_valid,
        slot_order_valid=board.evidence.slot_order_valid,
        overlap_valid=board.evidence.overlap_valid,
        outer_frame_score=probe.outer_border_score,
        known_layout_score=(
            board.confidence_components.global_registration_score if known_layout_available else 0.0
        ),
        lsd_grid_score=probe.lsd_coverage_score,
        hough_grid_score=probe.hough_coverage_score,
        vertical_gradient_profile_score=probe.vertical_gradient_profile_score,
        horizontal_gradient_profile_score=probe.horizontal_gradient_profile_score,
        grid_regularity_score=probe.grid_periodicity_score,
        symbol_center_support_score=probe.symbol_center_support_score,
        reprojection_cell_diagonal_fraction=_normalized_reprojection(board, topology=topology),
    )
    decision = evaluate_geometry_candidate_v2(evidence, config=config, game_id=game_id)
    reasons = () if known_layout_available else ("known_layout_evidence_unavailable",)
    return StructuredGeometryShadowBoardV2(
        position_index=board.slot.position_index,
        sequence_number=board.slot.sequence_number,
        upstream_disposition=board.disposition.value,
        evaluation_status="evaluated",
        decision=decision,
        evidence=evidence,
        signal_probe=probe,
        reason_codes=reasons,
    )


def _normalized_reprojection(
    board: BoardGeometryResult,
    *,
    topology: BoardTopology,
) -> float | None:
    p95 = board.evidence.half_scale_p95_reprojection_error
    quad = board.final_quad
    if p95 is None or quad is None:
        return None
    top, right, bottom, left = _quad_edges(quad)
    cell_width = ((top + bottom) / 2) * 0.5 / topology.columns
    cell_height = ((left + right) / 2) * 0.5 / topology.rows
    diagonal = math.hypot(cell_width, cell_height)
    return None if diagonal <= 0 else round(p95 / diagonal, 8)


def _quad_short_edge(quad: SourceQuad) -> float:
    return min(_quad_edges(quad))


def _quad_edges(quad: SourceQuad) -> tuple[float, float, float, float]:
    points = quad.corners
    return (
        math.hypot(points[1].x - points[0].x, points[1].y - points[0].y),
        math.hypot(points[2].x - points[1].x, points[2].y - points[1].y),
        math.hypot(points[3].x - points[2].x, points[3].y - points[2].y),
        math.hypot(points[0].x - points[3].x, points[0].y - points[3].y),
    )


__all__ = [
    "STRUCTURED_GEOMETRY_SHADOW_V2_VERSION",
    "StructuredGeometryShadowBoardV2",
    "StructuredGeometryShadowResultV2",
    "evaluate_structured_geometry_shadow_v2",
]
