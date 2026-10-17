"""Pure canonical JPEG decoding and dimensioned RGB identity, shared with workers.

File ownership, managed roots, execution caches and database writes stay with callers.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_api.domain.image_geometry_v2 import NormalizedSourceImage
from game_predictor_api.domain.source_crop import (
    EDGE_RING_PX,
    PixelBox,
    SourceCropAttestation,
    SourceCropError,
    compose_canvas,
    decode_attestation,
    raw_dimensions,
)

CANONICAL_SOURCE_LOADER_VERSION = "image-normalization-v2-in-memory-source-v1"
RGB_PIXEL_CHECKSUM_VERSION = "rgb-uint8-v1"
MAX_SOURCE_PIXELS = 50_000_000
ORIENTATION_TAG = 274
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ORIENTATION_ACTIONS = {
    1: "identity",
    2: "flip_left_right",
    3: "rotate_180",
    4: "flip_top_bottom",
    5: "transpose",
    6: "rotate_90_clockwise",
    7: "transverse",
    8: "rotate_90_counterclockwise",
}


class CanonicalSourceLoadError(ValueError):
    """Stable failure before a source can enter virtual geometry."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CanonicalSourceCrop:
    """Attested crop behind a frame whose managed original was replaced (D-562).

    Only pixels inside ``valid_box`` come from the original image; the rest of
    the canvas is fill. Consumers that read pixels must stay inside it.
    """

    attestation: SourceCropAttestation

    @property
    def valid_box(self) -> PixelBox:
        return self.attestation.crop_box


@dataclass(frozen=True, slots=True, eq=False)
class CanonicalSourceFrame:
    """One execution-scoped RGB decode in the canonical source coordinate space.

    ``source`` always carries the identity of the managed original. A frame
    decoded from an attested crop (``crop`` set) has the original's dimensions
    and identity, but its pixels are the crop canvas with its own checksum.
    """

    source: NormalizedSourceImage
    raw_width: int
    raw_height: int
    source_mode: str
    orientation_action: str
    rgb: NDArray[np.uint8]
    crop: CanonicalSourceCrop | None = None

    @property
    def pixel_checksum_sha256(self) -> str:
        """Checksum of ``rgb``: the original's pixels, or the attested crop canvas."""

        if self.crop is None:
            return self.source.normalized_pixel_checksum_sha256
        return self.crop.attestation.canvas_pixel_checksum_sha256

    def __post_init__(self) -> None:
        if self.rgb.dtype != np.uint8:
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_FRAME_INVALID",
                "Canonical source pixels must use RGB uint8 without implicit conversion.",
            )
        contiguous = np.ascontiguousarray(self.rgb)
        if (
            contiguous.ndim != 3
            or contiguous.shape[2] != 3
            or contiguous.shape[1] != self.source.width
            or contiguous.shape[0] != self.source.height
            or self.raw_width < 1
            or self.raw_height < 1
            or not self.source_mode
        ):
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_FRAME_INVALID",
                "Canonical source pixels and metadata are inconsistent.",
            )
        if self.crop is not None:
            attestation = self.crop.attestation
            if (
                self.source.source_checksum_sha256 != attestation.original_checksum_sha256
                or self.source.normalized_pixel_checksum_sha256
                != attestation.original_normalized_pixel_checksum_sha256
                or self.source.width != attestation.original_width
                or self.source.height != attestation.original_height
                or self.source.exif_orientation != attestation.original_exif_orientation
            ):
                raise CanonicalSourceLoadError(
                    "SOURCE_CROP_IDENTITY_MISMATCH",
                    "A crop frame must carry exactly the attested original identity.",
                )
        if rgb_pixel_checksum_sha256(contiguous) != self.pixel_checksum_sha256:
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_PIXEL_CHECKSUM_MISMATCH",
                "Canonical source pixels differ from their normalized-pixel checksum.",
            )
        contiguous.setflags(write=False)
        object.__setattr__(self, "rgb", contiguous)


