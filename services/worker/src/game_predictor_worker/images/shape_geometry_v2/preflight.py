"""Pinned-profile parsing and local verification for shape-geometry preflight."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.global_geometry_library import (
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileVersion,
    GlobalGeometryTopology,
    global_geometry_profile_descriptor_checksum,
    global_geometry_profile_preflight_reference,
    validate_checksum,
    validate_global_geometry_profile_descriptor,
)
from numpy.typing import NDArray

from .core import (
    SHAPE_GEOMETRY_V2_CORE_VERSION,
    ShapeGeometryV2Error,
    ShapeGeometryV2Status,
    detect_shape_geometry_v2,
)

SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION = "shape-geometry-v2-preflight-profile-v1"
SHAPE_GEOMETRY_V2_LOCAL_VERIFICATION_VERSION = "shape-geometry-v2-local-verification-v1"
SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION = "shape-geometry-v2-local-policy-v1"
SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION = (
    "page-geometry-preflight-v4-shape-geometry-v2-profile"
)
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")


class ShapeGeometryV2PreflightError(ValueError):
    """Stable fail-closed error for a pinned shared-profile input."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2PreflightProfile:
    profile_id: UUID
    profile_number: int
    profile_checksum_sha256: str
    profile_descriptor_checksum_sha256: str
    geometry_family: str
    topology: GlobalGeometryTopology
    normalized_template: dict[str, object]
    frame_appearance: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION,
            "profileId": str(self.profile_id),
            "profileNumber": self.profile_number,
            "profileChecksumSha256": self.profile_checksum_sha256,
            "profileDescriptorChecksumSha256": self.profile_descriptor_checksum_sha256,
            "geometryFamily": self.geometry_family,
            "topology": self.topology.to_dict(),
            "normalizedTemplate": _json_object(self.normalized_template),
            "frameAppearance": _json_object(self.frame_appearance),
            "localVerification": {
                "schemaVersion": SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION,
                "colorCompatibility": "structural_only",
            },
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryV2LocalVerification:
    verdict: str
    reason_code: str
    observed_aspect_ratio: float | None
    core_result: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": SHAPE_GEOMETRY_V2_LOCAL_VERIFICATION_VERSION,
            "verdict": self.verdict,
            "reasonCode": self.reason_code,
            "observedAspectRatio": (
                None
                if self.observed_aspect_ratio is None
                else round(self.observed_aspect_ratio, 8)
            ),
            "coreResult": _json_object(self.core_result),
        }


def build_shape_geometry_v2_preflight_profile(
    profile: GlobalGeometryProfileVersion,
) -> dict[str, object]:
    """Build an immutable job snapshot from a single active global profile."""

    return parse_shape_geometry_v2_preflight_profile(
        {
            "schemaVersion": SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION,
            **global_geometry_profile_preflight_reference(profile),
            "localVerification": {
                "schemaVersion": SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION,
                "colorCompatibility": "structural_only",
            },
        }
    ).to_payload()


def parse_shape_geometry_v2_preflight_profile(
    payload: object,
) -> ShapeGeometryV2PreflightProfile:
    """Parse a closed, descriptor-only preflight profile snapshot."""

    if not isinstance(payload, Mapping) or set(payload) != {
        "schemaVersion",
        "profileId",
        "profileNumber",
        "profileChecksumSha256",
        "profileDescriptorChecksumSha256",
        "geometryFamily",
        "topology",
        "normalizedTemplate",
        "frameAppearance",
        "localVerification",
    }:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The pinned shared shape-geometry profile has an invalid structure.",
        )
    if payload.get("schemaVersion") != SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The pinned shared shape-geometry profile has an unsupported version.",
        )
    try:
        profile_id = UUID(str(payload["profileId"]))
    except (KeyError, ValueError, TypeError) as error:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The pinned shared shape-geometry profile ID is invalid.",
        ) from error
    profile_number = payload.get("profileNumber")
    checksum = payload.get("profileChecksumSha256")
    descriptor_checksum = payload.get("profileDescriptorChecksumSha256")
    geometry_family = payload.get("geometryFamily")
    if (
        not isinstance(profile_number, int)
        or isinstance(profile_number, bool)
        or profile_number < 1
        or not isinstance(checksum, str)
        or not _CHECKSUM.fullmatch(checksum)
        or not isinstance(descriptor_checksum, str)
        or not _CHECKSUM.fullmatch(descriptor_checksum)
        or geometry_family != SUPPORTED_GEOMETRY_FAMILY
    ):
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The pinned shared shape-geometry profile identity is invalid.",
        )
    try:
        validate_checksum(checksum)
        topology = _topology_from_payload(payload["topology"])
        template = _require_mapping(payload["normalizedTemplate"], "normalized template")
        appearance = _require_mapping(payload["frameAppearance"], "frame appearance")
        canonical_template, canonical_appearance = validate_global_geometry_profile_descriptor(
            geometry_family=geometry_family,
            topology=topology,
            normalized_template=template,
            frame_appearance=appearance,
        )
        if descriptor_checksum != global_geometry_profile_descriptor_checksum(
            geometry_family=geometry_family,
            topology=topology,
            normalized_template=canonical_template,
            frame_appearance=canonical_appearance,
        ):
            raise ShapeGeometryV2PreflightError(
                "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INTEGRITY_INVALID",
                "The pinned shared shape-geometry descriptors do not match their checksum.",
            )
    except GlobalGeometryLibraryError as error:
        raise ShapeGeometryV2PreflightError(error.code, str(error)) from error
    _validate_local_policy(payload["localVerification"])
    return ShapeGeometryV2PreflightProfile(
        profile_id=profile_id,
        profile_number=profile_number,
        profile_checksum_sha256=checksum,
        profile_descriptor_checksum_sha256=descriptor_checksum,
        geometry_family=geometry_family,
        topology=topology,
        normalized_template=_json_object(canonical_template),
        frame_appearance=_json_object(canonical_appearance),
    )


