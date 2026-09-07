"""Consume explicit human slot geometry without re-running an image detector."""

from collections.abc import Mapping, Sequence
from typing import cast

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import parse_slot_qualifications
from game_predictor_api.domain.image_geometry_v2 import (
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
    resolve_manual_geometry_qualification,
)

from .geometry import Point, Quad
from .page_geometry_registration import is_ordered_active_grid
from .pipeline_execution import ImagePipelineExecutionError


def apply_qualified_page_override(
    base: Mapping[str, object],
    entry: Mapping[str, object],
    *,
    width: int,
    height: int,
    start: int,
    count: int,
    topology: BoardTopology,
) -> dict[str, object]:
    """The base is a metadata-only manual template, never a detector fallback."""
    import hashlib

    qualifications = parse_slot_qualifications(
        entry.get("slotQualifications"), expected_board_count=count
    )
    raw_quads = entry.get("quads")
    if (
        qualifications is None
        or entry.get("status") != "registered"
        or entry.get("registrationVersion") != "manual-page-geometry-override-v1"
        or not isinstance(raw_quads, Sequence)
        or isinstance(raw_quads, str | bytes)
        or len(raw_quads) != count
    ):
        raise ImagePipelineExecutionError(
            "IMAGE_PAGE_GEOMETRY_INVALID", "Qualified manual page evidence is incomplete."
        )
    boards: list[dict[str, object]] = []
    ordered_quads: list[Quad] = []
    for position, (raw, qualification) in enumerate(zip(raw_quads, qualifications, strict=True)):
        if (
            not isinstance(raw, Sequence)
            or isinstance(raw, str | bytes)
            or len(raw) != 4
            or any(
                not isinstance(point, Mapping)
                or set(point) != {"x", "y"}
                or type(point["x"]) is not int
                or type(point["y"]) is not int
                for point in raw
            )
        ):
            raise ImagePipelineExecutionError(
                "IMAGE_PAGE_GEOMETRY_INVALID", "A qualified slot must have four integer corners."
            )
        points = cast(Sequence[Mapping[str, int]], raw)
        quad = SourceQuad(
            cast(
                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                tuple(SourcePoint(p["x"], p["y"]) for p in points),
            )
        )
        resolved = resolve_manual_geometry_qualification(
            quad,
            source=SourceImageBounds(width, height),
            topology=topology,
            qualification=qualification,
        )
        if resolved != qualification:
            raise ImagePipelineExecutionError(
                "IMAGE_GEOMETRY_UNAVAILABLE_MASK_INCOMPLETE",
                "The pinned human mask does not cover source-external cells.",
            )
        ordered_quads.append(
            cast(Quad, tuple(Point(p["x"] + width, p["y"] + height) for p in points))
        )
        boards.append(
            {
                "positionIndex": position,
                "sequenceNumber": start + position,
                "finalQuad": quad.to_dict(),
                "symbolGridQuad": quad.to_dict(),
                "analysisQuad": quad.to_dict(),
                "boardFrameQuad": None,
                "geometryConfidence": 1.0,
                "disposition": "automatic",
                "reasonCodes": [],
                "localLatticeStatus": "human_reviewed",
                "localLatticeVersion": "manual-geometry-qualification-v1",
                "guardResolutionDisposition": "partial"
                if qualification.completeness_status == "pending_partial"
                else "corrected_full",
                "geometryQualification": qualification.to_dict(),
                "completenessStatus": qualification.completeness_status,
                "unavailableCellIndices": list(qualification.unavailable_cell_indices),
            }
        )
    if not is_ordered_active_grid(
        tuple(ordered_quads), tuple(range(count)), width * 3 + 1, height * 3 + 1
    ):
        raise ImagePipelineExecutionError(
            "IMAGE_PAGE_GEOMETRY_INVALID", "Qualified slots overlap or violate row-major order."
        )
    payload = dict(base)
    payload.update(
        {
            "boards": boards,
            "reasonCodes": [],
            "status": "ready",
            "geometrySource": "manual",
            "manualOverrideDecisionChecksumSha256": entry.get(
                "manualOverrideDecisionChecksumSha256"
            ),
            "qualificationPolicy": "manual-geometry-qualification-v1",
        }
    )
    payload.pop("resultChecksumSha256", None)
    payload["resultChecksumSha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return payload