def require_inside_valid_box(
    frame: CanonicalSourceFrame, points: Iterable[tuple[float, float]]
) -> None:
    """Fail when a crop frame would be sampled outside its original pixels.

    Interpolation reads neighbours, so points must also keep one pixel clear
    of the crop's edge ring along edges that are not the image border. Along
    an image border the crop behaves like the original (points may reach past
    it, as partially visible cells do). A frame of a full original accepts
    every point.
    """

    if frame.crop is None:
        return
    box = frame.crop.valid_box
    width, height = frame.source.width, frame.source.height
    clearance = EDGE_RING_PX + 1
    unbounded = float("inf")
    left = box.left + clearance if box.left > 0 else -unbounded
    top = box.top + clearance if box.top > 0 else -unbounded
    right = box.right - clearance if box.right < width else unbounded
    bottom = box.bottom - clearance if box.bottom < height else unbounded
    for x, y in points:
        if not (left <= x <= right and top <= y <= bottom):
            raise CanonicalSourceLoadError(
                "SOURCE_REGION_UNAVAILABLE",
                "The requested region lies outside the retained crop of this source.",
            )


def validate_source_checksum_sha256(checksum: str) -> None:
    """Validate the byte identity before file access or decoding."""

    if _SHA256.fullmatch(checksum) is None:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_CHECKSUM_INVALID",
            "Canonical source loading requires a lowercase SHA-256 checksum.",
        )


def decode_canonical_source_bytes(
    content: bytes,
    *,
    expected_source_checksum_sha256: str,
    max_source_pixels: int = MAX_SOURCE_PIXELS,
    normalization_adapter_version: str = CANONICAL_SOURCE_LOADER_VERSION,
) -> CanonicalSourceFrame:
    """Hash and decode the same bytes, applying their EXIF orientation exactly once."""

    validate_source_checksum_sha256(expected_source_checksum_sha256)
    if max_source_pixels < 1:
        raise ValueError("max_source_pixels must be positive")
    actual_checksum = hashlib.sha256(content).hexdigest()
    if actual_checksum != expected_source_checksum_sha256:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_CHECKSUM_MISMATCH",
            "The managed source image differs from its attested checksum.",
        )

    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format != "JPEG":
                raise CanonicalSourceLoadError(
                    "IMAGE_CANONICAL_SOURCE_FORMAT_UNSUPPORTED",
                    "Virtual geometry currently accepts managed JPEG sources only.",
                )
            raw_width, raw_height = source.size
            if raw_width * raw_height > max_source_pixels:
                raise CanonicalSourceLoadError(
                    "IMAGE_CANONICAL_SOURCE_PIXEL_LIMIT",
                    "The managed source exceeds the configured pixel limit.",
                )
            source.load()
            source_mode = source.mode
            orientation_value = source.getexif().get(ORIENTATION_TAG)
            if orientation_value is not None and (
                isinstance(orientation_value, bool)
                or not isinstance(orientation_value, int)
                or orientation_value not in ORIENTATION_ACTIONS
            ):
                raise CanonicalSourceLoadError(
                    "IMAGE_CANONICAL_SOURCE_EXIF_ORIENTATION_INVALID",
                    "EXIF Orientation must be omitted or an integer from 1 through 8.",
                )
            oriented = ImageOps.exif_transpose(source)
            rgb = np.array(oriented.convert("RGB"), dtype=np.uint8, copy=True)
    except CanonicalSourceLoadError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_DECODE_FAILED",
            "The managed source JPEG cannot be decoded.",
        ) from error

    height, width = rgb.shape[:2]
    frame = CanonicalSourceFrame(
        source=NormalizedSourceImage(
            source_checksum_sha256=actual_checksum,
            normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb),
            width=width,
            height=height,
            exif_orientation=orientation_value,
            normalization_adapter_version=normalization_adapter_version,
        ),
        raw_width=raw_width,
        raw_height=raw_height,
        source_mode=source_mode,
        orientation_action=(
            "none" if orientation_value is None else ORIENTATION_ACTIONS[orientation_value]
        ),
        rgb=rgb,
    )
    return frame


