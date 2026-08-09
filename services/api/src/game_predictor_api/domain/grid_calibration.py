"""Deterministic geometry-cohort and grid-calibration domain logic."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

NormalizedQuad = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]


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
    image_selection_run_id: UUID
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
        "schemaVersion": 1,
        "gameId": str(game_id),
        "splitPolicy": "source-checksum-sha256-80-20-v1",
        "samples": [
            {
                "boardId": str(item.board_id),
                "reviewItemId": str(item.review_item_id),
                "sourceImageId": str(item.source_image_id),
                "sourceChecksumSha256": item.source_checksum_sha256,
                "imageSelectionRunId": str(item.image_selection_run_id),
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
        "calibrationPolicy": "robust-normalized-corner-offset-v1",
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


def _quad_payload(quad: NormalizedQuad) -> list[dict[str, float]]:
    return [{"x": point[0], "y": point[1]} for point in quad]


def _offset_scopes(
    samples: list[dict[str, object]], *, include_run: bool
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[list[tuple[float, float]]]] = {}
    for item in samples:
        run = str(item.get("imageSelectionRunId")) if include_run else "*"
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
    for key, require_run in (("scopes", True),):
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
