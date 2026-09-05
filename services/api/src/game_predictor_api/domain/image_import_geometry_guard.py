"""Checksum-bound decisions for exceptional boards before image import."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID, uuid4

CELL_COUNT = 15


class ImageGeometryGuardDecisionError(ValueError):
    pass


class ImageGeometryGuardDisposition(StrEnum):
    CORRECTED_FULL = "corrected_full"
    PARTIAL = "partial"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardBoardTarget:
    source_checksum_sha256: str
    source_relative_path: str
    position_index: int
    sequence_number: int
    reason_codes: tuple[str, ...]
    page_geometry: dict[str, object] | None
    analysis_quad: object | None
    proposed_symbol_grid_quad: object | None
    evidence: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardDecision:
    id: UUID
    game_id: UUID
    browser_selection_id: UUID
    guard_job_id: UUID
    guard_report_checksum_sha256: str
    source_checksum_sha256: str
    source_relative_path: str
    position_index: int
    sequence_number: int
    revision: int
    disposition: ImageGeometryGuardDisposition
    symbol_grid_quad: tuple[dict[str, int], ...] | None
    unavailable_cell_indices: tuple[int, ...]
    reason: str | None
    actor: str
    decision_checksum_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardResolutionManifest:
    id: UUID
    game_id: UUID
    browser_selection_id: UUID
    guard_job_id: UUID
    guard_report_checksum_sha256: str
    source_manifest_checksum_sha256: str
    page_geometry_manifest_checksum_sha256: str
    manifest_relative_path: str
    manifest_checksum_sha256: str
    decision_count: int
    sealed_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImageGeometryGuardScope:
    game_id: UUID
    browser_selection_id: UUID
    browser_manifest_checksum_sha256: str
    job_input_payload: dict[str, object]
    job_checkpoint_payload: dict[str, object] | None


def create_guard_decision(
    *,
    game_id: UUID,
    browser_selection_id: UUID,
    guard_job_id: UUID,
    guard_report_checksum_sha256: str,
    target: ImageGeometryGuardBoardTarget,
    revision: int,
    disposition: ImageGeometryGuardDisposition,
    symbol_grid_quad: tuple[dict[str, int], ...] | None,
    unavailable_cell_indices: tuple[int, ...],
    reason: str | None,
    actor: str,
    created_at: datetime | None = None,
) -> ImageGeometryGuardDecision:
    _sha256(guard_report_checksum_sha256)
    _sha256(target.source_checksum_sha256)
    _relative_path(target.source_relative_path)
    if not 0 <= target.position_index <= 8 or target.sequence_number < 1 or revision < 1:
        raise ImageGeometryGuardDecisionError("The guard decision target is invalid.")
    normalized_actor = actor.strip()
    if not normalized_actor:
        raise ImageGeometryGuardDecisionError("The guard decision actor is required.")
    normalized_reason = None if reason is None else reason.strip()
    if normalized_reason == "":
        normalized_reason = None
    unavailable = tuple(sorted(set(unavailable_cell_indices)))
    if unavailable != unavailable_cell_indices or any(
        not 0 <= value < CELL_COUNT for value in unavailable
    ):
        raise ImageGeometryGuardDecisionError(
            "Unavailable cell indices must be unique, sorted and between 0 and 14."
        )
    quad = _quad(symbol_grid_quad)
    if disposition is ImageGeometryGuardDisposition.CORRECTED_FULL:
        if quad is None or unavailable:
            raise ImageGeometryGuardDecisionError(
                "A full correction requires a four-point grid and all 15 cells."
            )
    elif disposition is ImageGeometryGuardDisposition.PARTIAL:
        if quad is None or not 1 <= len(unavailable) <= 14:
            raise ImageGeometryGuardDecisionError(
                "A partial board requires geometry and between 1 and 14 unavailable cells."
            )
    elif disposition is ImageGeometryGuardDisposition.REJECTED and (
        quad is not None or unavailable or normalized_reason is None
    ):
        raise ImageGeometryGuardDecisionError(
            "A rejected board requires a reason and cannot carry crop geometry."
        )
    payload = {
        "actor": normalized_actor,
        "browserSelectionId": str(browser_selection_id),
        "disposition": disposition.value,
        "gameId": str(game_id),
        "guardJobId": str(guard_job_id),
        "guardReportChecksumSha256": guard_report_checksum_sha256,
        "positionIndex": target.position_index,
        "reason": normalized_reason,
        "revision": revision,
        "sequenceNumber": target.sequence_number,
        "sourceChecksumSha256": target.source_checksum_sha256,
        "sourceRelativePath": target.source_relative_path,
        "symbolGridQuad": quad,
        "unavailableCellIndices": list(unavailable),
    }
    return ImageGeometryGuardDecision(
        id=uuid4(),
        game_id=game_id,
        browser_selection_id=browser_selection_id,
        guard_job_id=guard_job_id,
        guard_report_checksum_sha256=guard_report_checksum_sha256,
        source_checksum_sha256=target.source_checksum_sha256,
        source_relative_path=target.source_relative_path,
        position_index=target.position_index,
        sequence_number=target.sequence_number,
        revision=revision,
        disposition=disposition,
        symbol_grid_quad=quad,
        unavailable_cell_indices=unavailable,
        reason=normalized_reason,
        actor=normalized_actor,
        decision_checksum_sha256=_checksum(payload),
        created_at=created_at or datetime.now(UTC),
    )


def resolution_manifest_payload(
    *,
    game_id: UUID,
    browser_selection_id: UUID,
    guard_job_id: UUID,
    guard_report_checksum_sha256: str,
    source_manifest_checksum_sha256: str,
    page_geometry_manifest_checksum_sha256: str,
    decisions: tuple[ImageGeometryGuardDecision, ...],
) -> dict[str, object]:
    for value in (
        guard_report_checksum_sha256,
        source_manifest_checksum_sha256,
        page_geometry_manifest_checksum_sha256,
    ):
        _sha256(value)
    ordered = sorted(
        decisions,
        key=lambda item: (item.source_checksum_sha256, item.position_index),
    )
    if not ordered:
        raise ImageGeometryGuardDecisionError("A resolution manifest cannot be empty.")
    return {
        "schemaVersion": "ImageGeometryGuardResolutionManifestV1",
        "gameId": str(game_id),
        "browserSelectionId": str(browser_selection_id),
        "guardJobId": str(guard_job_id),
        "guardReportChecksumSha256": guard_report_checksum_sha256,
        "sourceManifestChecksumSha256": source_manifest_checksum_sha256,
        "pageGeometryManifestChecksumSha256": page_geometry_manifest_checksum_sha256,
        "decisions": [
            {
                "actor": item.actor,
                "decisionChecksumSha256": item.decision_checksum_sha256,
                "disposition": item.disposition.value,
                "positionIndex": item.position_index,
                "reason": item.reason,
                "revision": item.revision,
                "sequenceNumber": item.sequence_number,
                "sourceChecksumSha256": item.source_checksum_sha256,
                "sourceRelativePath": item.source_relative_path,
                "symbolGridQuad": item.symbol_grid_quad,
                "unavailableCellIndices": list(item.unavailable_cell_indices),
            }
            for item in ordered
        ],
    }


def payload_checksum(value: object) -> str:
    return _checksum(value)


def _quad(
    value: tuple[dict[str, int], ...] | None,
) -> tuple[dict[str, int], ...] | None:
    if value is None:
        return None
    if len(value) != 4:
        raise ImageGeometryGuardDecisionError("A symbol grid requires exactly four points.")
    points: list[dict[str, int]] = []
    for point in value:
        if set(point) != {"x", "y"}:
            raise ImageGeometryGuardDecisionError("A grid point requires x and y.")
        x, y = point["x"], point["y"]
        if (
            not isinstance(x, int)
            or isinstance(x, bool)
            or not isinstance(y, int)
            or isinstance(y, bool)
            or x < 0
            or y < 0
        ):
            raise ImageGeometryGuardDecisionError("Grid coordinates must be non-negative integers.")
        points.append({"x": x, "y": y})
    return tuple(points)


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value.strip() or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ImageGeometryGuardDecisionError("The source path is not a safe relative path.")
    return value


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ImageGeometryGuardDecisionError("A checksum is not lowercase SHA-256.")
    return value


def _checksum(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CELL_COUNT",
    "ImageGeometryGuardBoardTarget",
    "ImageGeometryGuardDecision",
    "ImageGeometryGuardDecisionError",
    "ImageGeometryGuardDisposition",
    "ImageGeometryGuardResolutionManifest",
    "ImageGeometryGuardScope",
    "create_guard_decision",
    "payload_checksum",
    "resolution_manifest_payload",
]
