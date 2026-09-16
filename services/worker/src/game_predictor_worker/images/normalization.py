"""Deterministic EXIF normalization for legacy artifacts and virtual geometry."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from game_predictor_api.domain.image_geometry_v2 import NormalizedSourceImage
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL import __version__ as pillow_version

from game_predictor_worker.images.discovery import (
    SourceImage,
    SourceManifest,
    discover_images,
)
from game_predictor_worker.images.image_file import ImageFileError, sha256_file

NORMALIZATION_VERSION = "image-normalization-v1"
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


class ImageNormalizationError(ValueError):
    """Stable fatal error for normalization setup or source integrity."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CanonicalSourceLoadError(ValueError):
    """Stable failure before a source can enter virtual geometry."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True, eq=False)
class CanonicalSourceFrame:
    """One execution-scoped RGB decode in the canonical source coordinate space."""

    source: NormalizedSourceImage
    raw_width: int
    raw_height: int
    source_mode: str
    orientation_action: str
    rgb: NDArray[np.uint8]

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
        if rgb_pixel_checksum_sha256(contiguous) != self.source.normalized_pixel_checksum_sha256:
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_PIXEL_CHECKSUM_MISMATCH",
                "Canonical source pixels differ from their normalized-pixel checksum.",
            )
        contiguous.setflags(write=False)
        object.__setattr__(self, "rgb", contiguous)


class CanonicalSourceLoader:
    """Decode one immutable source and apply its EXIF orientation exactly once.

    The one-entry cache is intentionally execution-scoped. It prevents geometry
    and all virtual-cell renders for one source from decoding the JPEG again,
    while keeping memory bounded independently of the size of an import.
    """

    version = CANONICAL_SOURCE_LOADER_VERSION

    def __init__(self, *, max_source_pixels: int = MAX_SOURCE_PIXELS) -> None:
        if max_source_pixels < 1:
            raise ValueError("max_source_pixels must be positive")
        self._max_source_pixels = max_source_pixels
        self._cache_key: tuple[Path, str] | None = None
        self._cached_frame: CanonicalSourceFrame | None = None

    def load(
        self,
        source_path: Path,
        *,
        expected_source_checksum_sha256: str,
    ) -> CanonicalSourceFrame:
        if _SHA256.fullmatch(expected_source_checksum_sha256) is None:
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_CHECKSUM_INVALID",
                "Canonical source loading requires a lowercase SHA-256 checksum.",
            )
        try:
            resolved = source_path.resolve(strict=True)
        except OSError as error:
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_NOT_FOUND",
                "The managed source image does not exist or cannot be resolved.",
            ) from error
        if not resolved.is_file() or resolved.is_symlink():
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_PATH_INVALID",
                "The managed source must be a regular, non-symlink file.",
            )
        cache_key = (resolved, expected_source_checksum_sha256)
        if self._cache_key == cache_key and self._cached_frame is not None:
            return self._cached_frame

        try:
            actual_checksum = sha256_file(resolved)
        except ImageFileError as error:
            raise CanonicalSourceLoadError(error.code, str(error)) from error
        if actual_checksum != expected_source_checksum_sha256:
            raise CanonicalSourceLoadError(
                "IMAGE_CANONICAL_SOURCE_CHECKSUM_MISMATCH",
                "The managed source image differs from its attested checksum.",
            )

        try:
            with Image.open(resolved) as source:
                if source.format != "JPEG":
                    raise CanonicalSourceLoadError(
                        "IMAGE_CANONICAL_SOURCE_FORMAT_UNSUPPORTED",
                        "Virtual geometry currently accepts managed JPEG sources only.",
                    )
                raw_width, raw_height = source.size
                if raw_width * raw_height > self._max_source_pixels:
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
                normalization_adapter_version=self.version,
            ),
            raw_width=raw_width,
            raw_height=raw_height,
            source_mode=source_mode,
            orientation_action=(
                "none" if orientation_value is None else ORIENTATION_ACTIONS[orientation_value]
            ),
            rgb=rgb,
        )
        self._cache_key = cache_key
        self._cached_frame = frame
        return frame

    def clear(self) -> None:
        """Release the execution-scoped source before processing the next file."""

        self._cache_key = None
        self._cached_frame = None


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


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    code: str
    source_checksum_sha256: str
    source_relative_path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceRelativePath": self.source_relative_path,
        }


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    source_checksum_sha256: str
    source_paths: tuple[str, ...]
    source_width: int
    source_height: int
    source_mode: str
    exif_orientation: int | None
    orientation_action: str
    normalized_width: int
    normalized_height: int
    normalized_checksum_sha256: str
    normalized_relative_path: str
    diagnostic_relative_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "diagnosticRelativePath": self.diagnostic_relative_path,
            "exifOrientation": self.exif_orientation,
            "normalizedChecksumSha256": self.normalized_checksum_sha256,
            "normalizedHeight": self.normalized_height,
            "normalizedRelativePath": self.normalized_relative_path,
            "normalizedWidth": self.normalized_width,
            "orientationAction": self.orientation_action,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceHeight": self.source_height,
            "sourceMode": self.source_mode,
            "sourcePaths": list(self.source_paths),
            "sourceWidth": self.source_width,
        }


@dataclass(frozen=True, slots=True)
class NormalizationReport:
    source_manifest_sha256: str
    images: tuple[NormalizedImage, ...]
    issues: tuple[NormalizationIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "images": [image.to_dict() for image in self.images],
            "issueCount": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
            "normalizationVersion": NORMALIZATION_VERSION,
            "normalizedImageCount": len(self.images),
            "pillowVersion": pillow_version,
            "schemaVersion": 1,
            "sourceImageCount": len(self.images) + len(self.issues),
            "sourceManifestSha256": self.source_manifest_sha256,
            "status": "clean" if not self.issues else "issues",
        }

    def to_json_bytes(self) -> bytes:
        text = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"{text}\n".encode()


def _safe_source_path(source_root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_UNSAFE_SOURCE_PATH",
            "Source manifest contains an unsafe relative path.",
        )
    resolved = (source_root / Path(*relative.parts)).resolve(strict=True)
    if not resolved.is_relative_to(source_root):
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_UNSAFE_SOURCE_PATH",
            "Source manifest path escapes the source root.",
        )
    return resolved


def _validate_roots(source_root: Path, artifact_root: Path) -> tuple[Path, Path]:
    try:
        source = source_root.resolve(strict=True)
    except OSError as error:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_SOURCE_ROOT_NOT_FOUND",
            "Source root does not exist or cannot be resolved.",
        ) from error
    if not source.is_dir():
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_SOURCE_ROOT_NOT_DIRECTORY",
            "Source root must be a directory.",
        )
    artifacts = artifact_root.resolve()
    if artifacts == source or artifacts.is_relative_to(source):
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_OUTPUT_IN_SOURCE",
            "Working artifacts must be stored outside the source root.",
        )
    return source, artifacts


def _load_and_verify_discovery_manifest(
    source_root: Path,
    manifest_path: Path,
) -> tuple[bytes, SourceManifest]:
    try:
        expected = manifest_path.read_bytes()
    except OSError as error:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_SOURCE_MANIFEST_UNREADABLE",
            "Source discovery manifest cannot be read.",
        ) from error
    current = discover_images(source_root)
    if current.to_json_bytes() != expected:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_SOURCE_MANIFEST_DRIFT",
            "Source folder differs from its discovery manifest.",
        )
    return expected, current


def _encode_clean_rgb_png(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    output = io.BytesIO()
    clean.save(output, format="PNG", optimize=False, compress_level=6)
    return output.getvalue()


def _artifact_paths(checksum: str) -> tuple[str, str]:
    base = PurePosixPath(NORMALIZATION_VERSION, checksum[:2], checksum)
    return (base / "normalized.png").as_posix(), (base / "diagnostic.json").as_posix()


def _artifact_path(root: Path, relative_path: str) -> Path:
    return root / Path(*PurePosixPath(relative_path).parts)


def _write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise ImageNormalizationError(
                "IMAGE_NORMALIZATION_ARTIFACT_UNREADABLE",
                "Existing normalization artifact cannot be read.",
            ) from error
        if existing != content:
            raise ImageNormalizationError(
                "IMAGE_NORMALIZATION_ARTIFACT_COLLISION",
                "Existing normalization artifact has different content.",
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except OSError as error:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_ARTIFACT_WRITE_FAILED",
            "Normalization artifact cannot be written.",
        ) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _diagnostic_bytes(image: NormalizedImage) -> bytes:
    payload = {
        **image.to_dict(),
        "normalizationVersion": NORMALIZATION_VERSION,
        "pillowVersion": pillow_version,
    }
    return f"{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}\n".encode()


def _normalize_one(
    source_root: Path,
    artifact_root: Path,
    source_image: SourceImage,
    *,
    max_source_pixels: int,
) -> NormalizedImage:
    source_paths = tuple(file.relative_path for file in source_image.files)
    source_path = _safe_source_path(source_root, source_paths[0])
    try:
        actual_checksum = sha256_file(source_path)
    except ImageFileError as error:
        raise ImageNormalizationError(error.code, str(error)) from error
    if actual_checksum != source_image.checksum_sha256:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_SOURCE_CHECKSUM_MISMATCH",
            "Source image checksum differs from the discovery manifest.",
        )

    try:
        with Image.open(source_path) as source:
            if source.format != "JPEG":
                raise ImageNormalizationError(
                    "IMAGE_NORMALIZATION_FORMAT_MISMATCH",
                    "Discovery source is not decoded as JPEG.",
                )
            source.load()
            source_width, source_height = source.size
            if source_width * source_height > max_source_pixels:
                raise ImageNormalizationError(
                    "IMAGE_NORMALIZATION_PIXEL_LIMIT",
                    "Source image exceeds the configured pixel limit.",
                )
            source_mode = source.mode
            orientation_value = source.getexif().get(ORIENTATION_TAG)
            if orientation_value is not None and (
                not isinstance(orientation_value, int)
                or isinstance(orientation_value, bool)
                or orientation_value not in ORIENTATION_ACTIONS
            ):
                raise ImageNormalizationError(
                    "IMAGE_NORMALIZATION_EXIF_ORIENTATION_INVALID",
                    "EXIF Orientation must be an integer from 1 to 8.",
                )
            orientation = orientation_value
            oriented = ImageOps.exif_transpose(source)
            normalized_png = _encode_clean_rgb_png(oriented)
            normalized_width, normalized_height = oriented.size
    except ImageNormalizationError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_DECODE_FAILED",
            "Source JPEG cannot be decoded.",
        ) from error

    normalized_checksum = hashlib.sha256(normalized_png).hexdigest()
    normalized_relative, diagnostic_relative = _artifact_paths(source_image.checksum_sha256)
    normalized = NormalizedImage(
        source_checksum_sha256=source_image.checksum_sha256,
        source_paths=source_paths,
        source_width=source_width,
        source_height=source_height,
        source_mode=source_mode,
        exif_orientation=orientation,
        orientation_action=("none" if orientation is None else ORIENTATION_ACTIONS[orientation]),
        normalized_width=normalized_width,
        normalized_height=normalized_height,
        normalized_checksum_sha256=normalized_checksum,
        normalized_relative_path=normalized_relative,
        diagnostic_relative_path=diagnostic_relative,
    )
    _write_immutable(
        _artifact_path(artifact_root, normalized_relative),
        normalized_png,
    )
    _write_immutable(
        _artifact_path(artifact_root, diagnostic_relative),
        _diagnostic_bytes(normalized),
    )
    return normalized


def normalize_images(
    source_root: Path,
    discovery_manifest_path: Path,
    artifact_root: Path,
    *,
    max_source_pixels: int = MAX_SOURCE_PIXELS,
) -> NormalizationReport:
    """Normalize every unique discovered image into immutable working artifacts."""

    if max_source_pixels < 1:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_PIXEL_LIMIT_INVALID",
            "Pixel limit must be a positive integer.",
        )
    source, artifacts = _validate_roots(source_root, artifact_root)
    manifest_bytes, discovered = _load_and_verify_discovery_manifest(
        source, discovery_manifest_path
    )
    if discovered.issues:
        raise ImageNormalizationError(
            "IMAGE_NORMALIZATION_DISCOVERY_ISSUES",
            "Source discovery manifest contains unresolved image issues.",
        )

    images: list[NormalizedImage] = []
    issues: list[NormalizationIssue] = []
    for source_image in discovered.images:
        try:
            images.append(
                _normalize_one(
                    source,
                    artifacts,
                    source_image,
                    max_source_pixels=max_source_pixels,
                )
            )
        except ImageNormalizationError as error:
            issues.append(
                NormalizationIssue(
                    code=error.code,
                    source_checksum_sha256=source_image.checksum_sha256,
                    source_relative_path=source_image.files[0].relative_path,
                    message=str(error),
                )
            )
    return NormalizationReport(
        source_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        images=tuple(images),
        issues=tuple(issues),
    )
