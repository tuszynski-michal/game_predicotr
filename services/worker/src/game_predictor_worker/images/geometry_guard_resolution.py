"""Fail-closed loader for pinned pre-import geometry guard resolutions."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Never, cast
from uuid import UUID

from game_predictor_api.domain.image_import_geometry_guard import payload_checksum
from game_predictor_api.domain.jobs import Job

from game_predictor_worker.jobs.runtime import JobHandlerError

from .source_ingestion import ManagedOriginal

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class GeometryGuardBoardResolution:
    source_checksum_sha256: str
    source_relative_path: str
    position_index: int
    sequence_number: int
    disposition: str
    symbol_grid_quad: tuple[dict[str, int], ...] | None
    unavailable_cell_indices: tuple[int, ...]
    decision_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class GeometryGuardResolutionSet:
    manifest_id: UUID
    manifest_checksum_sha256: str
    guard_job_id: UUID
    guard_report_checksum_sha256: str
    decisions: tuple[GeometryGuardBoardResolution, ...]

    def for_source(self, checksum_sha256: str) -> dict[int, GeometryGuardBoardResolution]:
        return {
            item.position_index: item
            for item in self.decisions
            if item.source_checksum_sha256 == checksum_sha256
        }

    @property
    def keys(self) -> set[tuple[str, int]]:
        return {(item.source_checksum_sha256, item.position_index) for item in self.decisions}


def load_geometry_guard_resolutions(
    *,
    artifact_root: Path,
    job: Job,
    originals: Sequence[ManagedOriginal],
    source_manifest_checksum_sha256: str,
    page_geometry_manifest_checksum_sha256: str,
) -> GeometryGuardResolutionSet | None:
    raw = job.input_payload.get("geometry_guard_resolution_manifest")
    if raw is None:
        return None
    if job.input_payload.get("schema_version") != 7 or not isinstance(raw, Mapping):
        _invalid("A geometry guard resolution manifest requires browser import schema v7.")
    rollout = job.input_payload.get("image_geometry_rollout")
    if not isinstance(rollout, Mapping) or rollout.get("geometryMode") != "structured_lattice_v3":
        _invalid("Geometry guard resolutions require the structured_lattice_v3 engine snapshot.")
    descriptor = cast(Mapping[str, object], raw)
    manifest_id = _uuid(descriptor.get("id"), "manifest id")
    guard_job_id = _uuid(descriptor.get("guardJobId"), "guard job id")
    expected_checksum = _sha256(descriptor.get("checksumSha256"), "manifest checksum")
    expected_report_checksum = _sha256(
        descriptor.get("guardReportChecksumSha256"), "guard report checksum"
    )
    _matching_sha256(
        descriptor.get("sourceManifestChecksumSha256"),
        source_manifest_checksum_sha256,
        "source manifest checksum",
    )
    _matching_sha256(
        descriptor.get("pageGeometryManifestChecksumSha256"),
        page_geometry_manifest_checksum_sha256,
        "page geometry manifest checksum",
    )
    relative = _relative_path(descriptor.get("relativePath"))
    root = artifact_root.resolve()
    path = root.joinpath(*PurePosixPath(relative).parts).resolve()
    allowed = (root / "data" / "image-geometry-guard-resolutions").resolve()
    if not path.is_relative_to(allowed) or not path.is_file():
        _invalid("The geometry guard resolution artifact is unavailable.")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            "The geometry guard resolution artifact cannot be decoded.",
        ) from error
    if not isinstance(payload, Mapping) or payload_checksum(payload) != expected_checksum:
        _invalid("The geometry guard resolution artifact checksum changed.")
    value = cast(Mapping[str, object], payload)
    if (
        value.get("schemaVersion") != "ImageGeometryGuardResolutionManifestV1"
        or value.get("gameId") != str(job.game_id)
        or value.get("browserSelectionId") != job.input_payload.get("source_selection_id")
        or value.get("guardJobId") != str(guard_job_id)
        or value.get("guardReportChecksumSha256") != expected_report_checksum
        or value.get("sourceManifestChecksumSha256") != source_manifest_checksum_sha256
        or value.get("pageGeometryManifestChecksumSha256") != page_geometry_manifest_checksum_sha256
    ):
        _invalid("The geometry guard resolution provenance differs from the import.")
    raw_decisions = value.get("decisions")
    if (
        not isinstance(raw_decisions, Sequence)
        or isinstance(raw_decisions, str | bytes)
        or not raw_decisions
    ):
        _invalid("The geometry guard resolution manifest has no decisions.")
    originals_by_checksum = {item.checksum_sha256: item for item in originals}
    decisions = tuple(
        _decision(
            cast(Mapping[str, object], item),
            originals_by_checksum,
            game_id=cast(UUID, job.game_id),
            browser_selection_id=cast(str, job.input_payload.get("source_selection_id")),
            guard_job_id=guard_job_id,
            guard_report_checksum_sha256=expected_report_checksum,
        )
        if isinstance(item, Mapping)
        else _invalid("A geometry guard resolution decision is invalid.")
        for item in raw_decisions
    )
    keys = [(item.source_checksum_sha256, item.position_index) for item in decisions]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        _invalid("Geometry guard resolutions must be unique and deterministically ordered.")
    return GeometryGuardResolutionSet(
        manifest_id=manifest_id,
        manifest_checksum_sha256=expected_checksum,
        guard_job_id=guard_job_id,
        guard_report_checksum_sha256=expected_report_checksum,
        decisions=decisions,
    )


def _decision(
    value: Mapping[str, object],
    originals: Mapping[str, ManagedOriginal],
    *,
    game_id: UUID,
    browser_selection_id: str,
    guard_job_id: UUID,
    guard_report_checksum_sha256: str,
) -> GeometryGuardBoardResolution:
    checksum = _sha256(value.get("sourceChecksumSha256"), "source checksum")
    original = originals.get(checksum)
    if original is None or value.get("sourceRelativePath") != original.source_relative_path:
        _invalid("A geometry guard decision references another source image.")
    position = _integer(value.get("positionIndex"), "position index", minimum=0, maximum=8)
    sequence_number = _integer(value.get("sequenceNumber"), "sequence number", minimum=1)
    if (
        original.sequence_range_start is None
        or original.sequence_range_end is None
        or sequence_number != original.sequence_range_start + position
        or sequence_number > original.sequence_range_end
    ):
        _invalid("A geometry guard decision changed its attested sequence slot.")
    disposition = value.get("disposition")
    if disposition not in {"corrected_full", "partial", "rejected"}:
        _invalid("A geometry guard decision has an unsupported disposition.")
    unavailable = _unavailable(value.get("unavailableCellIndices"))
    quad = _quad(value.get("symbolGridQuad"))
    if disposition == "corrected_full" and (quad is None or unavailable):
        _invalid("A full correction must provide all 15 cells.")
    if disposition == "partial" and (quad is None or not 1 <= len(unavailable) <= 14):
        _invalid("A partial correction must identify between 1 and 14 unavailable cells.")
    if disposition == "rejected" and (quad is not None or unavailable):
        _invalid("A rejected board cannot carry crop geometry.")
    revision = _integer(value.get("revision"), "decision revision", minimum=1)
    actor = value.get("actor")
    reason = value.get("reason")
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or (reason is not None and not isinstance(reason, str))
    ):
        _invalid("A geometry guard decision actor or reason is invalid.")
    decision_checksum = _sha256(value.get("decisionChecksumSha256"), "decision checksum")
    expected_decision_checksum = payload_checksum(
        {
            "actor": actor,
            "browserSelectionId": browser_selection_id,
            "disposition": disposition,
            "gameId": str(game_id),
            "guardJobId": str(guard_job_id),
            "guardReportChecksumSha256": guard_report_checksum_sha256,
            "positionIndex": position,
            "reason": reason,
            "revision": revision,
            "sequenceNumber": sequence_number,
            "sourceChecksumSha256": checksum,
            "sourceRelativePath": original.source_relative_path,
            "symbolGridQuad": quad,
            "unavailableCellIndices": list(unavailable),
        }
    )
    if decision_checksum != expected_decision_checksum:
        _invalid("A geometry guard decision checksum changed.")
    return GeometryGuardBoardResolution(
        source_checksum_sha256=checksum,
        source_relative_path=original.source_relative_path,
        position_index=position,
        sequence_number=sequence_number,
        disposition=cast(str, disposition),
        symbol_grid_quad=quad,
        unavailable_cell_indices=unavailable,
        decision_checksum_sha256=decision_checksum,
    )


def _quad(value: object) -> tuple[dict[str, int], ...] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        _invalid("A resolved symbol grid must have four points.")
    points: list[dict[str, int]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {"x", "y"}:
            _invalid("A resolved symbol-grid point is invalid.")
        x = _integer(raw.get("x"), "grid x", minimum=0)
        y = _integer(raw.get("y"), "grid y", minimum=0)
        points.append({"x": x, "y": y})
    return tuple(points)


def _unavailable(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        _invalid("Unavailable cell indices must be an array.")
    indices = tuple(
        _integer(item, "unavailable cell index", minimum=0, maximum=14) for item in value
    )
    if indices != tuple(sorted(set(indices))):
        _invalid("Unavailable cell indices must be unique and ordered.")
    return indices


def _relative_path(value: object) -> str:
    if not isinstance(value, str):
        _invalid("The geometry guard resolution path is invalid.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        _invalid("The geometry guard resolution path is unsafe.")
    return value


def _uuid(value: object, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise JobHandlerError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE",
            f"The geometry guard resolution {label} is invalid.",
        ) from error


def _integer(value: object, label: str, *, minimum: int, maximum: int | None = None) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        _invalid(f"The geometry guard resolution {label} is invalid.")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        _invalid(f"The geometry guard resolution {label} is invalid.")
    return value


def _matching_sha256(value: object, expected: str, label: str) -> None:
    if _sha256(value, label) != expected:
        _invalid(f"The geometry guard resolution {label} changed.")


def _invalid(message: str) -> Never:
    raise JobHandlerError("IMAGE_GEOMETRY_GUARD_MANIFEST_INCOMPATIBLE", message)


__all__ = [
    "GeometryGuardBoardResolution",
    "GeometryGuardResolutionSet",
    "load_geometry_guard_resolutions",
]
