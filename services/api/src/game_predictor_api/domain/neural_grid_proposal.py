"""Immutable Mumie proposals and explicit source-to-sequence associations.

Inference never qualifies geometry or invents a missing position. This contract
is shared by staging, source correction and the deferred production importer.
"""

from __future__ import annotations

import hashlib
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from .catalog import GameShapeGeometryConfiguration
from .grid_engine_profiles import (
    GridEngineModelVersion,
    grid_engine_manifest,
    grid_engine_profile_for,
)
from .image_geometry_v2 import (
    AttestedSequenceRange,
    ImageGeometryContractError,
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    canonical_json_bytes,
    source_quad_intersects_image,
)

NEURAL_GRID_PREFLIGHT_POLICY_VERSION = "page-geometry-preflight-v13-neural-mumie-pilot"
NEURAL_GRID_MANIFEST_SCHEMA_VERSION = 5
NEURAL_GRID_SNAPSHOT_VERSION = "neural-grid-proposal-snapshot-v1"
NEURAL_SOURCE_PROPOSAL_VERSION = "neural-source-proposal-v1"
NEURAL_SOURCE_BINDING_VERSION = "neural-source-binding-v1"
NEURAL_GRID_REVIEW_REASON = "NEURAL_GRID_GATE_UNCALIBRATED"
_SHA = re.compile(r"^[0-9a-f]{64}$")


class NeuralGridProposalError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _invalid(message: str) -> NeuralGridProposalError:
    return NeuralGridProposalError("NEURAL_GRID_PROPOSAL_INVALID", message)


def _object(value: object, keys: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise _invalid(f"{label} has an unsupported structure.")
    return value


def _integer(value: object, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _invalid("A source contract requires bounded integer positions and dimensions.")
    return value


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise _invalid("A source contract requires a UUID owner.")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise _invalid("A source contract requires a UUID owner.") from error


def _checksum(value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise _invalid("A source contract requires a SHA-256 pin.")
    return value


def _range(value: object) -> AttestedSequenceRange:
    raw = _object(value, {"sequenceRangeStart", "sequenceRangeEnd"}, "Sequence range")
    try:
        return AttestedSequenceRange(
            start=_integer(raw["sequenceRangeStart"]), end=_integer(raw["sequenceRangeEnd"])
        )
    except ImageGeometryContractError as error:
        raise _invalid(str(error)) from error


@dataclass(frozen=True, slots=True)
class NeuralGridSnapshot:
    expected_layout_count: int
    version: GridEngineModelVersion

    def __post_init__(self) -> None:
        _integer(self.expected_layout_count)
        if self.version.profile is not GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1:
            raise _invalid("The neural folder pilot is scoped to the registered Mumie profile.")

    @classmethod
    def for_game(
        cls, expected_layout_count: int, version: GridEngineModelVersion
    ) -> NeuralGridSnapshot:
        return cls(expected_layout_count=expected_layout_count, version=version)

    @classmethod
    def from_payload(cls, value: object) -> NeuralGridSnapshot:
        raw = _object(value, {"contractVersion", "expectedLayoutCount", "model"}, "Neural snapshot")
        if raw["contractVersion"] != NEURAL_GRID_SNAPSHOT_VERSION:
            raise _invalid("The neural snapshot version is unsupported.")
        model = raw["model"]
        profile = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1)
        if profile is None:
            raise _invalid("The registered Mumie profile is unavailable.")
        for version in profile.versions:
            if model == grid_engine_manifest(version):
                return cls(_integer(raw["expectedLayoutCount"]), version)
        raise NeuralGridProposalError(
            "NEURAL_GRID_MODEL_SNAPSHOT_DRIFT", "The frozen neural model differs from the registry."
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "contractVersion": NEURAL_GRID_SNAPSHOT_VERSION,
            "expectedLayoutCount": self.expected_layout_count,
            "model": grid_engine_manifest(self.version),
        }


def lattice_cell_quads(value: object, *, width: int, height: int) -> tuple[SourceQuad, ...]:
    """Validate exact floats, retaining each internal node rather than interpolating."""
    from .image_geometry_v2 import SourceLatticeNodes

    if not isinstance(value, list | tuple) or len(value) != 24:
        raise _invalid("A neural lattice requires 24 row-major source points.")
    points = []
    for point in value:
        raw = _object(point, {"x", "y"}, "Lattice point")
        try:
            points.append(SourcePoint(x=cast(float, raw["x"]), y=cast(float, raw["y"])))
        except ImageGeometryContractError as error:
            raise _invalid(str(error)) from error
    try:
        lattice = SourceLatticeNodes(nodes=tuple(points))
        lattice.require_manual_edit_bounds(SourceImageBounds(width=width, height=height))
        from .board_topology import BoardTopology

        topology = BoardTopology(rows=3, columns=5)
        return tuple(
            lattice.cell_quad(topology=topology, row_index=row, column_index=column)
            for row in range(3)
            for column in range(5)
        )
    except ImageGeometryContractError as error:
        raise _invalid(str(error)) from error


def lattice_visibility(quads: Sequence[SourceQuad], *, width: int, height: int) -> list[str]:
    bounds = SourceImageBounds(width=width, height=height)
    return [
        "full"
        if all(0 <= p.x <= width and 0 <= p.y <= height for p in quad.corners)
        else "partial"
        if source_quad_intersects_image(quad, bounds)
        else "outside"
        for quad in quads
    ]


def proposal_checksum_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {key: item for key, item in value.items() if key != "proposalChecksumSha256"}
        )
    ).hexdigest()


