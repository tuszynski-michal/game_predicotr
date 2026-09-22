"""Opt-in V1.2 page geometry based on local frame contrast, not frame colour.

The module deliberately reuses only ``VerifiedPageRegistrar.initialize`` for
same-game ORB alignment.  ``initialize`` projects reviewed board-frame anchors
but never runs the legacy red-edge snap or red-coverage acceptance checks.
Every projected frame is then independently tested against contrast visible in
the target photo, and the learned inner-grid margins merely bound the later
symbol-lattice search.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .board_cell_geometry_estimator import estimate_board_cell_geometry
from .geometry import Point, Quad
from .page_geometry_registration import VerifiedPageRegistrar, is_ordered_active_grid

CONTRAST_FRAME_GRID_V12_VARIANT = "contrast_frame_grid_v1_2"
CONTRAST_FRAME_GRID_V12_PROFILE_SCHEMA = "contrast-frame-grid-profile-v1"
CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION = "contrast-frame-grid-v1.2"
CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION = "local-frame-contrast-v1"
_RECTIFIED_WIDTH = 480
_RECTIFIED_HEIGHT = 300
_FRAME_SHIFT_RATIO = 0.12
_FRAME_SAMPLE_PADDING_RATIO = 0.12
_MINIMUM_EDGE_CONTRAST = 8.0
_MINIMUM_EDGE_PEAK_RATIO = 1.08
_MINIMUM_EDGE_SEPARATION = 8
_MAXIMUM_COMPETING_EDGE_RATIO = 0.95
_GRID_ANALYSIS_PADDING = 0.08


class ContrastFrameGridV12Error(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FrameGridSample:
    source_checksum_sha256: str
    image_width: int
    image_height: int
    board_frame_quads: tuple[Quad, ...]
    symbol_grid_quads: tuple[Quad, ...]
    override_id: str
    revision: int
    decision_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class ContrastFrameGridV12Profile:
    samples: tuple[FrameGridSample, ...]
    checksum_sha256: str

    @property
    def available(self) -> bool:
        return bool(self.samples)

    def to_payload(self, *, include_checksum: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "algorithmVersion": CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION,
            "sampleCount": sum(len(sample.board_frame_quads) for sample in self.samples),
            "sampleSourceCount": len(self.samples),
            "samples": [_sample_to_payload(sample) for sample in self.samples],
            "schemaVersion": CONTRAST_FRAME_GRID_V12_PROFILE_SCHEMA,
            "thresholdsVersion": CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION,
            "variant": CONTRAST_FRAME_GRID_V12_VARIANT,
        }
        if include_checksum:
            payload["checksumSha256"] = self.checksum_sha256
        return payload

    @classmethod
    def from_payload(cls, value: object) -> ContrastFrameGridV12Profile:
        if not isinstance(value, Mapping):
            raise ContrastFrameGridV12Error(
                "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID",
                "The V1.2 contrast-frame profile is invalid.",
            )
        if (
            value.get("schemaVersion") != CONTRAST_FRAME_GRID_V12_PROFILE_SCHEMA
            or value.get("variant") != CONTRAST_FRAME_GRID_V12_VARIANT
            or value.get("algorithmVersion") != CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION
            or value.get("thresholdsVersion") != CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION
        ):
            raise ContrastFrameGridV12Error(
                "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID",
                "The V1.2 profile version is unsupported.",
            )
        raw_samples = value.get("samples")
        if not isinstance(raw_samples, Sequence) or isinstance(raw_samples, str | bytes):
            raise ContrastFrameGridV12Error(
                "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID",
                "The V1.2 profile samples are invalid.",
            )
        samples = tuple(_parse_sample(sample) for sample in raw_samples)
        expected = _profile_payload(samples)
        expected_checksum = _checksum(expected)
        if (
            value.get("sampleSourceCount") != len(samples)
            or value.get("sampleCount") != sum(len(sample.board_frame_quads) for sample in samples)
            or value.get("checksumSha256") != expected_checksum
            or set(value) != set({*expected, "checksumSha256"})
        ):
            raise ContrastFrameGridV12Error(
                "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID",
                "The V1.2 profile checksum or fields are invalid.",
            )
        return cls(samples=samples, checksum_sha256=expected_checksum)

    def registration_profile(self) -> dict[str, object]:
        """Return only manually confirmed frame anchors for ORB initialization."""

        return {
            "schemaVersion": 1,
            "policy": "verified-page-registration-v1",
            "thresholdsVersion": "verified-page-registration-thresholds-v1",
            "anchors": [
                {
                    "sourceChecksumSha256": sample.source_checksum_sha256,
                    "imageWidth": sample.image_width,
                    "imageHeight": sample.image_height,
                    "quads": [
                        [{"x": point.x, "y": point.y} for point in quad]
                        for quad in sample.board_frame_quads
                    ],
                    "provenance": "manual-v12-board-frame-grid-pair",
                }
                for sample in self.samples
            ],
        }

    def margins(self) -> tuple[float, float, float, float]:
        values = [margin for sample in self.samples for margin in _sample_margins(sample)]
        if not values:
            raise ContrastFrameGridV12Error(
                "IMAGE_CONTRAST_FRAME_GRID_PROFILE_REQUIRED",
                "V1.2 needs at least one complete manually confirmed frame and grid pair.",
            )
        return tuple(float(statistics.median(item[index] for item in values)) for index in range(4))


def build_contrast_frame_grid_v12_profile(overrides: Mapping[str, object]) -> dict[str, object]:
    """Create one immutable per-game snapshot from complete manual pair revisions.

    Legacy single-quadrilateral corrections do not become samples.  The caller
    supplies only one game's current override snapshot, so the result cannot
    cross game boundaries.
    """

    samples: list[FrameGridSample] = []
    for checksum, raw in sorted(overrides.items()):
        if not isinstance(checksum, str) or not isinstance(raw, Mapping):
            continue
        try:
            sample = _parse_sample({"sourceChecksumSha256": checksum, **raw})
        except ContrastFrameGridV12Error:
            continue
        samples.append(sample)
    payload = _profile_payload(tuple(samples))
    payload["checksumSha256"] = _checksum(payload)
    return payload


@dataclass(frozen=True, slots=True)
class ContrastFrameGridV12Result:
    anchor_source_checksum_sha256: str
    board_frame_quads: tuple[Quad, ...]
    symbol_grid_quads: tuple[Quad, ...]
    board_contrast_scores: tuple[float, ...]
    initialization_inlier_count: int
    initialization_inlier_ratio: float
    initialization_p95_reprojection_error: float
    profile_checksum_sha256: str

    def to_payload(self) -> dict[str, object]:
        return {
            "anchorSourceChecksumSha256": self.anchor_source_checksum_sha256,
            "boardContrastScores": [round(value, 6) for value in self.board_contrast_scores],
            "boardFrameQuads": [_quad_to_payload(quad) for quad in self.board_frame_quads],
            "featureCount": self.initialization_inlier_count,
            "inlierCount": self.initialization_inlier_count,
            "inlierRatio": round(self.initialization_inlier_ratio, 6),
            "meanFrameContrast": round(statistics.fmean(self.board_contrast_scores), 6),
            "p95ReprojectionError": round(self.initialization_p95_reprojection_error, 6),
            "profileChecksumSha256": self.profile_checksum_sha256,
            "quads": [_quad_to_payload(quad) for quad in self.board_frame_quads],
            "registrationVersion": CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION,
            "symbolGridQuads": [_quad_to_payload(quad) for quad in self.symbol_grid_quads],
            "thresholdsVersion": CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION,
        }


@dataclass(frozen=True, slots=True)
class ContrastFrameGridV12Evaluation:
    result: ContrastFrameGridV12Result | None
    reason_code: str | None = None

    def failure_payload(self) -> dict[str, object]:
        return {
            "reasonCode": self.reason_code or "PAGE_GEOMETRY_CONTRAST_FRAME_UNAVAILABLE",
            "contrastFrameGridV12": {
                "profileRequired": self.reason_code == "IMAGE_CONTRAST_FRAME_GRID_PROFILE_REQUIRED",
                "registrationVersion": CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION,
                "thresholdsVersion": CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION,
            },
        }


class ContrastFrameGridV12Registrar:
    """Same-game anchor registration plus target-local contrast and grid checks."""

    def __init__(
        self,
        profile: ContrastFrameGridV12Profile,
        *,
        load_anchor_rgb: Callable[[str], NDArray[np.uint8]],
    ) -> None:
        self._profile = profile
        self._registrar = VerifiedPageRegistrar(
            profile.registration_profile(), load_anchor_rgb=load_anchor_rgb
        )

    @property
    def available(self) -> bool:
        return self._profile.available and self._registrar.available

    def prepare(self) -> None:
        self._registrar.prepare()

    def evaluate(
        self, target_rgb: NDArray[np.uint8], *, active_board_slots: Sequence[int]
    ) -> ContrastFrameGridV12Evaluation:
        slots = tuple(active_board_slots)
        if not self._profile.available:
            return ContrastFrameGridV12Evaluation(
                None, "IMAGE_CONTRAST_FRAME_GRID_PROFILE_REQUIRED"
            )
        if slots != tuple(range(9)):
            return ContrastFrameGridV12Evaluation(
                None, "IMAGE_CONTRAST_FRAME_GRID_TOPOLOGY_UNSUPPORTED"
            )
        initialization = self._registrar.initialize(target_rgb, active_board_slots=slots)
        if initialization is None:
            return ContrastFrameGridV12Evaluation(
                None, "PAGE_GEOMETRY_CONTRAST_FRAME_ANCHOR_UNAVAILABLE"
            )
        frames: list[Quad] = []
        scores: list[float] = []
        for projected in initialization.initialization_quads:
            refined = _refine_frame_by_local_contrast(target_rgb, projected)
            if refined is None:
                return ContrastFrameGridV12Evaluation(
                    None, "PAGE_GEOMETRY_CONTRAST_FRAME_AMBIGUOUS"
                )
            frame, score = refined
            frames.append(frame)
            scores.append(score)
        if not is_ordered_active_grid(
            tuple(frames), slots, target_rgb.shape[1], target_rgb.shape[0]
        ):
            return ContrastFrameGridV12Evaluation(
                None, "PAGE_GEOMETRY_CONTRAST_FRAME_GRID_INCONSISTENT"
            )
        margins = self._profile.margins()
        symbol_grids: list[Quad] = []
        for frame in frames:
            analysis_quad = _expanded_grid_hint(frame, margins)
            estimate = estimate_board_cell_geometry(target_rgb, analysis_quad)
            if estimate.status != "estimated" or estimate.lattice_bounds_quad is None:
                return ContrastFrameGridV12Evaluation(
                    None, "PAGE_GEOMETRY_CONTRAST_FRAME_SYMBOL_GRID_UNSAFE"
                )
            lattice_quad = _lattice_quad_to_page_quad(estimate.lattice_bounds_quad)
            if not _quad_contains_float(frame, lattice_quad):
                return ContrastFrameGridV12Evaluation(
                    None, "PAGE_GEOMETRY_CONTRAST_FRAME_SYMBOL_GRID_OUTSIDE_FRAME"
                )
            symbol_grids.append(lattice_quad)
        return ContrastFrameGridV12Evaluation(
            ContrastFrameGridV12Result(
                anchor_source_checksum_sha256=initialization.anchor_source_checksum_sha256,
                board_frame_quads=tuple(frames),
                symbol_grid_quads=tuple(symbol_grids),
                board_contrast_scores=tuple(scores),
                initialization_inlier_count=initialization.inlier_count,
                initialization_inlier_ratio=initialization.inlier_ratio,
                initialization_p95_reprojection_error=initialization.p95_reprojection_error,
                profile_checksum_sha256=self._profile.checksum_sha256,
            )
        )


def _profile_payload(samples: tuple[FrameGridSample, ...]) -> dict[str, object]:
    return {
        "algorithmVersion": CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION,
        "sampleCount": sum(len(sample.board_frame_quads) for sample in samples),
        "sampleSourceCount": len(samples),
        "samples": [_sample_to_payload(sample) for sample in samples],
        "schemaVersion": CONTRAST_FRAME_GRID_V12_PROFILE_SCHEMA,
        "thresholdsVersion": CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION,
        "variant": CONTRAST_FRAME_GRID_V12_VARIANT,
    }


def _checksum(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _sample_to_payload(sample: FrameGridSample) -> dict[str, object]:
    return {
        "boardFrameQuads": [_quad_to_payload(quad) for quad in sample.board_frame_quads],
        "decisionChecksumSha256": sample.decision_checksum_sha256,
        "imageHeight": sample.image_height,
        "imageWidth": sample.image_width,
        "overrideId": sample.override_id,
        "revision": sample.revision,
        "sourceChecksumSha256": sample.source_checksum_sha256,
        "symbolGridQuads": [_quad_to_payload(quad) for quad in sample.symbol_grid_quads],
    }


def _quad_to_payload(quad: Quad) -> list[dict[str, int]]:
    return [{"x": point.x, "y": point.y} for point in quad]


def _lattice_quad_to_page_quad(
    quad: Sequence[tuple[float, float]],
) -> Quad:
    """Convert the estimator's float tuples into the page editor's Points.

    ``typing.cast`` would only silence the type checker here; it would leave
    the tuple values in place and make both containment checks and manifest
    serialization fail at runtime.
    """
    if len(quad) != 4:
        raise ContrastFrameGridV12Error(
            "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID",
            "The symbol-grid estimator returned an invalid quadrilateral.",
        )
    return cast(
        Quad,
        tuple(Point(int(round(x)), int(round(y))) for x, y in quad),
    )


def _parse_sample(value: object) -> FrameGridSample:
    if not isinstance(value, Mapping):
        raise ContrastFrameGridV12Error(
            "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID", "Invalid sample."
        )
    checksum = value.get("sourceChecksumSha256")
    width = value.get("imageWidth")
    height = value.get("imageHeight")
    override_id = value.get("overrideId")
    revision = value.get("revision")
    decision_checksum = value.get("decisionChecksumSha256")
    frames = _parse_quads(value.get("boardFrameQuads"), width, height)
    grids = _parse_quads(value.get("symbolGridQuads"), width, height)
    if (
        not isinstance(checksum, str)
        or not _is_sha256(checksum)
        or not isinstance(width, int)
        or isinstance(width, bool)
        or width < 1
        or not isinstance(height, int)
        or isinstance(height, bool)
        or height < 1
        or not isinstance(override_id, str)
        or not override_id
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(decision_checksum, str)
        or not _is_sha256(decision_checksum)
        or len(frames) != 9
        or len(grids) != 9
        or not is_ordered_active_grid(frames, tuple(range(9)), width, height)
        or not is_ordered_active_grid(grids, tuple(range(9)), width, height)
        or any(
            not _quad_contains_float(frame, grid) for frame, grid in zip(frames, grids, strict=True)
        )
    ):
        raise ContrastFrameGridV12Error(
            "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID", "Invalid V1.2 sample."
        )
    return FrameGridSample(
        source_checksum_sha256=checksum,
        image_width=width,
        image_height=height,
        board_frame_quads=frames,
        symbol_grid_quads=grids,
        override_id=override_id,
        revision=revision,
        decision_checksum_sha256=decision_checksum,
    )


def _parse_quads(value: object, width: object, height: object) -> tuple[Quad, ...]:
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or not isinstance(value, Sequence)
        or isinstance(value, str | bytes)
    ):
        return ()
    quads: list[Quad] = []
    for raw_quad in value:
        if (
            not isinstance(raw_quad, Sequence)
            or isinstance(raw_quad, str | bytes)
            or len(raw_quad) != 4
        ):
            return ()
        points: list[Point] = []
        for raw_point in raw_quad:
            if not isinstance(raw_point, Mapping):
                return ()
            x, y = raw_point.get("x"), raw_point.get("y")
            if (
                not isinstance(x, int)
                or isinstance(x, bool)
                or not isinstance(y, int)
                or isinstance(y, bool)
                or not 0 <= x < width
                or not 0 <= y < height
            ):
                return ()
            points.append(Point(x, y))
        quads.append(cast(Quad, tuple(points)))
    return tuple(quads)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sample_margins(sample: FrameGridSample) -> tuple[tuple[float, float, float, float], ...]:
    margins: list[tuple[float, float, float, float]] = []
    destination = np.asarray(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), dtype=np.float32)
    for frame, grid in zip(sample.board_frame_quads, sample.symbol_grid_quads, strict=True):
        transform = cv2.getPerspectiveTransform(_quad_array(frame), destination)
        projected = cv2.perspectiveTransform(_quad_array(grid)[None, :, :], transform)[0]
        left, top = float(np.min(projected[:, 0])), float(np.min(projected[:, 1]))
        right = 1.0 - float(np.max(projected[:, 0]))
        bottom = 1.0 - float(np.max(projected[:, 1]))
        if min(left, top, right, bottom) < -0.01 or max(left, top, right, bottom) > 0.8:
            raise ContrastFrameGridV12Error(
                "IMAGE_CONTRAST_FRAME_GRID_PROFILE_INVALID", "The V1.2 grid margins are invalid."
            )
        margins.append((left, top, right, bottom))
    return tuple(margins)


def _refine_frame_by_local_contrast(
    rgb: NDArray[np.uint8], initial_quad: Quad
) -> tuple[Quad, float] | None:
    """Snap four borders in rectified coordinates using target-local RGB contrast."""

    source = _quad_array(initial_quad)
    destination = np.asarray(
        (
            (0.0, 0.0),
            (float(_RECTIFIED_WIDTH - 1), 0.0),
            (float(_RECTIFIED_WIDTH - 1), float(_RECTIFIED_HEIGHT - 1)),
            (0.0, float(_RECTIFIED_HEIGHT - 1)),
        ),
        dtype=np.float32,
    )
    inverse = cv2.getPerspectiveTransform(destination, source)
    padded_destination = np.asarray(
        (
            (
                -_RECTIFIED_WIDTH * _FRAME_SAMPLE_PADDING_RATIO,
                -_RECTIFIED_HEIGHT * _FRAME_SAMPLE_PADDING_RATIO,
            ),
            (
                _RECTIFIED_WIDTH * (1 + _FRAME_SAMPLE_PADDING_RATIO),
                -_RECTIFIED_HEIGHT * _FRAME_SAMPLE_PADDING_RATIO,
            ),
            (
                _RECTIFIED_WIDTH * (1 + _FRAME_SAMPLE_PADDING_RATIO),
                _RECTIFIED_HEIGHT * (1 + _FRAME_SAMPLE_PADDING_RATIO),
            ),
            (
                -_RECTIFIED_WIDTH * _FRAME_SAMPLE_PADDING_RATIO,
                _RECTIFIED_HEIGHT * (1 + _FRAME_SAMPLE_PADDING_RATIO),
            ),
        ),
        dtype=np.float32,
    )
    padded_source = cv2.perspectiveTransform(padded_destination[None, :, :], inverse)[0]
    padded_rectified = np.asarray(
        (
            (0.0, 0.0),
            (float(_RECTIFIED_WIDTH - 1), 0.0),
            (float(_RECTIFIED_WIDTH - 1), float(_RECTIFIED_HEIGHT - 1)),
            (0.0, float(_RECTIFIED_HEIGHT - 1)),
        ),
        dtype=np.float32,
    )
    padded_transform = cv2.getPerspectiveTransform(padded_source, padded_rectified)
    padded_inverse = cv2.getPerspectiveTransform(padded_rectified, padded_source)
    rectified = cv2.warpPerspective(
        rgb, padded_transform, (_RECTIFIED_WIDTH, _RECTIFIED_HEIGHT), flags=cv2.INTER_LINEAR
    )
    pad_x = int(round(_RECTIFIED_WIDTH * _FRAME_SAMPLE_PADDING_RATIO))
    pad_y = int(round(_RECTIFIED_HEIGHT * _FRAME_SAMPLE_PADDING_RATIO))
    expected = (
        pad_x,
        pad_y,
        _RECTIFIED_WIDTH - pad_x - 1,
        _RECTIFIED_HEIGHT - pad_y - 1,
    )
    maximum_x_shift = max(3, int(round((expected[2] - expected[0]) * _FRAME_SHIFT_RATIO)))
    maximum_y_shift = max(3, int(round((expected[3] - expected[1]) * _FRAME_SHIFT_RATIO)))
    left = _best_vertical_edge(rectified, expected[0], maximum_x_shift)
    right = _best_vertical_edge(rectified, expected[2], maximum_x_shift)
    top = _best_horizontal_edge(rectified, expected[1], maximum_y_shift)
    bottom = _best_horizontal_edge(rectified, expected[3], maximum_y_shift)
    if any(edge is None for edge in (left, right, top, bottom)):
        return None
    left_x, left_score = cast(tuple[int, float], left)
    right_x, right_score = cast(tuple[int, float], right)
    top_y, top_score = cast(tuple[int, float], top)
    bottom_y, bottom_score = cast(tuple[int, float], bottom)
    if right_x - left_x < _RECTIFIED_WIDTH * 0.35 or bottom_y - top_y < _RECTIFIED_HEIGHT * 0.35:
        return None
    refined_rectified = np.asarray(
        ((left_x, top_y), (right_x, top_y), (right_x, bottom_y), (left_x, bottom_y)),
        dtype=np.float32,
    )
    source_quad = cv2.perspectiveTransform(refined_rectified[None, :, :], padded_inverse)[0]
    height, width = rgb.shape[:2]
    if (
        not np.isfinite(source_quad).all()
        or np.any(source_quad[:, 0] < 0)
        or np.any(source_quad[:, 1] < 0)
        or np.any(source_quad[:, 0] >= width)
        or np.any(source_quad[:, 1] >= height)
    ):
        return None
    return (
        cast(Quad, tuple(Point(int(round(x)), int(round(y))) for x, y in source_quad)),
        float(statistics.fmean((left_score, right_score, top_score, bottom_score))),
    )


def _best_vertical_edge(
    rgb: NDArray[np.uint8], expected: int, maximum_shift: int
) -> tuple[int, float] | None:
    candidates = _edge_candidates(expected, maximum_shift, rgb.shape[1], vertical=True)
    scores = [(candidate, _vertical_contrast(rgb, candidate)) for candidate in candidates]
    return _select_edge(scores)


def _best_horizontal_edge(
    rgb: NDArray[np.uint8], expected: int, maximum_shift: int
) -> tuple[int, float] | None:
    candidates = _edge_candidates(expected, maximum_shift, rgb.shape[0], vertical=False)
    scores = [(candidate, _horizontal_contrast(rgb, candidate)) for candidate in candidates]
    return _select_edge(scores)


def _edge_candidates(expected: int, maximum_shift: int, limit: int, *, vertical: bool) -> range:
    _ = vertical
    lower = max(3, expected - maximum_shift)
    upper = min(limit - 4, expected + maximum_shift)
    return range(lower, upper + 1)


def _vertical_contrast(rgb: NDArray[np.uint8], x: int) -> float:
    start = max(0, int(rgb.shape[0] * 0.15))
    end = max(start + 1, int(rgb.shape[0] * 0.85))
    left = rgb[start:end, x - 3 : x].astype(np.float32).mean(axis=1)
    right = rgb[start:end, x + 1 : x + 4].astype(np.float32).mean(axis=1)
    return float(np.median(np.linalg.norm(right - left, axis=1)))


def _horizontal_contrast(rgb: NDArray[np.uint8], y: int) -> float:
    start = max(0, int(rgb.shape[1] * 0.15))
    end = max(start + 1, int(rgb.shape[1] * 0.85))
    top = rgb[y - 3 : y, start:end].astype(np.float32).mean(axis=0)
    bottom = rgb[y + 1 : y + 4, start:end].astype(np.float32).mean(axis=0)
    return float(np.median(np.linalg.norm(bottom - top, axis=1)))


def _select_edge(scores: Sequence[tuple[int, float]]) -> tuple[int, float] | None:
    if not scores:
        return None
    position, score = max(scores, key=lambda item: (item[1], -abs(item[0])))
    baseline = max(1e-6, float(np.median([value for _, value in scores])))
    if score < _MINIMUM_EDGE_CONTRAST or score / baseline < _MINIMUM_EDGE_PEAK_RATIO:
        return None
    # A broad peak around one physical edge is acceptable.  Two spatially
    # separated peaks of similar strength mean that this image does not say
    # which transition is the board frame, so it must remain manual.
    if any(
        abs(candidate - position) >= _MINIMUM_EDGE_SEPARATION
        and candidate_score >= score * _MAXIMUM_COMPETING_EDGE_RATIO
        for candidate, candidate_score in scores
    ):
        return None
    return position, score


def _expanded_grid_hint(frame: Quad, margins: tuple[float, float, float, float]) -> Quad:
    left, top, right, bottom = margins
    padded = np.asarray(
        (
            (max(0.0, left - _GRID_ANALYSIS_PADDING), max(0.0, top - _GRID_ANALYSIS_PADDING)),
            (
                min(1.0, 1.0 - right + _GRID_ANALYSIS_PADDING),
                max(0.0, top - _GRID_ANALYSIS_PADDING),
            ),
            (
                min(1.0, 1.0 - right + _GRID_ANALYSIS_PADDING),
                min(1.0, 1.0 - bottom + _GRID_ANALYSIS_PADDING),
            ),
            (
                max(0.0, left - _GRID_ANALYSIS_PADDING),
                min(1.0, 1.0 - bottom + _GRID_ANALYSIS_PADDING),
            ),
        ),
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(
        np.asarray(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), dtype=np.float32),
        _quad_array(frame),
    )
    source = cv2.perspectiveTransform(padded[None, :, :], transform)[0]
    return cast(Quad, tuple(Point(int(round(x)), int(round(y))) for x, y in source))


def _quad_contains_float(outer: Quad, inner: Quad) -> bool:
    for point in inner:
        signs = []
        for index, start in enumerate(outer):
            end = outer[(index + 1) % len(outer)]
            signs.append(
                (end.x - start.x) * (point.y - start.y) - (end.y - start.y) * (point.x - start.x)
            )
        if not (all(value >= -1e-6 for value in signs) or all(value <= 1e-6 for value in signs)):
            return False
    return True


def _quad_array(quad: Quad) -> NDArray[np.float32]:
    return np.asarray([(point.x, point.y) for point in quad], dtype=np.float32)


__all__ = [
    "CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION",
    "CONTRAST_FRAME_GRID_V12_THRESHOLDS_VERSION",
    "CONTRAST_FRAME_GRID_V12_VARIANT",
    "ContrastFrameGridV12Error",
    "ContrastFrameGridV12Profile",
    "ContrastFrameGridV12Registrar",
    "build_contrast_frame_grid_v12_profile",
]
