"""Verified, target-specific registration of complete 3 x 3 layout pages.

The legacy detector is deliberately not used as a recovery mechanism here.
It can find a red border that is joined to the navigation UI and then invent
the remaining cells.  A registration result is useful only when all nine
target quads originate in a reviewed page and have independent red-border
evidence on the target image.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .geometry import Point, Quad

PAGE_REGISTRATION_VERSION: Final = "verified-page-registration-v1"
PAGE_REGISTRATION_THRESHOLDS_VERSION: Final = "verified-page-registration-thresholds-v1"
# Registration starts with the 1,000-feature profile used by the overwhelming
# majority of pages.  A small, visually clear cluster of strongly oblique pages
# does not retain enough distinct ORB features at that budget, even though it
# satisfies every geometric/red-frame proof at 1,500 or 3,000 features.  Those
# larger budgets are therefore a deterministic *fallback*, attempted only after
# the smaller budget has already failed closed.  This preserves the fast path
# for ordinary pages while keeping a valid page out of manual correction solely
# because of an optimisation budget.
PAGE_REGISTRATION_FEATURES_VERSION: Final = "orb-1000-1500-3000-fallback-v1"
_ORB_FEATURE_COUNTS: Final = (1000, 1500, 3000)


@dataclass(frozen=True, slots=True)
class PageRegistrationThresholds:
    minimum_inliers: int = 35
    minimum_inlier_ratio: float = 0.23
    maximum_p95_reprojection_error: float = 2.5
    minimum_mean_red_edge_coverage: float = 0.70
    minimum_board_red_edge_coverage: float = 0.45


DEFAULT_PAGE_REGISTRATION_THRESHOLDS = PageRegistrationThresholds()


@dataclass(frozen=True, slots=True)
class RegisteredPageGeometry:
    anchor_source_checksum_sha256: str
    quads: tuple[Quad, ...]
    board_red_edge_coverages: tuple[float, ...]
    inlier_count: int
    inlier_ratio: float
    p95_reprojection_error: float
    mean_red_edge_coverage: float
    feature_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "anchorSourceChecksumSha256": self.anchor_source_checksum_sha256,
            "boardRedEdgeCoverages": [round(value, 6) for value in self.board_red_edge_coverages],
            "featureCount": self.feature_count,
            "featuresVersion": PAGE_REGISTRATION_FEATURES_VERSION,
            "inlierCount": self.inlier_count,
            "inlierRatio": round(self.inlier_ratio, 6),
            "meanRedEdgeCoverage": round(self.mean_red_edge_coverage, 6),
            "p95ReprojectionError": round(self.p95_reprojection_error, 6),
            "quads": [[point.to_dict() for point in quad] for quad in self.quads],
            "registrationVersion": PAGE_REGISTRATION_VERSION,
            "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
        }


@dataclass(frozen=True, slots=True)
class PageRegistrationInitialization:
    """Global anchor registration before any local board refinement.

    The projected quads are deliberately named initialization quads. They are
    useful as bounded ROIs for the structured engine, but are not proof that a
    board border or its internal symbol grid is valid on the target image.
    """

    anchor_source_checksum_sha256: str
    active_board_slots: tuple[int, ...]
    initialization_quads: tuple[Quad, ...]
    native_homography: tuple[tuple[float, float, float], ...]
    inlier_count: int
    inlier_ratio: float
    p95_reprojection_error: float
    feature_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "activeBoardSlots": list(self.active_board_slots),
            "anchorSourceChecksumSha256": self.anchor_source_checksum_sha256,
            "featureCount": self.feature_count,
            "featuresVersion": PAGE_REGISTRATION_FEATURES_VERSION,
            "inlierCount": self.inlier_count,
            "inlierRatio": round(self.inlier_ratio, 6),
            "initializationQuads": [
                [point.to_dict() for point in quad] for quad in self.initialization_quads
            ],
            "nativeHomography": [list(row) for row in self.native_homography],
            "p95ReprojectionError": round(self.p95_reprojection_error, 6),
            "registrationVersion": PAGE_REGISTRATION_VERSION,
            "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
        }


@dataclass(frozen=True, slots=True)
class _Anchor:
    source_checksum_sha256: str
    feature_descriptors: NDArray[np.uint8]
    feature_points: Sequence[cv2.KeyPoint]
    quads: tuple[Quad, ...]


@dataclass(frozen=True, slots=True)
class _MatchedAnchor:
    anchor: _Anchor
    inlier_count: int
    inlier_ratio: float
    native_homography: NDArray[np.float64]
    p95_reprojection_error: float


class VerifiedPageRegistrar:
    """Register a page to a reviewed nine-board page profile.

    ``load_anchor_rgb`` is intentionally injected.  It keeps the pure image
    algorithm free from artifact-store details and lets tests use real photos
    without a database or a worker process.
    """

    def __init__(
        self,
        profile: Mapping[str, object] | None,
        *,
        load_anchor_rgb: Callable[[str], NDArray[np.uint8]],
        thresholds: PageRegistrationThresholds = DEFAULT_PAGE_REGISTRATION_THRESHOLDS,
    ) -> None:
        self._thresholds = thresholds
        self._load_anchor_rgb = load_anchor_rgb
        self._profile = profile
        self._anchors_by_feature_count: dict[int, tuple[_Anchor, ...]] = {}
        self._anchors_by_feature_count[_ORB_FEATURE_COUNTS[0]] = _anchors_from_profile(
            profile,
            load_anchor_rgb,
            minimum_inliers=thresholds.minimum_inliers,
            feature_count=_ORB_FEATURE_COUNTS[0],
        )

    @property
    def available(self) -> bool:
        return bool(self._anchors_by_feature_count[_ORB_FEATURE_COUNTS[0]])

    def register(self, target_rgb: NDArray[np.uint8]) -> RegisteredPageGeometry | None:
        if not self.available or not _valid_rgb(target_rgb):
            return None
        target_half = _half_gray(target_rgb)
        mask = _red_mask(target_rgb)
        for feature_count in _ORB_FEATURE_COUNTS:
            registered = self._register_with_feature_count(
                target_half,
                target_rgb=target_rgb,
                red_mask=mask,
                feature_count=feature_count,
            )
            if registered is not None:
                return registered
        return None

    def initialize(
        self,
        target_rgb: NDArray[np.uint8],
        *,
        active_board_slots: Sequence[int],
    ) -> PageRegistrationInitialization | None:
        """Project only the attested row-major prefix from the best anchor.

        Unlike :meth:`register`, this method does not snap to red borders and
        does not claim final page validity. Local, per-board verification is a
        separate structured-geometry stage.
        """

        slots = tuple(active_board_slots)
        if not self.available or not _valid_rgb(target_rgb) or slots != tuple(range(len(slots))):
            return None
        target_half = _half_gray(target_rgb)
        for feature_count in _ORB_FEATURE_COUNTS:
            for candidate in self._matched_candidates(
                target_half,
                feature_count=feature_count,
            ):
                quads = tuple(
                    _transform_quad(candidate.anchor.quads[position], candidate.native_homography)
                    for position in slots
                )
                if not is_ordered_active_grid(
                    quads,
                    slots,
                    target_rgb.shape[1],
                    target_rgb.shape[0],
                ):
                    continue
                return PageRegistrationInitialization(
                    anchor_source_checksum_sha256=candidate.anchor.source_checksum_sha256,
                    active_board_slots=slots,
                    initialization_quads=quads,
                    native_homography=_homography_payload(candidate.native_homography),
                    inlier_count=candidate.inlier_count,
                    inlier_ratio=candidate.inlier_ratio,
                    p95_reprojection_error=candidate.p95_reprojection_error,
                    feature_count=feature_count,
                )
        return None

    def _register_with_feature_count(
        self,
        target_half: NDArray[np.uint8],
        *,
        target_rgb: NDArray[np.uint8],
        red_mask: NDArray[np.uint8],
        feature_count: int,
    ) -> RegisteredPageGeometry | None:
        for candidate in self._matched_candidates(target_half, feature_count=feature_count):
            registered = _finalize_registration(
                candidate,
                target_rgb=target_rgb,
                red_mask=red_mask,
                thresholds=self._thresholds,
                feature_count=feature_count,
            )
            if registered is not None:
                return registered
        return None

    def _matched_candidates(
        self,
        target_half: NDArray[np.uint8],
        *,
        feature_count: int,
    ) -> tuple[_MatchedAnchor, ...]:
        anchors = self._anchors_for(feature_count)
        if not anchors:
            return ()
        target_points, target_descriptors = _orb_features(target_half, feature_count=feature_count)
        if target_descriptors is None or len(target_points) < self._thresholds.minimum_inliers:
            return ()
        candidates = tuple(
            matched
            for anchor in anchors
            if (
                matched := _match_anchor(
                    anchor,
                    target_points=target_points,
                    target_descriptors=target_descriptors,
                    thresholds=self._thresholds,
                )
            )
            is not None
        )
        return tuple(
            sorted(
                candidates,
                key=lambda value: (
                    -value.inlier_count,
                    -value.inlier_ratio,
                    value.p95_reprojection_error,
                    value.anchor.source_checksum_sha256,
                ),
            )
        )

    def _anchors_for(self, feature_count: int) -> tuple[_Anchor, ...]:
        existing = self._anchors_by_feature_count.get(feature_count)
        if existing is not None:
            return existing
        anchors = _anchors_from_profile(
            self._profile,
            self._load_anchor_rgb,
            minimum_inliers=self._thresholds.minimum_inliers,
            feature_count=feature_count,
        )
        self._anchors_by_feature_count[feature_count] = anchors
        return anchors


def build_verified_page_registration_profile(
    geometry_manifest: Mapping[str, object],
    *,
    anchor_source_checksums: Sequence[str] | None = None,
) -> dict[str, object]:
    """Extract complete, independently reviewed 3 x 3 pages as anchors.

    The result contains no image bytes and is safe to pin in a job payload.
    It is deliberately a separate profile from the legacy normalized-offset
    calibration policy: a page is registered with its own homography.
    """

    raw_samples = geometry_manifest.get("samples")
    if not isinstance(raw_samples, list):
        return {
            "schemaVersion": 1,
            "policy": PAGE_REGISTRATION_VERSION,
            "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
            "anchors": [],
        }
    by_source: dict[str, list[Mapping[str, object]]] = {}
    for raw in raw_samples:
        if not isinstance(raw, Mapping):
            continue
        checksum = raw.get("sourceChecksumSha256")
        position = raw.get("positionIndex")
        if isinstance(checksum, str) and isinstance(position, int) and 0 <= position < 9:
            by_source.setdefault(checksum, []).append(raw)
    anchors_by_checksum: dict[str, dict[str, object]] = {}
    for checksum, samples in sorted(by_source.items()):
        by_position: dict[int, Mapping[str, object]] = {}
        for sample in samples:
            position = sample.get("positionIndex")
            if isinstance(position, int):
                by_position[position] = sample
        if sorted(by_position.keys()) != list(range(9)):
            continue
        first = by_position[0]
        width = first.get("imageWidth")
        height = first.get("imageHeight")
        if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
            continue
        quads = [_payload_quad(by_position[position].get("finalQuad")) for position in range(9)]
        if any(quad is None for quad in quads):
            continue
        anchors_by_checksum[checksum] = {
            "sourceChecksumSha256": checksum,
            "imageWidth": width,
            "imageHeight": height,
            "quads": [
                [{"x": point.x, "y": point.y} for point in cast(Quad, quad)] for quad in quads
            ],
        }
    if anchor_source_checksums is None:
        # Historical schema-v1 profiles selected the first seven complete
        # sources by checksum. Preserve that exact replay behavior.
        anchors = [anchors_by_checksum[key] for key in sorted(anchors_by_checksum)[:7]]
        schema_version = 1
        selection_policy = "checksum-first-seven-v1"
    else:
        # New profiles pin their bounded, source-disjoint and geometry-diverse
        # anchor order in the immutable calibration payload.
        anchors = [
            anchors_by_checksum[key]
            for key in anchor_source_checksums
            if key in anchors_by_checksum
        ]
        schema_version = 2
        selection_policy = "geometry-medoid-farthest-point-16-v1"
    return {
        "schemaVersion": schema_version,
        "policy": PAGE_REGISTRATION_VERSION,
        "featuresVersion": PAGE_REGISTRATION_FEATURES_VERSION,
        "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
        "anchorSelectionPolicy": selection_policy,
        "cornerCountPerAnchor": 36,
        "anchors": anchors,
    }


def _anchors_from_profile(
    profile: Mapping[str, object] | None,
    load_anchor_rgb: Callable[[str], NDArray[np.uint8]],
    *,
    minimum_inliers: int,
    feature_count: int,
) -> tuple[_Anchor, ...]:
    if not isinstance(profile, Mapping) or profile.get("policy") != PAGE_REGISTRATION_VERSION:
        return ()
    raw_anchors = profile.get("anchors")
    if not isinstance(raw_anchors, Sequence) or isinstance(raw_anchors, str | bytes):
        return ()
    anchors: list[_Anchor] = []
    for raw in raw_anchors:
        if not isinstance(raw, Mapping):
            continue
        checksum = raw.get("sourceChecksumSha256")
        raw_quads = raw.get("quads")
        if not isinstance(checksum, str) or not isinstance(raw_quads, Sequence):
            continue
        quads = tuple(_payload_quad(value) for value in raw_quads)
        if len(quads) != 9 or any(quad is None for quad in quads):
            continue
        try:
            image = load_anchor_rgb(checksum)
        except (OSError, ValueError):
            continue
        if not _valid_rgb(image):
            continue
        points, descriptors = _orb_features(_half_gray(image), feature_count=feature_count)
        if descriptors is None or len(points) < minimum_inliers:
            continue
        anchors.append(
            _Anchor(
                checksum,
                descriptors,
                points,
                cast(tuple[Quad, ...], quads),
            )
        )
    return tuple(anchors)


def _match_anchor(
    anchor: _Anchor,
    *,
    target_points: Sequence[cv2.KeyPoint],
    target_descriptors: NDArray[np.uint8],
    thresholds: PageRegistrationThresholds,
) -> _MatchedAnchor | None:
    matches = _ratio_matches(anchor.feature_descriptors, target_descriptors)
    if len(matches) < thresholds.minimum_inliers:
        return None
    source_points = cast(
        NDArray[np.float32],
        np.asarray(
            [anchor.feature_points[match.queryIdx].pt for match in matches], dtype=np.float32
        ),
    )
    destination_points = cast(
        NDArray[np.float32],
        np.asarray([target_points[match.trainIdx].pt for match in matches], dtype=np.float32),
    )
    homography, inlier_mask = cv2.findHomography(
        source_points,
        destination_points,
        cv2.RANSAC,
        2.0,
    )
    if homography is None or inlier_mask is None or not np.isfinite(homography).all():
        return None
    typed_homography = cast(NDArray[np.float64], homography)
    inliers = cast(NDArray[np.bool_], inlier_mask.reshape(-1).astype(bool))
    inlier_count = int(inliers.sum())
    inlier_ratio = inlier_count / len(matches)
    if inlier_count < thresholds.minimum_inliers or inlier_ratio < thresholds.minimum_inlier_ratio:
        return None
    projected = cast(
        NDArray[np.float32],
        cv2.perspectiveTransform(source_points.reshape(-1, 1, 2), typed_homography).reshape(-1, 2),
    )
    errors = np.linalg.norm(projected[inliers] - destination_points[inliers], axis=1)
    p95 = float(np.percentile(errors, 95)) if len(errors) else float("inf")
    if p95 > thresholds.maximum_p95_reprojection_error:
        return None
    # Features were extracted at half resolution.  Convert the homography to
    # native source coordinates before applying it to reviewed native quads.
    scale_anchor = np.array([[0.5, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 1.0]])
    scale_target_inverse = np.array([[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]])
    native_homography = cast(
        NDArray[np.float64],
        scale_target_inverse @ typed_homography @ scale_anchor,
    )
    return _MatchedAnchor(
        anchor=anchor,
        inlier_count=inlier_count,
        inlier_ratio=inlier_ratio,
        native_homography=native_homography,
        p95_reprojection_error=p95,
    )


def _finalize_registration(
    match: _MatchedAnchor,
    *,
    target_rgb: NDArray[np.uint8],
    red_mask: NDArray[np.uint8],
    thresholds: PageRegistrationThresholds,
    feature_count: int,
) -> RegisteredPageGeometry | None:
    # The former implementation inspected a 3 x 3 neighbourhood in Python
    # for every sampled edge point and every bounded snap candidate.  Dilating
    # once preserves that exact neighbourhood rule while leaving the actual
    # red-border sampling vectorised below.
    red_neighbourhood = cast(
        NDArray[np.uint8],
        cv2.dilate(red_mask, np.ones((3, 3), dtype=np.uint8)),
    )
    quads = tuple(
        _snap_quad_to_red_edges(
            red_neighbourhood,
            _transform_quad(quad, match.native_homography),
        )
        for quad in match.anchor.quads
    )
    if not is_complete_ordered_grid(quads, target_rgb.shape[1], target_rgb.shape[0]):
        return None
    coverage = tuple(_red_edge_coverage(red_neighbourhood, quad) for quad in quads)
    mean_coverage = sum(coverage) / len(coverage)
    if (
        mean_coverage < thresholds.minimum_mean_red_edge_coverage
        or min(coverage) < thresholds.minimum_board_red_edge_coverage
    ):
        return None
    return RegisteredPageGeometry(
        anchor_source_checksum_sha256=match.anchor.source_checksum_sha256,
        quads=quads,
        board_red_edge_coverages=coverage,
        inlier_count=match.inlier_count,
        inlier_ratio=match.inlier_ratio,
        p95_reprojection_error=match.p95_reprojection_error,
        mean_red_edge_coverage=mean_coverage,
        feature_count=feature_count,
    )


def _half_gray(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    half = cast(
        NDArray[np.uint8],
        cv2.resize(rgb, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
    )
    return cast(NDArray[np.uint8], cv2.cvtColor(half, cv2.COLOR_RGB2GRAY))


def _orb_features(
    image: NDArray[np.uint8],
    *,
    feature_count: int,
) -> tuple[Sequence[cv2.KeyPoint], NDArray[np.uint8] | None]:
    orb = cv2.ORB_create(nfeatures=feature_count, fastThreshold=7)  # type: ignore[attr-defined]
    return cast(
        tuple[Sequence[cv2.KeyPoint], NDArray[np.uint8] | None],
        orb.detectAndCompute(image, None),
    )


def _ratio_matches(first: NDArray[np.uint8], second: NDArray[np.uint8]) -> list[cv2.DMatch]:
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    pairs = matcher.knnMatch(first, second, k=2)
    return [
        pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.76 * pair[1].distance
    ]


def _transform_quad(quad: Quad, homography: NDArray[np.float64]) -> Quad:
    source = np.asarray([[[point.x, point.y] for point in quad]], dtype=np.float32)
    target = cv2.perspectiveTransform(source, homography)[0]
    return cast(
        Quad,
        tuple(Point(int(round(point[0])), int(round(point[1]))) for point in target),
    )


def _red_mask(rgb: NDArray[np.uint8]) -> NDArray[np.uint8]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    lower = cv2.inRange(
        hsv,
        np.asarray((0, 80, 50), dtype=np.uint8),
        np.asarray((18, 255, 255), dtype=np.uint8),
    )
    upper = cv2.inRange(
        hsv,
        np.asarray((165, 80, 50), dtype=np.uint8),
        np.asarray((179, 255, 255), dtype=np.uint8),
    )
    return cast(NDArray[np.uint8], cv2.bitwise_or(lower, upper))


def _snap_quad_to_red_edges(mask: NDArray[np.uint8], quad: Quad) -> Quad:
    """Only allow a bounded translational refinement around the registration."""

    width = max(point.x for point in quad) - min(point.x for point in quad)
    height = max(point.y for point in quad) - min(point.y for point in quad)
    radius = max(2, min(12, int(round(min(width, height) * 0.06))))
    best = quad
    best_score = _red_edge_coverage(mask, quad)
    for dy in range(-radius, radius + 1, max(1, radius // 3)):
        for dx in range(-radius, radius + 1, max(1, radius // 3)):
            candidate = cast(Quad, tuple(Point(point.x + dx, point.y + dy) for point in quad))
            score = _red_edge_coverage(mask, candidate)
            if score > best_score:
                best, best_score = candidate, score
    return best


def _red_edge_coverage(red_neighbourhood: NDArray[np.uint8], quad: Quad) -> float:
    """Measure red-border evidence at the established sampled edge points.

    ``red_neighbourhood`` is the original red mask dilated by one pixel.  It is
    therefore equivalent to the old 3 x 3 patch test, but NumPy resolves every
    edge in a vectorised indexed read instead of entering Python once per
    sample.  This is important because bounded snapping evaluates up to 49
    nearby translations for each of nine cells.
    """

    height, width = red_neighbourhood.shape[:2]
    observed: list[NDArray[np.bool_]] = []
    sample_count = 0
    for first, second in zip(quad, (*quad[1:], quad[0]), strict=True):
        distance = max(abs(second.x - first.x), abs(second.y - first.y), 1)
        fractions = np.linspace(0.0, 1.0, num=max(12, distance // 3))
        xs = np.rint(first.x + (second.x - first.x) * fractions).astype(np.intp)
        ys = np.rint(first.y + (second.y - first.y) * fractions).astype(np.intp)
        valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        sample_count += len(xs)
        if valid.any():
            observed.append(red_neighbourhood[ys[valid], xs[valid]] > 0)
        missing = len(xs) - int(valid.sum())
        if missing:
            observed.append(np.zeros(missing, dtype=bool))
    if not observed or sample_count == 0:
        return 0.0
    return float(np.concatenate(observed).mean())


def is_complete_ordered_grid(quads: Sequence[Quad], width: int, height: int) -> bool:
    if len(quads) != 9:
        return False
    centres: list[tuple[float, float]] = []
    for quad in quads:
        points = np.asarray([[point.x, point.y] for point in quad], dtype=np.float32)
        if not cv2.isContourConvex(points) or abs(cv2.contourArea(points)) < 25.0:
            return False
        if (
            np.any(points[:, 0] < 0)
            or np.any(points[:, 0] >= width)
            or np.any(points[:, 1] < 0)
            or np.any(points[:, 1] >= height)
        ):
            return False
        centres.append((float(points[:, 0].mean()), float(points[:, 1].mean())))
    for row in range(3):
        if not centres[row * 3][0] < centres[row * 3 + 1][0] < centres[row * 3 + 2][0]:
            return False
    for column in range(3):
        if not centres[column][1] < centres[column + 3][1] < centres[column + 6][1]:
            return False
    polygons = [
        np.asarray([[point.x, point.y] for point in quad], dtype=np.float32) for quad in quads
    ]
    for first in range(9):
        for second in range(first + 1, 9):
            intersection, _ = cv2.intersectConvexConvex(polygons[first], polygons[second])
            if intersection > 2.0:
                return False
    return True


def is_ordered_active_grid(
    quads: Sequence[Quad],
    active_board_slots: Sequence[int],
    width: int,
    height: int,
) -> bool:
    """Validate only an attested prefix without inventing inactive boards."""

    slots = tuple(active_board_slots)
    if not slots or slots != tuple(range(len(slots))) or len(quads) != len(slots):
        return False
    centres: dict[int, tuple[float, float]] = {}
    polygons: list[NDArray[np.float32]] = []
    for slot, quad in zip(slots, quads, strict=True):
        points = np.asarray([[point.x, point.y] for point in quad], dtype=np.float32)
        if not cv2.isContourConvex(points) or abs(cv2.contourArea(points)) < 25.0:
            return False
        if (
            np.any(points[:, 0] < 0)
            or np.any(points[:, 0] >= width)
            or np.any(points[:, 1] < 0)
            or np.any(points[:, 1] >= height)
        ):
            return False
        centres[slot] = (float(points[:, 0].mean()), float(points[:, 1].mean()))
        polygons.append(points)
    for slot in slots:
        row, column = divmod(slot, 3)
        left = row * 3 + column - 1
        above = (row - 1) * 3 + column
        if column > 0 and left in centres and centres[left][0] >= centres[slot][0]:
            return False
        if row > 0 and above in centres and centres[above][1] >= centres[slot][1]:
            return False
    for first in range(len(polygons)):
        for second in range(first + 1, len(polygons)):
            intersection, _ = cv2.intersectConvexConvex(polygons[first], polygons[second])
            if intersection > 2.0:
                return False
    return True


def _homography_payload(
    homography: NDArray[np.float64],
) -> tuple[tuple[float, float, float], ...]:
    normalized = homography / homography[2, 2]
    rows = tuple(tuple(round(float(value), 12) for value in row) for row in normalized)
    return cast(tuple[tuple[float, float, float], ...], rows)


def _payload_quad(value: object) -> Quad | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return None
    points: list[Point] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            return None
        x, y = raw.get("x"), raw.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            return None
        points.append(Point(int(round(x)), int(round(y))))
    return cast(Quad, tuple(points))


def _valid_rgb(value: object) -> bool:
    return (
        isinstance(value, np.ndarray)
        and value.ndim == 3
        and value.shape[2] == 3
        and value.dtype == np.uint8
    )


__all__ = [
    "DEFAULT_PAGE_REGISTRATION_THRESHOLDS",
    "PAGE_REGISTRATION_FEATURES_VERSION",
    "PAGE_REGISTRATION_THRESHOLDS_VERSION",
    "PAGE_REGISTRATION_VERSION",
    "PageRegistrationThresholds",
    "PageRegistrationInitialization",
    "RegisteredPageGeometry",
    "VerifiedPageRegistrar",
    "build_verified_page_registration_profile",
    "is_complete_ordered_grid",
    "is_ordered_active_grid",
]