def decode_cropped_source_bytes(
    crop_content: bytes,
    attestation_content: bytes,
    *,
    expected_source_checksum_sha256: str,
    max_source_pixels: int = MAX_SOURCE_PIXELS,
    normalization_adapter_version: str = CANONICAL_SOURCE_LOADER_VERSION,
) -> CanonicalSourceFrame:
    """Rebuild the canonical frame of a replaced original from its attested crop.

    Every identity is checked before the canvas is trusted: the attestation's
    own checksum and original, the crop file bytes, its decoded dimensions and
    pixels, and finally the canvas checksum. Any drift fails closed.
    """

    validate_source_checksum_sha256(expected_source_checksum_sha256)
    if max_source_pixels < 1:
        raise ValueError("max_source_pixels must be positive")
    try:
        attestation = decode_attestation(
            attestation_content,
            expected_original_checksum_sha256=expected_source_checksum_sha256,
        )
    except SourceCropError as error:
        raise CanonicalSourceLoadError(
            "SOURCE_CROP_ATTESTATION_INVALID", "The crop attestation is not valid."
        ) from error
    if hashlib.sha256(crop_content).hexdigest() != attestation.crop_checksum_sha256:
        raise CanonicalSourceLoadError(
            "SOURCE_CROP_CHECKSUM_MISMATCH",
            "The crop file differs from its attested checksum.",
        )
    if attestation.original_width * attestation.original_height > max_source_pixels:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_PIXEL_LIMIT",
            "The managed source exceeds the configured pixel limit.",
        )
    try:
        with Image.open(io.BytesIO(crop_content)) as cropped:
            if cropped.format != "JPEG":
                raise CanonicalSourceLoadError(
                    "IMAGE_CANONICAL_SOURCE_FORMAT_UNSUPPORTED",
                    "Virtual geometry currently accepts managed JPEG sources only.",
                )
            cropped.load()
            source_mode = cropped.mode
            orientation_value = cropped.getexif().get(ORIENTATION_TAG)
            if orientation_value != attestation.original_exif_orientation:
                raise CanonicalSourceLoadError(
                    "SOURCE_CROP_ORIENTATION_MISMATCH",
                    "The crop does not keep the original EXIF orientation.",
                )
            rgb = np.array(
                ImageOps.exif_transpose(cropped).convert("RGB"), dtype=np.uint8, copy=True
            )
    except CanonicalSourceLoadError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_DECODE_FAILED",
            "The managed source crop cannot be decoded.",
        ) from error
    box = attestation.crop_box
    if rgb.shape != (box.height, box.width, 3):
        raise CanonicalSourceLoadError(
            "SOURCE_CROP_DIMENSIONS_MISMATCH",
            "The decoded crop differs from its attested box.",
        )
    if rgb_pixel_checksum_sha256(rgb) != attestation.crop_normalized_pixel_checksum_sha256:
        raise CanonicalSourceLoadError(
            "SOURCE_CROP_PIXEL_CHECKSUM_MISMATCH",
            "The decoded crop differs from its attested pixels.",
        )
    canvas = compose_canvas(
        rgb, crop_box=box, width=attestation.original_width, height=attestation.original_height
    )
    raw_width, raw_height = raw_dimensions(
        attestation.original_width,
        attestation.original_height,
        attestation.original_exif_orientation,
    )
    orientation = attestation.original_exif_orientation
    return CanonicalSourceFrame(
        source=NormalizedSourceImage(
            source_checksum_sha256=attestation.original_checksum_sha256,
            normalized_pixel_checksum_sha256=attestation.original_normalized_pixel_checksum_sha256,
            width=attestation.original_width,
            height=attestation.original_height,
            exif_orientation=orientation,
            normalization_adapter_version=normalization_adapter_version,
        ),
        raw_width=raw_width,
        raw_height=raw_height,
        source_mode=source_mode,
        orientation_action="none" if orientation is None else ORIENTATION_ACTIONS[orientation],
        rgb=canvas,
        crop=CanonicalSourceCrop(attestation),
    )


def rgb_pixel_checksum_sha256(rgb: NDArray[np.uint8]) -> str:
    """Hash exact RGB pixels with dimensions, independently of file encoding."""

    if rgb.dtype != np.uint8:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_RGB_INVALID",
            "Pixel checksum requires RGB uint8 without implicit conversion.",
        )
    contiguous = np.ascontiguousarray(rgb)
    if contiguous.ndim != 3 or contiguous.shape[2] != 3:
        raise CanonicalSourceLoadError(
            "IMAGE_CANONICAL_SOURCE_RGB_INVALID",
            "Pixel checksum requires an RGB uint8 image.",
        )
    digest = hashlib.sha256()
    digest.update(f"{RGB_PIXEL_CHECKSUM_VERSION}\0".encode("ascii"))
    digest.update(int(contiguous.shape[1]).to_bytes(8, "big"))
    digest.update(int(contiguous.shape[0]).to_bytes(8, "big"))
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()
