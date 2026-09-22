"""Strict replay of source-bound lateral search evidence, without image work."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal, cast

import numpy as np

from .geometry import Point, Quad
from .lateral_partial_contract import (
    MAXIMUM_FRAME_REVIEW_SLOTS,
    MAXIMUM_SELECTIVE_REVIEW_SLOTS,
    MINIMUM_AUTOMATIC_BOARD_RED_EDGE_COVERAGE,
    MINIMUM_REVIEWABLE_BOARD_RED_EDGE_COVERAGE,
    MINIMUM_REVIEWABLE_PAGE_MEAN_RED_EDGE_COVERAGE,
    MINIMUM_SELECTIVE_CONFIDENT_SLOTS,
    LateralPartialContractError,
    LateralPartialGeometrySnapshot,
)
from .page_geometry_registration import (
    DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
    PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO,
    PAGE_REGISTRATION_ANCHOR_MASK_VERSION,
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_FEATURES_VERSION,
    PAGE_REGISTRATION_THRESHOLDS_VERSION,
    PAGE_REGISTRATION_VERSION,
    LateralPageRegistrationCandidate,
    PageRegistrationInitialization,
    _is_lateral_ordered_grid,
    is_ordered_active_grid,
)


def load_lateral_manifest(
    root: Path,
    descriptor: object,
    *,
    game_id: str,
    source_selection_id: str,
    source_manifest_sha256: str,
    policy: LateralPartialGeometrySnapshot,
) -> Mapping[str, object]:
    if not isinstance(descriptor, Mapping):
        raise _invalid("A pinned preflight descriptor is required.")
    checksum = descriptor.get("checksumSha256")
    relative = descriptor.get("relativePath")
    if not isinstance(relative, str) or not isinstance(checksum, str):
        raise _invalid("Invalid preflight descriptor.")
    parts = PurePosixPath(relative).parts
    path = (root / Path(*parts)).resolve()
    if parts[:2] != ("data", "page-geometry-manifests") or not path.is_relative_to(
        (root / "data" / "page-geometry-manifests").resolve()
    ):
        raise _invalid("Invalid preflight path.")
    try:
        content = path.read_bytes()
        manifest = json.loads(content)
    except (OSError, ValueError) as error:
        raise _invalid(
            "The pinned preflight artifact is unavailable; prepare it explicitly."
        ) from error
    if hashlib.sha256(content).hexdigest() != checksum or not isinstance(manifest, Mapping):
        raise _invalid("The pinned preflight checksum changed.")
    require_lateral_manifest(
        manifest,
        game_id=game_id,
        source_selection_id=source_selection_id,
        source_manifest_sha256=source_manifest_sha256,
        policy=policy,
    )
    return manifest


def require_lateral_manifest(
    manifest: Mapping[str, object],
    *,
    game_id: str,
    source_selection_id: str,
    source_manifest_sha256: str,
    policy: LateralPartialGeometrySnapshot,
) -> None:
    if manifest.get("lateralPartialGeometry") is None:
        raise LateralPartialContractError(
            "IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED",
            "Prepare a v0.10.4 preflight for the existing sources; upload is not required.",
        )
    pinned = LateralPartialGeometrySnapshot.from_payload(manifest["lateralPartialGeometry"])
    if (
        pinned != policy
        or manifest.get("gameId") != game_id
        or manifest.get("sourceSelectionId") != source_selection_id
        or manifest.get("sourceManifestChecksumSha256") != source_manifest_sha256
    ):
        raise _invalid("The lateral preflight belongs to different source provenance.")


def lateral_candidate_from_entry(
    entry: Mapping[str, object],
    *,
    width: int,
    height: int,
    board_count: int,
    policy: LateralPartialGeometrySnapshot,
) -> LateralPageRegistrationCandidate | None:
    raw = entry.get("lateralRegistrationCandidate")
    if raw is None:
        return None
    expected_version = (
        "lateral-page-registration-candidate-v3"
        if policy.selective_frame_review
        else "lateral-page-registration-candidate-v2"
        if policy.frame_support_review
        else "lateral-page-registration-candidate-v1"
    )
    if (
        not isinstance(raw, Mapping)
        or entry.get("status") != "review_required"
        or entry.get("imageWidth") != width
        or entry.get("imageHeight") != height
        or raw.get("version") != expected_version
        or raw.get("origin") != "automatic_search_proposal"
        or raw.get("requiresLocalRefinement") is not True
        or raw.get("policyChecksumSha256") != policy.checksum_sha256
        or raw.get("featuresVersion") != PAGE_REGISTRATION_FEATURES_VERSION
        or raw.get("thresholdsVersion") != PAGE_REGISTRATION_THRESHOLDS_VERSION
        or raw.get("activeBoardSlots") != list(range(board_count))
    ):
        raise _invalid("The lateral candidate envelope changed.")
    try:
        anchor = raw["anchorSourceChecksumSha256"]
        if not isinstance(anchor, str) or re.fullmatch("[0-9a-f]{64}", anchor) is None:
            raise ValueError("Invalid anchor checksum.")
        values = raw["analysisQuads"]
        if not isinstance(values, list) or len(values) != board_count:
            raise ValueError("Invalid quad count.")
        quads: list[Quad] = []
        for value in values:
            if not isinstance(value, list) or len(value) != 4:
                raise ValueError("Invalid quad.")
            points = []
            for point in value:
                if not isinstance(point, dict) or set(point) != {"x", "y"}:
                    raise ValueError("Invalid point.")
                x, y = _number(point["x"]), _number(point["y"])
                if not x.is_integer() or not y.is_integer():
                    raise ValueError(
                        "Registration coordinates must preserve native integer pixels."
                    )
                points.append(Point(int(x), int(y)))
            quads.append(cast(Quad, tuple(points)))
        homography = raw["nativeHomography"]
        if not isinstance(homography, list) or len(homography) != 3:
            raise ValueError("Invalid homography.")
        matrix = tuple(
            tuple(_number(v) for v in row)
            for row in homography
            if isinstance(row, list) and len(row) == 3
        )
        if len(matrix) != 3 or abs(float(np.linalg.det(matrix))) < 1e-12:
            raise ValueError("Singular homography.")
        inliers = _integer(raw["inlierCount"])
        features = _integer(raw["featureCount"])
        ratio = _number(raw["inlierRatio"])
        residual = _number(raw["p95ReprojectionError"])
        coverage_values = raw["boardRedEdgeCoverages"]
        if not isinstance(coverage_values, list) or len(coverage_values) != board_count:
            raise ValueError("Invalid edge coverage.")
        coverages = tuple(_number(v) for v in coverage_values)
        thresholds = DEFAULT_PAGE_REGISTRATION_THRESHOLDS
        recovery_kind = raw.get("recoveryKind", "lateral_source_support")
        review_required_slots_raw = raw.get("reviewRequiredSlots", [])
        if (
            recovery_kind
            not in {"lateral_source_support", "frame_support_review", "standalone_frame_lines"}
            or not isinstance(review_required_slots_raw, list)
            or any(type(slot) is not int for slot in review_required_slots_raw)
        ):
            raise ValueError("Invalid recovery classification.")
        review_required_slots = tuple(review_required_slots_raw)
        if recovery_kind == "standalone_frame_lines":
            common_valid = (
                inliers == 0
                and features == 0
                and ratio == 0.0
                and residual == 0.0
            )
        else:
            common_valid = (
                inliers >= thresholds.minimum_inliers
                and features in {1000, 1500, 3000}
                and thresholds.minimum_inlier_ratio <= ratio <= 1
                and 0 <= residual <= thresholds.maximum_p95_reprojection_error
            )
        if recovery_kind == "standalone_frame_lines":
            geometry_valid = (
                expected_version
                in {
                    "lateral-page-registration-candidate-v2",
                    "lateral-page-registration-candidate-v3",
                }
                and review_required_slots == tuple(range(board_count))
                and is_ordered_active_grid(tuple(quads), tuple(range(board_count)), width, height)
            )
        elif recovery_kind == "frame_support_review":
            expected_review_slots = tuple(
                slot
                for slot, coverage in enumerate(coverages)
                if coverage < MINIMUM_AUTOMATIC_BOARD_RED_EDGE_COVERAGE
            )
            geometry_valid = (
                expected_version
                in {
                    "lateral-page-registration-candidate-v2",
                    "lateral-page-registration-candidate-v3",
                }
                and review_required_slots == expected_review_slots
                and 1
                <= len(review_required_slots)
                <= (
                    MAXIMUM_SELECTIVE_REVIEW_SLOTS
                    if policy.selective_frame_review
                    else MAXIMUM_FRAME_REVIEW_SLOTS
                )
                and min(coverages) >= MINIMUM_REVIEWABLE_BOARD_RED_EDGE_COVERAGE
                and sum(coverages) / len(coverages)
                >= MINIMUM_REVIEWABLE_PAGE_MEAN_RED_EDGE_COVERAGE
                and sum(value >= MINIMUM_AUTOMATIC_BOARD_RED_EDGE_COVERAGE for value in coverages)
                >= (
                    MINIMUM_SELECTIVE_CONFIDENT_SLOTS
                    if policy.selective_frame_review
                    else max(3, board_count - MAXIMUM_FRAME_REVIEW_SLOTS)
                )
                and is_ordered_active_grid(tuple(quads), tuple(range(board_count)), width, height)
            )
        else:
            geometry_valid = (
                not review_required_slots
                and all(thresholds.minimum_board_red_edge_coverage <= v <= 1 for v in coverages)
                and sum(coverages) / len(coverages) >= thresholds.minimum_mean_red_edge_coverage
                and _is_lateral_ordered_grid(tuple(quads), tuple(range(board_count)), width, height)
            )
        if not common_valid or not geometry_valid:
            raise ValueError("The candidate no longer meets its registration gates.")
        registration = raw["registrationVersion"]
        if registration not in {
            PAGE_REGISTRATION_VERSION,
            PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
        }:
            raise ValueError("Invalid registration version.")
        if registration == PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION:
            if (
                raw.get("anchorMaskVersion") != PAGE_REGISTRATION_ANCHOR_MASK_VERSION
                or raw.get("anchorMaskPaddingRatio") != PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO
            ):
                raise ValueError("Invalid anchor mask policy.")
        elif "anchorMaskVersion" in raw or "anchorMaskPaddingRatio" in raw:
            raise ValueError("Unexpected anchor mask fields.")
        candidate = LateralPageRegistrationCandidate(
            initialization=PageRegistrationInitialization(
                anchor_source_checksum_sha256=anchor,
                active_board_slots=tuple(range(board_count)),
                initialization_quads=tuple(quads),
                native_homography=cast(tuple[tuple[float, float, float], ...], matrix),
                inlier_count=inliers,
                inlier_ratio=ratio,
                p95_reprojection_error=residual,
                feature_count=features,
                registration_version=registration,
                anchor_mask_version=cast(str | None, raw.get("anchorMaskVersion")),
                anchor_mask_padding_ratio=cast(float | None, raw.get("anchorMaskPaddingRatio")),
            ),
            policy_checksum_sha256=policy.checksum_sha256,
            board_red_edge_coverages=coverages,
            recovery_kind=cast(
                Literal["lateral_source_support", "frame_support_review"], recovery_kind
            ),
            review_required_slots=review_required_slots,
            version=cast(
                Literal[
                    "lateral-page-registration-candidate-v1",
                    "lateral-page-registration-candidate-v2",
                    "lateral-page-registration-candidate-v3",
                ],
                expected_version,
            ),
        )
        # Exact serialization also rejects unknown fields and missing version fields.
        if candidate.to_payload() != dict(raw):
            raise ValueError("The candidate payload is not canonical.")
        return candidate
    except (KeyError, TypeError, ValueError) as error:
        raise _invalid(str(error)) from error


def _number(value: object) -> float:
    if type(value) not in {float, int} or not math.isfinite(cast(float, value)):
        raise ValueError("Expected a finite number.")
    return float(cast(float, value))


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("Expected an integer.")
    return value


def _invalid(message: str) -> LateralPartialContractError:
    return LateralPartialContractError("IMAGE_LATERAL_PARTIAL_ARTIFACT_INVALID", message)