def verify_shape_geometry_v2_profile(
    rgb: NDArray[np.uint8],
    profile: ShapeGeometryV2PreflightProfile,
) -> ShapeGeometryV2LocalVerification:
    """Check current pixels locally without granting import-ready geometry."""

    try:
        result = detect_shape_geometry_v2(rgb)
    except ShapeGeometryV2Error as error:
        return ShapeGeometryV2LocalVerification(
            verdict="needs_manual_review",
            reason_code=error.code,
            observed_aspect_ratio=None,
            core_result={
                "coreVersion": SHAPE_GEOMETRY_V2_CORE_VERSION,
                "status": ShapeGeometryV2Status.NEEDS_MANUAL_REVIEW.value,
                "reasonCodes": [error.code],
            },
        )
    core_result = result.as_dict()
    if result.status is not ShapeGeometryV2Status.PROPOSAL or result.frame_quad is None:
        return ShapeGeometryV2LocalVerification(
            verdict="needs_manual_review",
            reason_code="SHAPE_GEOMETRY_V2_CORE_REVIEW_REQUIRED",
            observed_aspect_ratio=None,
            core_result=core_result,
        )
    if len(result.boards) != 9 or any(len(board.cell_quads) != 15 for board in result.boards):
        return ShapeGeometryV2LocalVerification(
            verdict="needs_manual_review",
            reason_code="SHAPE_GEOMETRY_V2_GRID_TOPOLOGY_MISMATCH",
            observed_aspect_ratio=None,
            core_result=core_result,
        )
    observed_aspect_ratio = _quad_aspect_ratio(result.frame_quad)
    aspect_range = cast(Mapping[str, object], profile.normalized_template["aspectRatioRange"])
    minimum = float(cast(int | float, aspect_range["minimum"]))
    maximum = float(cast(int | float, aspect_range["maximum"]))
    if not minimum <= observed_aspect_ratio <= maximum:
        return ShapeGeometryV2LocalVerification(
            verdict="needs_manual_review",
            reason_code="SHAPE_GEOMETRY_V2_ASPECT_RATIO_MISMATCH",
            observed_aspect_ratio=observed_aspect_ratio,
            core_result=core_result,
        )
    return ShapeGeometryV2LocalVerification(
        verdict="proposal_requires_manual_confirmation",
        reason_code="SHAPE_GEOMETRY_V2_MANUAL_CONFIRMATION_REQUIRED",
        observed_aspect_ratio=observed_aspect_ratio,
        core_result=core_result,
    )


def _topology_from_payload(value: object) -> GlobalGeometryTopology:
    if not isinstance(value, Mapping) or set(value) != {
        "pageBoardRows",
        "pageBoardColumns",
        "boardCellRows",
        "boardCellColumns",
    }:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The pinned shared shape-geometry topology is invalid.",
        )
    values = tuple(value[field] for field in sorted(value))
    if any(not isinstance(item, int) or isinstance(item, bool) for item in values):
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The pinned shared shape-geometry topology has non-integer dimensions.",
        )
    return GlobalGeometryTopology(
        page_board_rows=cast(int, value["pageBoardRows"]),
        page_board_columns=cast(int, value["pageBoardColumns"]),
        board_cell_rows=cast(int, value["boardCellRows"]),
        board_cell_columns=cast(int, value["boardCellColumns"]),
    )


def _validate_local_policy(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {"schemaVersion", "colorCompatibility"}:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The local shape-geometry verification policy is invalid.",
        )
    if (
        value.get("schemaVersion") != SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION
        or value.get("colorCompatibility") != "structural_only"
    ):
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            "The local shape-geometry verification policy is unsupported.",
        )


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_INVALID",
            f"The pinned shared shape-geometry {name} is invalid.",
        )
    return cast(Mapping[str, object], value)


def _quad_aspect_ratio(points: Sequence[tuple[float, float]]) -> float:
    if len(points) != 4:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_LOCAL_GEOMETRY_INVALID",
            "The detected frame does not have four corners.",
        )
    top = math.dist(points[0], points[1])
    bottom = math.dist(points[2], points[3])
    right = math.dist(points[1], points[2])
    left = math.dist(points[3], points[0])
    vertical = (right + left) / 2.0
    if not math.isfinite(vertical) or vertical <= 0.0:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_LOCAL_GEOMETRY_INVALID",
            "The detected frame has an invalid aspect ratio.",
        )
    ratio = ((top + bottom) / 2.0) / vertical
    if not math.isfinite(ratio) or ratio <= 0.0:
        raise ShapeGeometryV2PreflightError(
            "SHAPE_GEOMETRY_V2_LOCAL_GEOMETRY_INVALID",
            "The detected frame has an invalid aspect ratio.",
        )
    return ratio


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):  # pragma: no cover - guarded by Mapping input
        raise AssertionError("JSON mapping did not decode to an object")
    return cast(dict[str, object], decoded)


__all__ = [
    "SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION",
    "SHAPE_GEOMETRY_V2_LOCAL_VERIFICATION_VERSION",
    "SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION",
    "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION",
    "ShapeGeometryV2LocalVerification",
    "ShapeGeometryV2PreflightError",
    "ShapeGeometryV2PreflightProfile",
    "build_shape_geometry_v2_preflight_profile",
    "parse_shape_geometry_v2_preflight_profile",
    "verify_shape_geometry_v2_profile",
]
