"""Pure rules for lossless crops of managed originals (D-562).

A verified crop keeps every approved board and cell quad of a managed original
plus a margin. Coordinates stay in the original ``exif-normalized-rgb-pixels-v1``
space; the crop only records where it sits in that space. This module plans the
crop box, judges the decoded pixels and encodes the crop attestation. It does
not read files, run ``jpegtran`` or touch the database.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

import numpy as np
from numpy.typing import NDArray

SOURCE_CROP_POLICY_VERSION: Final = "source-crop-v1"
SOURCE_CROP_ATTESTATION_VERSION: Final = "source-crop-attestation-v1"
SOURCE_CROP_COORDINATE_SPACE: Final = "exif-normalized-rgb-pixels-v1"
DEFAULT_MARGIN_PX: Final = 50
EDGE_RING_PX: Final = 1
MIN_PROTECTED_DISTANCE_FROM_RING_PX: Final = 8
MIN_SAVING_FRACTION: Final = 0.05
CANVAS_FILL_VALUE: Final = 0
ORIGINALS_DIRECTORY: Final = "originals"
CROPPED_ORIGINALS_DIRECTORY: Final = "originals-cropped"

# EXIF orientations that are pure rotations; mirrored ones are rejected.
SUPPORTED_ORIENTATIONS: Final = frozenset({1, 3, 6, 8})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceCropError(ValueError):
    """Stable failure of a crop rule, before any file is written or trusted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PixelBox:
    """Half-open integer pixel box ``[left, right) × [top, bottom)``."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise SourceCropError("SOURCE_CROP_BOX_INVALID", "Pixel box edges must be integers.")
        if self.left < 0 or self.top < 0 or self.right <= self.left or self.bottom <= self.top:
            raise SourceCropError("SOURCE_CROP_BOX_INVALID", "Pixel box must be non-empty.")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def fits(self, width: int, height: int) -> bool:
        return self.right <= width and self.bottom <= height

    def contains(self, other: PixelBox) -> bool:
        return (
            self.left <= other.left
            and self.top <= other.top
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def as_list(self) -> list[int]:
        return [self.left, self.top, self.right, self.bottom]


@dataclass(frozen=True, slots=True)
class ProtectedBox:
    """Float bounding box of every protected quad point, before the margin."""

    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
            raise SourceCropError("SOURCE_CROP_POINT_INVALID", "Protected box must be numeric.")
        if not all(math.isfinite(value) for value in values):
            raise SourceCropError("SOURCE_CROP_POINT_INVALID", "Protected box must be finite.")
        if self.right < self.left or self.bottom < self.top:
            raise SourceCropError("SOURCE_CROP_POINT_INVALID", "Protected box is inverted.")
        # Always floats, so the canonical attestation bytes survive a round trip.
        for name in ("left", "top", "right", "bottom"):
            object.__setattr__(self, name, float(getattr(self, name)))

    def as_list(self) -> list[float]:
        return [self.left, self.top, self.right, self.bottom]


@dataclass(frozen=True, slots=True)
class SourceCropPlan:
    """Where a lossless crop sits, in oriented and stored-JPEG pixels."""

    protected_box: ProtectedBox
    margin_px: int
    imcu_width: int
    imcu_height: int
    raw_box: PixelBox
    oriented_box: PixelBox


PROTECTED_QUAD_KEYS: Final = frozenset(
    {
        "finalQuad",
        "sourceQuad",
        "symbolGridQuad",
        "latticeBoundsQuad",
        "boardFrameQuad",
        "paddedSourceQuad",
        "sequenceLabelQuad",
        "corners",
    }
)


def protected_points_from_geometry(document: object) -> list[tuple[float, float]]:
    """Every point of a protected quad in a stored geometry document.

    Board geometry, source revision entries, board revisions (``corners``,
    ``geometry``, ``virtual_render_spec``) and render manifests nest their quads
    differently, so the walk descends into every object and list and keeps the
    points of quads stored under ``PROTECTED_QUAD_KEYS`` (the P1 selection) or
    given as a bare list of four points. A malformed quad is an error rather
    than a silently smaller crop.
    """

    points: list[tuple[float, float]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in PROTECTED_QUAD_KEYS and value is not None:
                    points.extend(_quad_points(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            quad = _try_quad_points(node)
            if quad is not None:
                points.extend(quad)
            else:
                for item in node:
                    walk(item)

    walk(document)
    return points


def _try_quad_points(value: list[object]) -> list[tuple[float, float]] | None:
    if len(value) != 4:
        return None
    try:
        return _quad_points(value)
    except SourceCropError:
        return None


def _quad_points(value: object) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) != 4:
        raise SourceCropError("SOURCE_CROP_POINT_INVALID", "A protected quad needs four points.")
    result: list[tuple[float, float]] = []
    for point in value:
        if isinstance(point, dict) and set(point) >= {"x", "y"}:
            x, y = point["x"], point["y"]
        elif isinstance(point, list) and len(point) == 2:
            x, y = point
        else:
            raise SourceCropError(
                "SOURCE_CROP_POINT_INVALID", "A quad point must be {x, y} or [x, y]."
            )
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int | float)
            or not isinstance(y, int | float)
            or not math.isfinite(x)
            or not math.isfinite(y)
        ):
            raise SourceCropError(
                "SOURCE_CROP_POINT_INVALID", "Quad coordinates must be finite numbers."
            )
        result.append((float(x), float(y)))
    return result


def protected_box_from_points(points: Iterable[tuple[float, float]]) -> ProtectedBox:
    """Bound all protected quad points (board corners, cell and padded quads)."""

    xs: list[float] = []
    ys: list[float] = []
    for x, y in points:
        if not (math.isfinite(x) and math.isfinite(y)):
            raise SourceCropError("SOURCE_CROP_POINT_INVALID", "Protected points must be finite.")
        xs.append(float(x))
        ys.append(float(y))
    if not xs:
        raise SourceCropError(
            "SOURCE_CROP_NOTHING_PROTECTED", "A crop requires at least one protected quad."
        )
    return ProtectedBox(min(xs), min(ys), max(xs), max(ys))


def clamp_protected_box(protected: ProtectedBox, *, width: int, height: int) -> ProtectedBox:
    """Clip the protected box to the image; padded quads may reach past its border."""

    _require_dimensions(width, height)
    left = min(max(protected.left, 0.0), float(width))
    top = min(max(protected.top, 0.0), float(height))
    right = min(max(protected.right, 0.0), float(width))
    bottom = min(max(protected.bottom, 0.0), float(height))
    if right <= left or bottom <= top:
        raise SourceCropError(
            "SOURCE_CROP_OUTSIDE_IMAGE", "The protected quads lie outside the source image."
        )
    return ProtectedBox(left, top, right, bottom)


def margin_box(protected: ProtectedBox, *, margin_px: int, width: int, height: int) -> PixelBox:
    """Grow the protected box by the margin, round outward and clamp to the image."""

    if margin_px < 0:
        raise SourceCropError("SOURCE_CROP_MARGIN_INVALID", "The margin cannot be negative.")
    _require_dimensions(width, height)
    left = max(0, math.floor(protected.left - margin_px))
    top = max(0, math.floor(protected.top - margin_px))
    right = min(width, math.ceil(protected.right + margin_px))
    bottom = min(height, math.ceil(protected.bottom + margin_px))
    if right <= left or bottom <= top:
        raise SourceCropError(
            "SOURCE_CROP_OUTSIDE_IMAGE", "The protected quads lie outside the source image."
        )
    return PixelBox(left, top, right, bottom)


def raw_dimensions(
    oriented_width: int, oriented_height: int, orientation: int | None
) -> tuple[int, int]:
    """Stored-JPEG dimensions for oriented dimensions and an EXIF orientation."""

    resolved = _resolve_orientation(orientation)
    _require_dimensions(oriented_width, oriented_height)
    if resolved in (6, 8):
        return oriented_height, oriented_width
    return oriented_width, oriented_height


def oriented_to_raw_box(
    box: PixelBox, *, orientation: int | None, oriented_width: int, oriented_height: int
) -> PixelBox:
    """Map an oriented box to stored-JPEG pixels (``ImageOps.exif_transpose`` inverse)."""

    resolved = _resolve_orientation(orientation)
    _require_box_inside(box, oriented_width, oriented_height)
    left, top, right, bottom = box.left, box.top, box.right, box.bottom
    if resolved == 1:
        return box
    if resolved == 3:
        return PixelBox(
            oriented_width - right,
            oriented_height - bottom,
            oriented_width - left,
            oriented_height - top,
        )
    if resolved == 6:
        # Displayed = stored rotated 90° clockwise; stored height = oriented width.
        return PixelBox(top, oriented_width - right, bottom, oriented_width - left)
    # Orientation 8: displayed = stored rotated 90° counter-clockwise.
    return PixelBox(oriented_height - bottom, left, oriented_height - top, right)


def raw_to_oriented_box(
    box: PixelBox, *, orientation: int | None, raw_width: int, raw_height: int
) -> PixelBox:
    """Map a stored-JPEG box to oriented pixels (``ImageOps.exif_transpose``)."""

    resolved = _resolve_orientation(orientation)
    _require_box_inside(box, raw_width, raw_height)
    left, top, right, bottom = box.left, box.top, box.right, box.bottom
    if resolved == 1:
        return box
    if resolved == 3:
        return PixelBox(raw_width - right, raw_height - bottom, raw_width - left, raw_height - top)
    if resolved == 6:
        return PixelBox(raw_height - bottom, left, raw_height - top, right)
    return PixelBox(top, raw_width - right, bottom, raw_width - left)


def imcu_size(max_horizontal_sampling: int, max_vertical_sampling: int) -> tuple[int, int]:
    """iMCU size of a baseline JPEG from its largest component sampling factors."""

    for factor in (max_horizontal_sampling, max_vertical_sampling):
        if isinstance(factor, bool) or factor not in (1, 2):
            raise SourceCropError(
                "SOURCE_CROP_SAMPLING_UNSUPPORTED",
                "Only sampling factors 1 and 2 (4:4:4, 4:2:2, 4:4:0, 4:2:0) are supported.",
            )
    return 8 * max_horizontal_sampling, 8 * max_vertical_sampling


def imcu_from_sampling_factors(factors: Iterable[tuple[int, int]]) -> tuple[int, int]:
    """iMCU size from per-component ``(horizontal, vertical)`` sampling factors.

    Works for baseline and progressive JPEG alike (Pillow ``Image.layer``).
    """

    pairs = list(factors)
    if not pairs:
        raise SourceCropError("SOURCE_CROP_SAMPLING_UNSUPPORTED", "JPEG has no components.")
    return imcu_size(max(h for h, _ in pairs), max(v for _, v in pairs))


def align_raw_box(
    box: PixelBox, *, imcu: tuple[int, int], raw_width: int, raw_height: int
) -> PixelBox:
    """Widen a stored-JPEG box outward to the iMCU grid, clamped to the image."""

    imcu_width, imcu_height = imcu
    if imcu_width not in (8, 16) or imcu_height not in (8, 16):
        raise SourceCropError("SOURCE_CROP_SAMPLING_UNSUPPORTED", "iMCU must be 8 or 16 pixels.")
    _require_box_inside(box, raw_width, raw_height)
    return PixelBox(
        (box.left // imcu_width) * imcu_width,
        (box.top // imcu_height) * imcu_height,
        min(raw_width, -(-box.right // imcu_width) * imcu_width),
        min(raw_height, -(-box.bottom // imcu_height) * imcu_height),
    )


def plan_source_crop(
    points: Iterable[tuple[float, float]],
    *,
    oriented_width: int,
    oriented_height: int,
    orientation: int | None,
    imcu: tuple[int, int],
    margin_px: int = DEFAULT_MARGIN_PX,
) -> SourceCropPlan:
    """Plan the lossless crop of one managed original (plan R6)."""

    protected = clamp_protected_box(
        protected_box_from_points(points), width=oriented_width, height=oriented_height
    )
    grown = margin_box(protected, margin_px=margin_px, width=oriented_width, height=oriented_height)
    raw_width, raw_height = raw_dimensions(oriented_width, oriented_height, orientation)
    raw = oriented_to_raw_box(
        grown,
        orientation=orientation,
        oriented_width=oriented_width,
        oriented_height=oriented_height,
    )
    aligned = align_raw_box(raw, imcu=imcu, raw_width=raw_width, raw_height=raw_height)
    oriented = raw_to_oriented_box(
        aligned, orientation=orientation, raw_width=raw_width, raw_height=raw_height
    )
    return SourceCropPlan(
        protected_box=protected,
        margin_px=margin_px,
        imcu_width=imcu[0],
        imcu_height=imcu[1],
        raw_box=aligned,
        oriented_box=oriented,
    )


def is_crop_beneficial(*, original_size_bytes: int, crop_size_bytes: int) -> bool:
    """A crop is worth keeping only when it saves at least 5% of the original."""

    if original_size_bytes < 1 or crop_size_bytes < 1:
        raise SourceCropError("SOURCE_CROP_SIZE_INVALID", "File sizes must be positive.")
    return crop_size_bytes <= original_size_bytes * (1.0 - MIN_SAVING_FRACTION)


@dataclass(frozen=True, slots=True)
class CropPixelVerdict:
    """Accepted crop; ``edge_mismatch_pixels`` all lie on the outer edge ring."""

    edge_mismatch_pixels: int


def verify_crop_pixels(
    original_region: NDArray[np.uint8],
    crop: NDArray[np.uint8],
    *,
    crop_box: PixelBox,
    image_width: int,
    image_height: int,
    protected: ProtectedBox,
) -> CropPixelVerdict:
    """Accept a decoded crop only when it equals the original region (plan R7).

    Chroma upsampling may change the outermost pixel ring along crop edges that
    are not image borders; nothing else may differ, and protected quads must
    stay clear of that ring.
    """

    if original_region.dtype != np.uint8 or crop.dtype != np.uint8:
        raise SourceCropError("SOURCE_CROP_VERIFICATION_FAILED", "Pixels must be RGB uint8.")
    expected_shape = (crop_box.height, crop_box.width, 3)
    if original_region.shape != expected_shape or crop.shape != expected_shape:
        raise SourceCropError(
            "SOURCE_CROP_VERIFICATION_FAILED",
            "Decoded crop dimensions differ from the planned box.",
        )
    if not crop_box.fits(image_width, image_height):
        raise SourceCropError("SOURCE_CROP_VERIFICATION_FAILED", "Crop box lies outside the image.")
    ring_left = EDGE_RING_PX if crop_box.left > 0 else 0
    ring_top = EDGE_RING_PX if crop_box.top > 0 else 0
    ring_right = EDGE_RING_PX if crop_box.right < image_width else 0
    ring_bottom = EDGE_RING_PX if crop_box.bottom < image_height else 0
    clearance = MIN_PROTECTED_DISTANCE_FROM_RING_PX
    if (
        (ring_left and protected.left < crop_box.left + ring_left + clearance)
        or (ring_top and protected.top < crop_box.top + ring_top + clearance)
        or (ring_right and protected.right > crop_box.right - ring_right - clearance)
        or (ring_bottom and protected.bottom > crop_box.bottom - ring_bottom - clearance)
        or protected.left < crop_box.left
        or protected.top < crop_box.top
        or protected.right > crop_box.right
        or protected.bottom > crop_box.bottom
    ):
        raise SourceCropError(
            "SOURCE_CROP_VERIFICATION_FAILED",
            "Protected quads must stay inside the crop and clear of its edge ring.",
        )
    differs = np.any(original_region != crop, axis=2)
    inner = differs[
        ring_top : crop_box.height - ring_bottom, ring_left : crop_box.width - ring_right
    ]
    inner_mismatches = int(np.count_nonzero(inner))
    total = int(np.count_nonzero(differs))
    if inner_mismatches:
        raise SourceCropError(
            "SOURCE_CROP_VERIFICATION_FAILED",
            f"{inner_mismatches} pixels inside the crop differ from the original.",
        )
    return CropPixelVerdict(edge_mismatch_pixels=total)


def compose_canvas(
    crop_rgb: NDArray[np.uint8], *, crop_box: PixelBox, width: int, height: int
) -> NDArray[np.uint8]:
    """Paste a decoded oriented crop into a full-size canvas of the original."""

    if crop_rgb.dtype != np.uint8 or crop_rgb.shape != (crop_box.height, crop_box.width, 3):
        raise SourceCropError(
            "SOURCE_CROP_CANVAS_INVALID", "Decoded crop does not match the attested crop box."
        )
    _require_box_inside(crop_box, width, height)
    canvas = np.full((height, width, 3), CANVAS_FILL_VALUE, dtype=np.uint8)
    canvas[crop_box.top : crop_box.bottom, crop_box.left : crop_box.right] = crop_rgb
    return canvas


@dataclass(frozen=True, slots=True)
class SourceCropAttestation:
    """Checksum-bound statement that a crop file is a verified region of an original."""

    original_checksum_sha256: str
    original_size_bytes: int
    original_normalized_pixel_checksum_sha256: str
    original_width: int
    original_height: int
    original_exif_orientation: int | None
    crop_checksum_sha256: str
    crop_size_bytes: int
    crop_normalized_pixel_checksum_sha256: str
    canvas_pixel_checksum_sha256: str
    crop_box: PixelBox
    raw_crop_box: PixelBox
    protected_box: ProtectedBox
    margin_px: int
    imcu_width: int
    imcu_height: int
    edge_mismatch_pixels: int
    tool_version: str
    policy_version: str = SOURCE_CROP_POLICY_VERSION

    def __post_init__(self) -> None:
        for checksum in (
            self.original_checksum_sha256,
            self.original_normalized_pixel_checksum_sha256,
            self.crop_checksum_sha256,
            self.crop_normalized_pixel_checksum_sha256,
            self.canvas_pixel_checksum_sha256,
        ):
            _require_sha256(checksum)
        _require_dimensions(self.original_width, self.original_height)
        _resolve_orientation(self.original_exif_orientation)
        for count in (self.original_size_bytes, self.crop_size_bytes):
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise _attestation_error("File sizes must be positive integers.")
        if self.crop_size_bytes >= self.original_size_bytes:
            raise _attestation_error("A crop must be smaller than its original.")
        if not self.crop_box.fits(self.original_width, self.original_height):
            raise _attestation_error("Crop box lies outside the original.")
        raw_width, raw_height = raw_dimensions(
            self.original_width, self.original_height, self.original_exif_orientation
        )
        expected_raw = oriented_to_raw_box(
            self.crop_box,
            orientation=self.original_exif_orientation,
            oriented_width=self.original_width,
            oriented_height=self.original_height,
        )
        if expected_raw != self.raw_crop_box or not self.raw_crop_box.fits(raw_width, raw_height):
            raise _attestation_error("Stored and oriented crop boxes disagree.")
        for value in (self.imcu_width, self.imcu_height, self.margin_px, self.edge_mismatch_pixels):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _attestation_error("Attestation counters must be non-negative integers.")
        if self.imcu_width not in (8, 16) or self.imcu_height not in (8, 16):
            raise _attestation_error("iMCU must be 8 or 16 pixels.")
        raw = self.raw_crop_box
        if (
            raw.left % self.imcu_width
            or raw.top % self.imcu_height
            or (raw.right % self.imcu_width and raw.right != raw_width)
            or (raw.bottom % self.imcu_height and raw.bottom != raw_height)
        ):
            raise _attestation_error("Stored crop box is not aligned to the iMCU grid.")
        protected = self.protected_box
        if (
            protected.left < 0
            or protected.top < 0
            or protected.right > self.original_width
            or protected.bottom > self.original_height
        ):
            raise _attestation_error("Protected box must be clamped to the original.")
        try:
            required = margin_box(
                protected,
                margin_px=self.margin_px,
                width=self.original_width,
                height=self.original_height,
            )
        except SourceCropError as error:
            raise _attestation_error(str(error)) from error
        if not self.crop_box.contains(required):
            raise _attestation_error("Crop box does not contain the protected box and margin.")
        if not self.tool_version:
            raise _attestation_error("Attestation tool version is missing.")
        if self.policy_version != SOURCE_CROP_POLICY_VERSION:
            raise _attestation_error("Unsupported crop policy version.")

    def body(self) -> dict[str, object]:
        return {
            "version": SOURCE_CROP_ATTESTATION_VERSION,
            "policyVersion": self.policy_version,
            "coordinateSpace": SOURCE_CROP_COORDINATE_SPACE,
            "original": {
                "checksumSha256": self.original_checksum_sha256,
                "sizeBytes": self.original_size_bytes,
                "normalizedPixelChecksumSha256": self.original_normalized_pixel_checksum_sha256,
                "width": self.original_width,
                "height": self.original_height,
                "exifOrientation": self.original_exif_orientation,
            },
            "crop": {
                "checksumSha256": self.crop_checksum_sha256,
                "sizeBytes": self.crop_size_bytes,
                "normalizedPixelChecksumSha256": self.crop_normalized_pixel_checksum_sha256,
                "canvasPixelChecksumSha256": self.canvas_pixel_checksum_sha256,
                "box": self.crop_box.as_list(),
                "rawBox": self.raw_crop_box.as_list(),
                "imcu": [self.imcu_width, self.imcu_height],
                "edgeMismatchPixels": self.edge_mismatch_pixels,
                "toolVersion": self.tool_version,
            },
            "protectedBox": self.protected_box.as_list(),
            "marginPx": self.margin_px,
        }


def crop_covers_points(
    attestation: SourceCropAttestation, points: Iterable[tuple[float, float]]
) -> bool:
    """Whether an attested crop still keeps today's protected quads (TASK-1048).

    The crop must contain the clamped protected box of ``points`` grown by the
    attested margin, and the protected box must stay clear of the edge ring on
    every crop edge that is not an image border, exactly as R7 required when
    the crop was made. Geometry approved after the crop may fall outside it.
    """

    width, height = attestation.original_width, attestation.original_height
    try:
        protected = clamp_protected_box(
            protected_box_from_points(points), width=width, height=height
        )
        required = margin_box(
            protected, margin_px=attestation.margin_px, width=width, height=height
        )
    except SourceCropError:
        return False
    box = attestation.crop_box
    if not box.contains(required):
        return False
    clearance = EDGE_RING_PX + MIN_PROTECTED_DISTANCE_FROM_RING_PX
    return not (
        (box.left > 0 and protected.left < box.left + clearance)
        or (box.top > 0 and protected.top < box.top + clearance)
        or (box.right < width and protected.right > box.right - clearance)
        or (box.bottom < height and protected.bottom > box.bottom - clearance)
    )


def encode_attestation(attestation: SourceCropAttestation) -> bytes:
    """Canonical JSON bytes with a checksum over every other field."""

    body = attestation.body()
    document = dict(body)
    document["attestationSha256"] = _canonical_sha256(body)
    return _canonical_json(document)


def attestation_sha256(document: bytes) -> str:
    """Checksum of the stored attestation file, recorded by the crop row."""

    return hashlib.sha256(document).hexdigest()


def decode_attestation(
    document: bytes, *, expected_original_checksum_sha256: str
) -> SourceCropAttestation:
    """Parse and fully validate an attestation; any drift is fail-closed."""

    _require_sha256(expected_original_checksum_sha256)
    try:
        parsed = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _attestation_error("Attestation is not valid UTF-8 JSON.") from error
    if not isinstance(parsed, dict):
        raise _attestation_error("Attestation must be a JSON object.")
    claimed = parsed.pop("attestationSha256", None)
    if not isinstance(claimed, str) or claimed != _canonical_sha256(parsed):
        raise _attestation_error("Attestation checksum does not match its content.")
    _require_keys(
        parsed,
        {
            "version",
            "policyVersion",
            "coordinateSpace",
            "original",
            "crop",
            "protectedBox",
            "marginPx",
        },
    )
    if (
        parsed["version"] != SOURCE_CROP_ATTESTATION_VERSION
        or parsed["coordinateSpace"] != SOURCE_CROP_COORDINATE_SPACE
    ):
        raise _attestation_error("Unsupported attestation version or coordinate space.")
    original = _mapping(parsed["original"])
    crop = _mapping(parsed["crop"])
    _require_keys(
        original,
        {
            "checksumSha256",
            "sizeBytes",
            "normalizedPixelChecksumSha256",
            "width",
            "height",
            "exifOrientation",
        },
    )
    _require_keys(
        crop,
        {
            "checksumSha256",
            "sizeBytes",
            "normalizedPixelChecksumSha256",
            "canvasPixelChecksumSha256",
            "box",
            "rawBox",
            "imcu",
            "edgeMismatchPixels",
            "toolVersion",
        },
    )
    imcu = _int_list(crop["imcu"], 2)
    protected_values = parsed["protectedBox"]
    if not isinstance(protected_values, list) or len(protected_values) != 4:
        raise _attestation_error("Protected box must have four numbers.")
    try:
        attestation = SourceCropAttestation(
            original_checksum_sha256=_str(original["checksumSha256"]),
            original_size_bytes=_int(original["sizeBytes"]),
            original_normalized_pixel_checksum_sha256=_str(
                original["normalizedPixelChecksumSha256"]
            ),
            original_width=_int(original["width"]),
            original_height=_int(original["height"]),
            original_exif_orientation=_optional_int(original["exifOrientation"]),
            crop_checksum_sha256=_str(crop["checksumSha256"]),
            crop_size_bytes=_int(crop["sizeBytes"]),
            crop_normalized_pixel_checksum_sha256=_str(crop["normalizedPixelChecksumSha256"]),
            canvas_pixel_checksum_sha256=_str(crop["canvasPixelChecksumSha256"]),
            crop_box=PixelBox(*_int_list(crop["box"], 4)),
            raw_crop_box=PixelBox(*_int_list(crop["rawBox"], 4)),
            protected_box=ProtectedBox(*(_number(value) for value in protected_values)),
            margin_px=_int(parsed["marginPx"]),
            imcu_width=imcu[0],
            imcu_height=imcu[1],
            edge_mismatch_pixels=_int(crop["edgeMismatchPixels"]),
            tool_version=_str(crop["toolVersion"]),
            policy_version=_str(parsed["policyVersion"]),
        )
    except SourceCropError as error:
        raise _attestation_error(str(error)) from error
    if attestation.original_checksum_sha256 != expected_original_checksum_sha256:
        raise _attestation_error("Attestation belongs to a different original.")
    return attestation


def cropped_original_relative_paths(
    original_checksum_sha256: str,
) -> tuple[PurePosixPath, PurePosixPath]:
    """Crop and attestation paths relative to the managed ``data`` directory."""

    _require_sha256(original_checksum_sha256)
    directory = PurePosixPath(CROPPED_ORIGINALS_DIRECTORY, original_checksum_sha256[:2])
    return (
        directory / f"{original_checksum_sha256}.jpg",
        directory / f"{original_checksum_sha256}.json",
    )


def cropped_sibling_paths(
    original_path: Path, original_checksum_sha256: str
) -> tuple[Path, Path] | None:
    """Crop and attestation paths next to a managed original path.

    Only the content-addressed layout ``<data>/originals/<sha[:2]>/<sha>.jpg``
    has a crop sibling; any other path returns ``None`` so callers keep their
    current behavior.
    """

    _require_sha256(original_checksum_sha256)
    shard = original_path.parent
    originals = shard.parent
    if (
        original_path.name != f"{original_checksum_sha256}.jpg"
        or shard.name != original_checksum_sha256[:2]
        or originals.name != ORIGINALS_DIRECTORY
    ):
        return None
    crop_relative, attestation_relative = cropped_original_relative_paths(original_checksum_sha256)
    data = originals.parent
    return data.joinpath(*crop_relative.parts), data.joinpath(*attestation_relative.parts)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _resolve_orientation(orientation: int | None) -> int:
    if orientation is None:
        return 1
    if isinstance(orientation, bool) or orientation not in SUPPORTED_ORIENTATIONS:
        raise SourceCropError(
            "SOURCE_CROP_ORIENTATION_UNSUPPORTED",
            "Only EXIF orientations 1, 3, 6 and 8 (or none) can be cropped losslessly.",
        )
    return orientation


def _require_dimensions(width: int, height: int) -> None:
    if isinstance(width, bool) or isinstance(height, bool) or width < 1 or height < 1:
        raise SourceCropError("SOURCE_CROP_BOX_INVALID", "Image dimensions must be positive.")


def _require_box_inside(box: PixelBox, width: int, height: int) -> None:
    _require_dimensions(width, height)
    if not box.fits(width, height):
        raise SourceCropError("SOURCE_CROP_BOX_INVALID", "Pixel box lies outside the image.")


def _require_sha256(value: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SourceCropError(
            "SOURCE_CROP_CHECKSUM_INVALID", "Checksums must be lowercase SHA-256."
        )


def _attestation_error(message: str) -> SourceCropError:
    return SourceCropError("SOURCE_CROP_ATTESTATION_INVALID", message)


def _require_keys(value: Mapping[str, object], keys: set[str]) -> None:
    if set(value) != keys:
        raise _attestation_error("Attestation fields differ from the closed schema.")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _attestation_error("Attestation section must be an object.")
    return value


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise _attestation_error("Expected a string.")
    return value


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _attestation_error("Expected an integer.")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _int(value)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _attestation_error("Expected a number.")
    return float(value)


def _int_list(value: object, length: int) -> list[int]:
    if not isinstance(value, list) or len(value) != length:
        raise _attestation_error(f"Expected a list of {length} integers.")
    return [_int(item) for item in value]
