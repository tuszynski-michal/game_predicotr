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


def apply_v12_page_geometry(
    base: Mapping[str, object],
    entry: Mapping[str, object],
    *,
    width: int,
    height: int,
    start: int,
    count: int,
    topology: BoardTopology,
) -> dict[str, object]:
    """Use the pinned inner grid for cells; the outer frame is evidence only."""
    import hashlib

    from game_predictor_api.domain.geometry_qualification import GeometryQualification
    from game_predictor_api.domain.image_geometry_v2 import ImageGeometryContractError

    from .contrast_frame_grid_v12 import CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION

    frames = entry.get("boardFrameQuads")
    grids = entry.get("symbolGridQuads")
    if (
        entry.get("status") != "registered"
        or entry.get("registrationVersion") != CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION
        or entry.get("imageWidth") != width
        or entry.get("imageHeight") != height
        or not isinstance(frames, Sequence)
        or isinstance(frames, str | bytes)
        or not isinstance(grids, Sequence)
        or isinstance(grids, str | bytes)
        or len(frames) != count
        or len(grids) != count
        or entry.get("quads") != frames
    ):
        raise ImagePipelineExecutionError(
            "IMAGE_PAGE_GEOMETRY_INVALID", "The V1.2 frame/grid pair is incomplete."
        )

    def parse(raw: object) -> SourceQuad:
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
                "IMAGE_PAGE_GEOMETRY_INVALID", "V1.2 corners must be integer source points."
            )
        points = cast(Sequence[Mapping[str, int]], raw)
        try:
            return SourceQuad(
                cast(
                    tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                    tuple(SourcePoint(point["x"], point["y"]) for point in points),
                )
            )
        except ImageGeometryContractError as error:
            raise ImagePipelineExecutionError("IMAGE_PAGE_GEOMETRY_INVALID", str(error)) from error

    parsed_frames = tuple(parse(raw) for raw in frames)
    parsed_grids = tuple(parse(raw) for raw in grids)
    source = SourceImageBounds(width, height)
    for frame, grid in zip(parsed_frames, parsed_grids, strict=True):
        try:
            frame.require_manual_edit_bounds(source)
            grid.require_manual_edit_bounds(source)
        except ImageGeometryContractError as error:
            raise ImagePipelineExecutionError("IMAGE_PAGE_GEOMETRY_INVALID", str(error)) from error
        for point in grid.corners:
            cross = tuple(
                (end.x - begin.x) * (point.y - begin.y) - (end.y - begin.y) * (point.x - begin.x)
                for begin, end in zip(
                    frame.corners, frame.corners[1:] + frame.corners[:1], strict=True
                )
            )
            if not (
                all(value >= -1e-6 for value in cross) or all(value <= 1e-6 for value in cross)
            ):
                raise ImagePipelineExecutionError(
                    "IMAGE_PAGE_GEOMETRY_INVALID", "A V1.2 symbol grid escapes its board frame."
                )
    shifted = tuple(
        cast(Quad, tuple(Point(point.x + width, point.y + height) for point in quad.corners))
        for quad in parsed_frames
    )
    if not is_ordered_active_grid(shifted, tuple(range(count)), width * 3 + 1, height * 3 + 1):
        raise ImagePipelineExecutionError(
            "IMAGE_PAGE_GEOMETRY_INVALID", "V1.2 board frames overlap or are out of order."
        )
    qualifications = entry.get("slotQualifications")
    qualified = apply_qualified_page_override(
        base,
        {
            "status": "registered",
            "registrationVersion": "manual-page-geometry-override-v1",
            "quads": grids,
            "slotQualifications": (
                [GeometryQualification().to_dict() for _ in range(count)]
                if qualifications is None
                else qualifications
            ),
            "manualOverrideDecisionChecksumSha256": entry.get(
                "manualOverrideDecisionChecksumSha256"
            ),
        },
        width=width,
        height=height,
        start=start,
        count=count,
        topology=topology,
    )
    boards = cast(list[dict[str, object]], qualified["boards"])
    for board, frame in zip(boards, parsed_frames, strict=True):
        board["boardFrameQuad"] = frame.to_dict()
        board["localLatticeVersion"] = CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION
        if qualifications is None:
            board.pop("geometryQualification", None)
            board.pop("guardResolutionDisposition", None)
            board.pop("completenessStatus", None)
            board.pop("unavailableCellIndices", None)
            board["localLatticeStatus"] = "pinned_preflight"
    qualified["geometrySource"] = "pinned_v12_frame_grid"
    if qualifications is None:
        qualified.pop("qualificationPolicy", None)
        qualified.pop("manualOverrideDecisionChecksumSha256", None)
    qualified["pinnedManifestEntryChecksumSha256"] = hashlib.sha256(
        canonical_json_bytes(entry)
    ).hexdigest()
    qualified.pop("resultChecksumSha256", None)
    qualified["resultChecksumSha256"] = hashlib.sha256(canonical_json_bytes(qualified)).hexdigest()
    return qualified


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
