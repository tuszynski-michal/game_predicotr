"""Exact human-control bindings, independently of DB and file transport."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

TRUTH_VERSION = "protected-human-control-truth-v1"
Quad = tuple[tuple[float, float], ...]


def truth_quad(value: object) -> Quad:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("A control binding requires exactly four source-space points.")
    points = []
    for point in value:
        if isinstance(point, Mapping):
            coordinates = [point.get("x"), point.get("y")]
        elif isinstance(point, list) and len(point) == 2:
            coordinates = point
        else:
            raise ValueError("Invalid source-space point.")
        if any(
            isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)
            for v in coordinates
        ):
            raise ValueError("Control coordinates must be finite numbers.")
        points.append(tuple(float(cast(float, v)) for v in coordinates))
    return tuple(cast(tuple[float, float], point) for point in points)


def truth_checksum(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("Invalid control SHA-256.")
    return value


@dataclass(frozen=True)
class ControlTruth:
    control_id: str
    source_byte_sha256: str
    source_pixel_sha256: str
    source_width: int
    source_height: int
    position_index: int
    cell_index: int
    source_quad: Quad
    crop_pixel_sha256: str
    symbol_id: str
    symbol_code: str
    origin: str
    decision_id: str
    proof_id: str

    @classmethod
    def from_payload(cls, row: Mapping[str, object]) -> ControlTruth:
        position, cell = row["positionIndex"], row["cellIndex"]
        width, height = row["sourceWidth"], row["sourceHeight"]
        if any(type(v) is not int for v in (position, cell, width, height)) or not (
            0 <= cast(int, position) <= 8
            and 0 <= cast(int, cell) <= 14
            and cast(int, width) > 0
            and cast(int, height) > 0
        ):
            raise ValueError("Invalid control dimensions or slot/cell binding.")
        origin = row["origin"]
        if (
            origin not in {"lab_human_approved", "batch_crop_review"}
            or row.get("action") != "approve"
            or row.get("actor") != "operator"
        ):
            raise ValueError("A frozen control requires a genuine operator approval.")
        return cls(
            control_id=truth_checksum(row["controlId"]),
            source_byte_sha256=truth_checksum(row["sourceByteSha256"]),
            source_pixel_sha256=truth_checksum(row["normalizedPixelChecksumSha256"]),
            source_width=cast(int, width),
            source_height=cast(int, height),
            position_index=cast(int, position),
            cell_index=cast(int, cell),
            source_quad=truth_quad(row["sourceQuad"]),
            crop_pixel_sha256=truth_checksum(row["renderedPixelChecksumSha256"]),
            symbol_id=str(UUID(cast(str, row["expectedSymbolId"]))),
            symbol_code=cast(str, row["expectedSymbolCode"]),
            origin=cast(str, origin),
            decision_id=truth_checksum(row["decisionId"]),
            proof_id=truth_checksum(row["proofId"]),
        )


@dataclass(frozen=True)
class CurrentControlDecision:
    cell_id: str
    source_pixel_sha256: str
    source_width: int
    source_height: int
    position_index: int
    cell_index: int
    source_quad: Quad
    crop_pixel_sha256: str
    symbol_id: str
    symbol_code: str
    revision: int
    source_geometry_revision_id: str


def compare_control_truth(
    truths: Sequence[ControlTruth], decisions: Sequence[CurrentControlDecision]
) -> dict[str, object]:
    """No human decision means zero comparisons, never an invented OPEN."""
    comparisons = 0
    conflicts: list[dict[str, object]] = []
    for decision in decisions:
        for truth in truths:
            if (
                decision.source_pixel_sha256,
                decision.source_width,
                decision.source_height,
                decision.position_index,
                decision.cell_index,
                decision.source_quad,
                decision.crop_pixel_sha256,
            ) != (
                truth.source_pixel_sha256,
                truth.source_width,
                truth.source_height,
                truth.position_index,
                truth.cell_index,
                truth.source_quad,
                truth.crop_pixel_sha256,
            ):
                continue
            comparisons += 1
            if decision.symbol_code != truth.symbol_code:
                conflicts.append(
                    {
                        "controlId": truth.control_id,
                        "decisionId": truth.decision_id,
                        "origin": truth.origin,
                        "cellReviewId": decision.cell_id,
                        "cellRevision": decision.revision,
                        "sourceGeometryRevisionId": decision.source_geometry_revision_id,
                        "positionIndex": truth.position_index,
                        "cellIndex": truth.cell_index,
                        "sourceQuad": [list(p) for p in truth.source_quad],
                        "normalizedPixelChecksumSha256": truth.source_pixel_sha256,
                        "renderedPixelChecksumSha256": truth.crop_pixel_sha256,
                        "expectedSymbolId": truth.symbol_id,
                        "currentSymbolId": decision.symbol_id,
                        "expectedSymbolCode": truth.symbol_code,
                        "currentSymbolCode": decision.symbol_code,
                    }
                )
    return {
        "version": TRUTH_VERSION,
        "status": "OPEN" if conflicts else "NO_CONFLICT",
        "comparisons": comparisons,
        "conflicts": conflicts,
    }
