"""Deterministic geometry-cohort and grid-calibration domain logic."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

NormalizedQuad = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]

GRID_CALIBRATION_MANIFEST_SCHEMA_VERSION = 2
GRID_CALIBRATION_POLICY_V1 = "robust-normalized-corner-offset-v1"
GRID_CALIBRATION_POLICY_V2 = "source-specific-36-corner-registration-v2"
GRID_ANCHOR_SELECTION_POLICY_V1 = "geometry-medoid-farthest-point-16-v1"
GRID_CORNERS_PER_COMPLETE_SOURCE = 36
GRID_MAX_REGISTRATION_ANCHORS = 16


class GridProfileStatus(StrEnum):
    CANDIDATE_READY = "candidate_ready"
    REJECTED = "rejected"


class GridProfileActivationAction(StrEnum):
    ACTIVATE = "activate"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class VerifiedGeometrySample:
    board_id: UUID
    review_item_id: UUID
    source_image_id: UUID
    source_checksum_sha256: str
    image_selection_run_id: UUID | None
    position_index: int
    image_width: int
    image_height: int
    geometry_revision: int
    resolution_revision: int
    detected_quad: NormalizedQuad
    final_quad: NormalizedQuad


@dataclass(frozen=True, slots=True)
class GeometryCohort:
    id: UUID
    game_id: UUID
    cohort_number: int
    manifest_checksum_sha256: str
    manifest: dict[str, object]
    sample_count: int
    source_image_count: int
    training_count: int
    validation_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GridCalibrationProfile:
    id: UUID
    game_id: UUID
    cohort_id: UUID
    profile_number: int
    status: GridProfileStatus
    profile_checksum_sha256: str
    profile_payload: dict[str, object]
    gate_metrics: dict[str, object]
    rejection_reasons: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GridProfileActivation:
    id: UUID
    game_id: UUID
    profile_id: UUID
    previous_profile_id: UUID | None
    action: GridProfileActivationAction
    activation_number: int
    actor: str
    reason: str | None
    idempotency_key: UUID
    command_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GridProfileActivationPreview:
    game_id: UUID
    profile_id: UUID
    profile_checksum_sha256: str
    current_profile_id: UUID | None
    action: GridProfileActivationAction
    can_activate: bool


@dataclass(frozen=True, slots=True)
class GeometryCohortDiagnostics:
    game_id: UUID
    accepted_geometry_count: int
    corrected_geometry_count: int
    missing_detection_count: int
    incomplete_geometry_count: int
    source_image_count: int
    first_sequence_number: int | None
    last_sequence_number: int | None
    eligible_geometry_count: int = 0
    excluded_geometry_count: int = 0
    exclusion_reason_counts: dict[str, int] = field(default_factory=dict)


def build_geometry_manifest(
    game_id: UUID,
    samples: Iterable[VerifiedGeometrySample],
) -> tuple[dict[str, object], str]:
    ordered = sorted(
        samples,
        key=lambda item: (
            item.source_checksum_sha256,
            item.position_index,
            str(item.board_id),
        ),
    )
    source_splits = _source_splits(tuple(item.source_checksum_sha256 for item in ordered))
    payload: dict[str, object] = {
        "schemaVersion": GRID_CALIBRATION_MANIFEST_SCHEMA_VERSION,
        "gameId": str(game_id),
        "splitPolicy": "source-checksum-sha256-80-20-v2",
        "samples": [
            {
                "boardId": str(item.board_id),
                "reviewItemId": str(item.review_item_id),
                "sourceImageId": str(item.source_image_id),
                "sourceChecksumSha256": item.source_checksum_sha256,
                "imageSelectionRunId": (
                    None
                    if item.image_selection_run_id is None
                    else str(item.image_selection_run_id)
                ),
                "positionIndex": item.position_index,
                "imageWidth": item.image_width,
                "imageHeight": item.image_height,
                "geometryRevision": item.geometry_revision,
                "resolutionRevision": item.resolution_revision,
                "split": source_splits[item.source_checksum_sha256],
                "detectedQuad": _quad_payload(item.detected_quad),
                "finalQuad": _quad_payload(item.final_quad),
            }
            for item in ordered
        ],
    }
    return payload, _checksum(payload)


def train_grid_profile(
    manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], tuple[str, ...]]:
    if manifest.get("schemaVersion") == 1:
        return _train_legacy_grid_profile_v1(manifest)
    return _train_source_specific_grid_profile_v2(manifest)


def _train_source_specific_grid_profile_v2(
    manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], tuple[str, ...]]:
    raw_samples = manifest.get("samples")
    if not isinstance(raw_samples, list):
        raise ValueError("Geometry cohort samples are missing.")
    samples = [item for item in raw_samples if isinstance(item, dict)]
    complete_pages, incomplete_source_count = _complete_source_pages(samples)
    training_pages = [page for page in complete_pages if page[0].get("split") == "training"]
    validation_pages = [page for page in complete_pages if page[0].get("split") == "validation"]
    anchor_checksums = _select_geometry_diverse_anchors(
        training_pages,
        limit=GRID_MAX_REGISTRATION_ANCHORS,
    )
    baseline_errors = [_source_page_error(page) for page in complete_pages]
    baseline = _error_metrics(baseline_errors)
    manually_corrected_sources = sum(_source_page_has_correction(page) for page in complete_pages)
    reasons: list[str] = []
    if len(complete_pages) < 3:
        reasons.append("INSUFFICIENT_COMPLETE_SOURCE_COVERAGE")
    if len(training_pages) < 2 or not anchor_checksums:
        reasons.append("TRAINING_SOURCE_SET_INSUFFICIENT")
    if not validation_pages:
        reasons.append("VALIDATION_SOURCE_SET_EMPTY")
    profile: dict[str, object] = {
        "schemaVersion": 2,
        "calibrationPolicy": GRID_CALIBRATION_POLICY_V2,
        "cohortChecksumSha256": _checksum(manifest),
        "cornerCountPerSource": GRID_CORNERS_PER_COMPLETE_SOURCE,
        "anchorSelectionPolicy": GRID_ANCHOR_SELECTION_POLICY_V1,
        "anchorSourceChecksums": list(anchor_checksums),
        "runtimeValidationPolicy": "target-specific-homography-and-nine-red-edge-gates-v1",
        # Kept empty intentionally. A v2 profile must never fall back to the
        # source-independent median offsets used by historical v1 profiles.
        "scopes": [],
        "positionFallbacks": [],
    }
    metrics: dict[str, object] = {
        "trainingSampleCount": len(training_pages) * 9,
        "validationSampleCount": len(validation_pages) * 9,
        "completeSourceCount": len(complete_pages),
        "incompleteSourceCount": incomplete_source_count,
        "trainingSourceCount": len(training_pages),
        "validationSourceCount": len(validation_pages),
        "anchorSourceCount": len(anchor_checksums),
        "trainingCornerCount": len(training_pages) * GRID_CORNERS_PER_COMPLETE_SOURCE,
        "validationCornerCount": len(validation_pages) * GRID_CORNERS_PER_COMPLETE_SOURCE,
        "manualCorrectionSourceCount": manually_corrected_sources,
        "sourceGeometryError": baseline,
        "runtimeFailClosed": True,
        "passed": not reasons,
    }
    return profile, metrics, tuple(reasons)


def _train_legacy_grid_profile_v1(
    manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], tuple[str, ...]]:
    """Retain the exact historical v1 trainer for replay and golden tests."""

    raw_samples = manifest.get("samples")
    if not isinstance(raw_samples, list):
        raise ValueError("Geometry cohort samples are missing.")
    samples = [item for item in raw_samples if isinstance(item, dict)]
    training = [item for item in samples if item.get("split") == "training"]
    validation = [item for item in samples if item.get("split") == "validation"]
    scopes = _offset_scopes(training, include_run=True)
    positions = _offset_scopes(training, include_run=False)
    profile: dict[str, object] = {
        "schemaVersion": 1,
        "calibrationPolicy": GRID_CALIBRATION_POLICY_V1,
        "cohortChecksumSha256": _checksum(manifest),
        "scopes": scopes,
        "positionFallbacks": positions,
    }
    baseline_errors = [_sample_error(item, None) for item in validation]
    candidate_errors = [_sample_error(item, profile) for item in validation]
    baseline = _error_metrics(baseline_errors)
    candidate = _error_metrics(candidate_errors)
    baseline["validProjectedQuadRate"] = _valid_quad_rate(validation, None)
    candidate["validProjectedQuadRate"] = _valid_quad_rate(validation, profile)
    reasons: list[str] = []
    if len({str(item.get("sourceChecksumSha256")) for item in samples}) < 2:
        reasons.append("INSUFFICIENT_SOURCE_IMAGE_COVERAGE")
    if len(validation) < 1:
        reasons.append("VALIDATION_SET_EMPTY")
    if not scopes and not positions:
        reasons.append("CALIBRATION_SCOPES_EMPTY")
    if baseline_errors:
        no_regression = (
            candidate["meanNormalizedCornerError"] <= baseline["meanNormalizedCornerError"] + 1e-9
            and candidate["p95NormalizedCornerError"] <= baseline["p95NormalizedCornerError"] + 1e-9
        )
        improved = (
            candidate["meanNormalizedCornerError"] < baseline["meanNormalizedCornerError"] - 1e-6
            or candidate["p95NormalizedCornerError"] < baseline["p95NormalizedCornerError"] - 1e-6
        )
        if not no_regression:
            reasons.append("GRID_ERROR_REGRESSION")
        if not improved:
            reasons.append("GRID_ERROR_NOT_IMPROVED")
        if candidate["validProjectedQuadRate"] < baseline["validProjectedQuadRate"]:
            reasons.append("GRID_PROJECTED_QUAD_COMPLETENESS_REGRESSION")
    metrics: dict[str, object] = {
        "trainingSampleCount": len(training),
        "validationSampleCount": len(validation),
        "baseline": baseline,
        "candidate": candidate,
        "scopeCount": len(scopes),
        "positionFallbackCount": len(positions),
        "passed": not reasons,
    }
    return profile, metrics, tuple(reasons)


def profile_checksum(profile: dict[str, object]) -> str:
    return _checksum(profile)


def activation_command_sha256(
    *,
    game_id: UUID,
    profile_id: UUID,
    expected_profile_checksum_sha256: str,
    expected_current_profile_id: UUID | None,
    action: GridProfileActivationAction,
    actor: str,
    reason: str | None,
) -> str:
    return _checksum(
        {
            "gameId": str(game_id),
            "profileId": str(profile_id),
            "expectedProfileChecksumSha256": expected_profile_checksum_sha256,
            "expectedCurrentProfileId": (
                None if expected_current_profile_id is None else str(expected_current_profile_id)
            ),
            "action": action.value,
            "actor": actor,
            "reason": reason,
        }
    )


def _source_splits(checksums: tuple[str, ...]) -> dict[str, str]:
    unique = sorted(set(checksums))
    splits = {
        checksum: ("training" if int(checksum[:8], 16) % 100 < 80 else "validation")
        for checksum in unique
    }
    if len(unique) > 1 and "validation" not in splits.values():
        splits[unique[-1]] = "validation"
    if len(unique) > 1 and "training" not in splits.values():
        splits[unique[0]] = "training"
    return splits


def _complete_source_pages(
    samples: list[dict[str, object]],
) -> tuple[list[tuple[dict[str, object], ...]], int]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in samples:
        checksum = item.get("sourceChecksumSha256")
        if isinstance(checksum, str):
            grouped.setdefault(checksum, []).append(item)
    complete: list[tuple[dict[str, object], ...]] = []
    incomplete = 0
    for checksum in sorted(grouped):
        rows = grouped[checksum]
        by_position: dict[int, dict[str, object]] = {}
        duplicated = False
        for row in rows:
            position = row.get("positionIndex")
            if not isinstance(position, int) or position in by_position:
                duplicated = True
                continue
            by_position[position] = row
        page = tuple(by_position.get(position, {}) for position in range(9))
        if duplicated or any(not row for row in page) or not _source_page_is_valid(page):
            incomplete += 1
            continue
        complete.append(page)
    return complete, incomplete


def _source_page_is_valid(page: tuple[dict[str, object], ...]) -> bool:
    if len(page) != 9:
        return False
    width = page[0].get("imageWidth")
    height = page[0].get("imageHeight")
    split = page[0].get("split")
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
        or split not in {"training", "validation"}
    ):
        return False
    quads: list[NormalizedQuad] = []
    for position, row in enumerate(page):
        if (
            row.get("positionIndex") != position
            or row.get("imageWidth") != width
            or row.get("imageHeight") != height
            or row.get("split") != split
        ):
            return False
        quad = _manifest_quad(row.get("finalQuad"))
        if quad is None or not _quad_is_valid(quad):
            return False
        if any(not (0 <= x < width and 0 <= y < height) for x, y in quad):
            return False
        quads.append(quad)
    centers = [
        (sum(point[0] for point in quad) / 4, sum(point[1] for point in quad) / 4) for quad in quads
    ]
    rows_are_ordered = all(
        centers[row * 3][0] < centers[row * 3 + 1][0] < centers[row * 3 + 2][0] for row in range(3)
    )
    columns_are_ordered = all(
        centers[column][1] < centers[column + 3][1] < centers[column + 6][1] for column in range(3)
    )
    return rows_are_ordered and columns_are_ordered


def _source_page_signature(page: tuple[dict[str, object], ...]) -> tuple[float, ...]:
    width = cast(int, page[0]["imageWidth"])
    height = cast(int, page[0]["imageHeight"])
    values: list[float] = []
    for row in page:
        quad = _manifest_quad(row.get("finalQuad"))
        if quad is None:
            raise ValueError("A complete source page must contain nine final quads.")
        for x, y in quad:
            values.extend((x / width, y / height))
    return tuple(values)


def _signature_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) / len(left))


def _select_geometry_diverse_anchors(
    pages: list[tuple[dict[str, object], ...]],
    *,
    limit: int,
) -> tuple[str, ...]:
    if not pages or limit < 1:
        return ()
    candidates = [
        (
            str(page[0]["sourceChecksumSha256"]),
            _source_page_signature(page),
        )
        for page in pages
    ]
    candidates.sort(key=lambda value: value[0])
    # Start with the medoid so the fast path represents the most typical page,
    # then add the farthest geometry from the already selected set. This keeps
    # the profile bounded while retaining different perspective/curvature
    # arrangements captured by all 36 approved corners.
    first = min(
        candidates,
        key=lambda candidate: (
            sum(_signature_distance(candidate[1], other[1]) for other in candidates),
            candidate[0],
        ),
    )
    selected = [first]
    remaining = [candidate for candidate in candidates if candidate[0] != first[0]]
    while remaining and len(selected) < limit:
        next_candidate = min(
            remaining,
            key=lambda candidate: (
                -min(_signature_distance(candidate[1], chosen[1]) for chosen in selected),
                candidate[0],
            ),
        )
        selected.append(next_candidate)
        remaining = [candidate for candidate in remaining if candidate[0] != next_candidate[0]]
    return tuple(candidate[0] for candidate in selected)


def _source_page_error(page: tuple[dict[str, object], ...]) -> float:
    errors = [_sample_error(row, None) for row in page]
    return sum(errors) / len(errors)


def _source_page_has_correction(page: tuple[dict[str, object], ...]) -> bool:
    return any(_sample_error(row, None) > 1e-9 for row in page)


def _quad_payload(quad: NormalizedQuad) -> list[dict[str, float]]:
    return [{"x": point[0], "y": point[1]} for point in quad]


def _offset_scopes(
    samples: list[dict[str, object]], *, include_run: bool
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[list[tuple[float, float]]]] = {}
    for item in samples:
        raw_run = item.get("imageSelectionRunId")
        if include_run:
            if not isinstance(raw_run, str):
                continue
            run = raw_run
        else:
            run = "*"
        position = item.get("positionIndex")
        width = item.get("imageWidth")
        height = item.get("imageHeight")
        detected = _manifest_quad(item.get("detectedQuad"))
        final = _manifest_quad(item.get("finalQuad"))
        if (
            not isinstance(position, int)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or width < 1
            or height < 1
            or detected is None
            or final is None
        ):
            continue
        offsets = [
            ((target[0] - source[0]) / width, (target[1] - source[1]) / height)
            for source, target in zip(detected, final, strict=True)
        ]
        grouped.setdefault((run, position), []).append(offsets)
    output: list[dict[str, object]] = []
    for (run, position), values in sorted(grouped.items()):
        corners = [
            {
                "x": statistics.median(value[index][0] for value in values),
                "y": statistics.median(value[index][1] for value in values),
            }
            for index in range(4)
        ]
        row: dict[str, object] = {
            "positionIndex": position,
            "sampleCount": len(values),
            "normalizedCornerOffsets": corners,
        }
        if include_run:
            row["imageSelectionRunId"] = run
        output.append(row)
    return output


def _sample_error(item: dict[str, object], profile: dict[str, object] | None) -> float:
    width = item.get("imageWidth")
    height = item.get("imageHeight")
    detected = _manifest_quad(item.get("detectedQuad"))
    final = _manifest_quad(item.get("finalQuad"))
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
        or detected is None
        or final is None
    ):
        return 1.0
    predicted = _predicted_quad(item, profile)
    if predicted is None:
        return 1.0
    diagonal = math.hypot(width, height)
    return (
        sum(
            math.hypot(source[0] - target[0], source[1] - target[1]) / diagonal
            for source, target in zip(predicted, final, strict=True)
        )
        / 4
    )


def _valid_quad_rate(samples: list[dict[str, object]], profile: dict[str, object] | None) -> float:
    if not samples:
        return 0.0
    valid = sum(_quad_is_valid(_predicted_quad(item, profile)) for item in samples)
    return valid / len(samples)


def _predicted_quad(
    item: dict[str, object], profile: dict[str, object] | None
) -> NormalizedQuad | None:
    width = item.get("imageWidth")
    height = item.get("imageHeight")
    detected = _manifest_quad(item.get("detectedQuad"))
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
        or detected is None
    ):
        return None
    offsets = _profile_offsets(profile, item) if profile is not None else None
    if offsets is None:
        return detected
    return tuple(
        (
            detected[index][0] + offsets[index][0] * width,
            detected[index][1] + offsets[index][1] * height,
        )
        for index in range(4)
    )  # type: ignore[return-value]


def _quad_is_valid(quad: NormalizedQuad | None) -> bool:
    if quad is None:
        return False
    area = 0.0
    for index, point in enumerate(quad):
        next_point = quad[(index + 1) % 4]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) > 1.0


def _profile_offsets(profile: dict[str, object], item: dict[str, object]) -> NormalizedQuad | None:
    position = item.get("positionIndex")
    run = item.get("imageSelectionRunId")
    for key, require_run in (("scopes", True), ("positionFallbacks", False)):
        values = profile.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict) or value.get("positionIndex") != position:
                continue
            if require_run and value.get("imageSelectionRunId") != run:
                continue
            return _manifest_quad(value.get("normalizedCornerOffsets"))
    return None


def _manifest_quad(value: object) -> NormalizedQuad | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    points: list[tuple[float, float]] = []
    for raw in value:
        if not isinstance(raw, dict):
            return None
        x = raw.get("x")
        y = raw.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            return None
        points.append((float(x), float(y)))
    return tuple(points)  # type: ignore[return-value]


def _error_metrics(errors: list[float]) -> dict[str, float | int]:
    if not errors:
        return {
            "sampleCount": 0,
            "meanNormalizedCornerError": 0.0,
            "p95NormalizedCornerError": 0.0,
        }
    ordered = sorted(errors)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "sampleCount": len(errors),
        "meanNormalizedCornerError": sum(errors) / len(errors),
        "p95NormalizedCornerError": ordered[index],
    }


def _checksum(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


__all__ = [
    "GeometryCohort",
    "GridCalibrationProfile",
    "GridProfileActivation",
    "GridProfileActivationAction",
    "GridProfileActivationPreview",
    "GridProfileStatus",
    "NormalizedQuad",
    "VerifiedGeometrySample",
    "activation_command_sha256",
    "build_geometry_manifest",
    "profile_checksum",
    "train_grid_profile",
]
