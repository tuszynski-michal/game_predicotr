"""Deterministic EXIF normalization into immutable local working artifacts."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps, UnidentifiedImageError
from PIL import __version__ as pillow_version

from game_predictor_worker.images.discovery import (
    SourceImage,
    SourceManifest,
    discover_images,
)
from game_predictor_worker.images.image_file import ImageFileError, sha256_file

NORMALIZATION_VERSION = "image-normalization-v1"
MAX_SOURCE_PIXELS = 50_000_000
ORIENTATION_TAG = 274
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