def build_neural_source_proposal(
    *,
    game_id: str,
    source_selection_id: str,
    source_checksum_sha256: str,
    source_width: int,
    source_height: int,
    original_range: AttestedSequenceRange,
    snapshot: NeuralGridSnapshot,
    detections: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {
        "contractVersion": NEURAL_SOURCE_PROPOSAL_VERSION,
        "gameId": game_id,
        "sourceSelectionId": source_selection_id,
        "sourceChecksumSha256": source_checksum_sha256,
        "sourceWidth": source_width,
        "sourceHeight": source_height,
        "originalRange": original_range.to_dict(),
        "engineSnapshot": snapshot.to_payload(),
        "detections": [dict(item) for item in detections],
    }
    value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    validate_neural_source_proposal(value)
    return value


def validate_neural_source_proposal(value: object) -> Mapping[str, object]:
    raw = _object(
        value,
        {
            "contractVersion",
            "gameId",
            "sourceSelectionId",
            "sourceChecksumSha256",
            "sourceWidth",
            "sourceHeight",
            "originalRange",
            "engineSnapshot",
            "detections",
            "proposalChecksumSha256",
        },
        "Neural source proposal",
    )
    if raw["contractVersion"] != NEURAL_SOURCE_PROPOSAL_VERSION:
        raise _invalid("The neural source proposal version is unsupported.")
    _uuid(raw["gameId"])
    _uuid(raw["sourceSelectionId"])
    _checksum(raw["sourceChecksumSha256"])
    width, height = _integer(raw["sourceWidth"]), _integer(raw["sourceHeight"])
    _range(raw["originalRange"])
    NeuralGridSnapshot.from_payload(raw["engineSnapshot"])
    checksum = _checksum(raw["proposalChecksumSha256"])
    if checksum != proposal_checksum_sha256(raw):
        raise NeuralGridProposalError(
            "NEURAL_GRID_PROPOSAL_DRIFT", "The source proposal bytes differ from their checksum."
        )
    detections = raw["detections"]
    if not isinstance(detections, list) or len(detections) > 256:
        raise _invalid("The source proposal detection inventory is invalid.")
    ids: set[str] = set()
    for detection in detections:
        item = _object(
            detection,
            {
                "detectionId",
                "score",
                "latticeNodes",
                "cellQuads",
                "cellVisibility",
                "structurallyValid",
                "reasonCodes",
            },
            "Neural detection",
        )
        detection_id = item["detectionId"]
        score = item["score"]
        reasons = item["reasonCodes"]
        if (
            not isinstance(detection_id, str)
            or not detection_id
            or len(detection_id) > 128
            or detection_id in ids
        ):
            raise _invalid("Neural detection identities must be unique and bounded.")
        ids.add(detection_id)
        if (
            isinstance(score, bool)
            or not isinstance(score, int | float)
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise _invalid("A neural detection score must be a finite probability.")
        if (
            not isinstance(reasons, list)
            or any(not isinstance(reason, str) or not reason for reason in reasons)
            or NEURAL_GRID_REVIEW_REASON not in reasons
        ):
            raise _invalid("Every neural detection remains explicitly uncalibrated.")
        if item["structurallyValid"] is True:
            quads = lattice_cell_quads(item["latticeNodes"], width=width, height=height)
            if item["cellQuads"] != [quad.to_dict() for quad in quads] or item[
                "cellVisibility"
            ] != lattice_visibility(quads, width=width, height=height):
                raise _invalid("Detection quads and visibility must describe the exact 24 nodes.")
        elif item["structurallyValid"] is False:
            if (
                item["latticeNodes"] is not None
                or item["cellQuads"] != []
                or item["cellVisibility"] != ["unknown"] * 15
            ):
                raise _invalid("Invalid detections cannot expose a renderable lattice.")
        else:
            raise _invalid("Detection structural validity must be explicit.")
    return raw


def validate_neural_source_binding(value: object, proposal: object) -> Mapping[str, object]:
    source = validate_neural_source_proposal(proposal)
    raw = _object(
        value,
        {
            "contractVersion",
            "gameId",
            "sourceSelectionId",
            "sourceChecksumSha256",
            "sourceWidth",
            "sourceHeight",
            "proposalChecksumSha256",
            "originalRange",
            "confirmedRange",
            "assignments",
            "missingPositionIndexes",
            "ignoredDetectionIds",
        },
        "Neural source binding",
    )
    if raw["contractVersion"] != NEURAL_SOURCE_BINDING_VERSION:
        raise _invalid("The neural source binding version is unsupported.")
    for field in (
        "gameId",
        "sourceSelectionId",
        "sourceChecksumSha256",
        "sourceWidth",
        "sourceHeight",
        "proposalChecksumSha256",
        "originalRange",
    ):
        if raw[field] != source[field]:
            raise NeuralGridProposalError(
                "NEURAL_GRID_BINDING_STALE", "The binding belongs to a different source proposal."
            )
    original, confirmed = _range(raw["originalRange"]), _range(raw["confirmedRange"])
    snapshot = NeuralGridSnapshot.from_payload(source["engineSnapshot"])
    if (
        not original.start
        <= confirmed.start
        <= confirmed.end
        <= min(original.end, snapshot.expected_layout_count)
    ):
        raise _invalid("A confirmed range must belong to the original source range and the game.")
    detections = {
        cast(str, item["detectionId"]): item
        for item in cast(list[Mapping[str, object]], source["detections"])
    }
    assignments = raw["assignments"]
    if not isinstance(assignments, list) or len(assignments) > confirmed.board_count:
        raise _invalid("The source assignments must belong to the active slots.")
    ids: set[str] = set()
    positions: set[int] = set()
    for assignment in assignments:
        item = _object(assignment, {"detectionId", "positionIndex"}, "Neural assignment")
        detection_id = item["detectionId"]
        position = _integer(item["positionIndex"], minimum=0)
        if (
            not isinstance(detection_id, str)
            or detection_id not in detections
            or detection_id in ids
            or position in positions
            or position >= confirmed.board_count
        ):
            raise _invalid("Detection and active-slot assignments must be unique.")
        if detections[detection_id]["structurallyValid"] is not True:
            raise _invalid("A structurally invalid detection cannot seed a board draft.")
        ids.add(detection_id)
        positions.add(position)
    if raw["missingPositionIndexes"] != sorted(
        set(range(confirmed.board_count)) - positions
    ) or raw["ignoredDetectionIds"] != sorted(set(detections) - ids):
        raise _invalid("Missing slots and ignored detections must be explicit and complete.")
    return raw


def build_neural_source_binding(
    proposal: object,
    *,
    confirmed_range: AttestedSequenceRange,
    assignments: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    source = validate_neural_source_proposal(proposal)
    items = sorted(
        (dict(item) for item in assignments), key=lambda item: cast(int, item["positionIndex"])
    )
    positions = {cast(int, item["positionIndex"]) for item in items}
    ids = {cast(str, item["detectionId"]) for item in items}
    value = {
        field: source[field]
        for field in (
            "gameId",
            "sourceSelectionId",
            "sourceChecksumSha256",
            "sourceWidth",
            "sourceHeight",
            "proposalChecksumSha256",
            "originalRange",
        )
    }
    value.update(
        contractVersion=NEURAL_SOURCE_BINDING_VERSION,
        confirmedRange=confirmed_range.to_dict(),
        assignments=items,
        missingPositionIndexes=sorted(set(range(confirmed_range.board_count)) - positions),
        ignoredDetectionIds=sorted(
            cast(str, item["detectionId"])
            for item in cast(list[Mapping[str, object]], source["detections"])
            if item["detectionId"] not in ids
        ),
    )
    validate_neural_source_binding(value, source)
    return value


def _outer(item: Mapping[str, object]) -> SourceQuad:
    nodes = cast(list[Mapping[str, float]], item["latticeNodes"])
    return SourceQuad(corners=tuple(SourcePoint(**nodes[index]) for index in (0, 5, 23, 18)))  # type: ignore[arg-type]


def _cross(a: SourcePoint, b: SourcePoint, c: SourcePoint) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _overlap(a: SourceQuad, b: SourceQuad) -> bool:
    """Separating-axis test; touching boundaries have no area overlap."""
    for polygon in (a, b):
        for index, start in enumerate(polygon.corners):
            end = polygon.corners[(index + 1) % 4]
            first = [_cross(start, end, point) for point in a.corners]
            second = [_cross(start, end, point) for point in b.corners]
            if max(first) <= min(second) + 1e-7 or max(second) <= min(first) + 1e-7:
                return False
    return True


def associate_expected_slots(proposal: object) -> dict[str, object] | None:
    """Offer a draft only for an exact, spatially unambiguous inventory."""
    source = validate_neural_source_proposal(proposal)
    sequence = _range(source["originalRange"])
    snapshot = NeuralGridSnapshot.from_payload(source["engineSnapshot"])
    detections = cast(list[Mapping[str, object]], source["detections"])
    if (
        sequence.end > snapshot.expected_layout_count
        or len(detections) != sequence.board_count
        or any(item["structurallyValid"] is not True for item in detections)
    ):
        return None
    quads = [_outer(item) for item in detections]
    if any(
        _overlap(quad, other) for index, quad in enumerate(quads) for other in quads[index + 1 :]
    ):
        return None
    source_centres = [
        (sum(point.x for point in quad.corners) / 4, sum(point.y for point in quad.corners) / 4)
        for quad in quads
    ]
    # Camera rotation can move a later column below the next row in raw y.
    # Derive axes from actual board edges before proposing a row-major draft.
    right_vectors = []
    down_vectors = []
    for quad in quads:
        points = quad.corners
        right = (
            (points[1].x - points[0].x + points[2].x - points[3].x) / 2,
            (points[1].y - points[0].y + points[2].y - points[3].y) / 2,
        )
        down = (
            (points[3].x - points[0].x + points[2].x - points[1].x) / 2,
            (points[3].y - points[0].y + points[2].y - points[1].y) / 2,
        )
        right_length, down_length = math.hypot(*right), math.hypot(*down)
        if right_length <= 1e-6 or down_length <= 1e-6:
            return None
        right_vectors.append((right[0] / right_length, right[1] / right_length))
        down_vectors.append((down[0] / down_length, down[1] / down_length))
    right = (
        statistics.median(vector[0] for vector in right_vectors),
        statistics.median(vector[1] for vector in right_vectors),
    )
    down = (
        statistics.median(vector[0] for vector in down_vectors),
        statistics.median(vector[1] for vector in down_vectors),
    )
    determinant = right[0] * down[1] - right[1] * down[0]
    if (
        determinant <= 1e-6
        or any(vector[0] * right[0] + vector[1] * right[1] <= 0 for vector in right_vectors)
        or any(vector[0] * down[0] + vector[1] * down[1] <= 0 for vector in down_vectors)
    ):
        return None

    def project(x: float, y: float) -> tuple[float, float]:
        return (
            (x * down[1] - y * down[0]) / determinant,
            (right[0] * y - right[1] * x) / determinant,
        )

    centres = [project(x, y) for x, y in source_centres]
    heights = sorted(
        abs(
            project(quad.corners[3].x - quad.corners[0].x, quad.corners[3].y - quad.corners[0].y)[1]
        )
        for quad in quads
    )
    tolerance = max(1.0, heights[len(heights) // 2] * 0.5)
    rows: list[list[int]] = []
    for index in sorted(range(len(detections)), key=lambda i: (centres[i][1], centres[i][0])):
        if (
            rows
            and abs(centres[index][1] - sum(centres[i][1] for i in rows[-1]) / len(rows[-1]))
            <= tolerance
        ):
            rows[-1].append(index)
        else:
            rows.append([index])
    if len(rows) > 3 or any(len(row) > 3 for row in rows):
        return None
    expected_rows = [
        min(3, sequence.board_count - start) for start in range(0, sequence.board_count, 3)
    ]
    if [len(row) for row in rows] != expected_rows:
        return None
    if any(
        abs(centres[a][0] - centres[b][0]) <= 1e-6
        for row in rows
        for a in row
        for b in row
        if a != b
    ):
        return None
    ordered = [index for row in rows for index in sorted(row, key=lambda i: centres[i][0])]
    return build_neural_source_binding(
        source,
        confirmed_range=sequence,
        assignments=[
            {"detectionId": detections[index]["detectionId"], "positionIndex": position}
            for position, index in enumerate(ordered)
        ],
    )
