"""Immutable, source-disjoint training contract for keypoint geometry."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import numpy as np
from game_predictor_api.domain.image_geometry_v2 import (
    SourceQuad,
    canonical_json_bytes,
)
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

KEYPOINT_GEOMETRY_DATASET_VERSION = "keypoint-geometry-approved-quads-v1"
KEYPOINT_GEOMETRY_SPLIT_VERSION = "keypoint-source-family-disjoint-v1"
KEYPOINT_GEOMETRY_SPLIT_SEED = "game-predictor-keypoint-geometry-v1"

type KeypointSplit = Literal["train", "validation", "test"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SPLITS: tuple[KeypointSplit, ...] = ("train", "validation", "test")


class KeypointGeometryDatasetError(ValueError):
    """Stable rejection before an image can enter geometry training."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ApprovedKeypointGeometrySample:
    """One immutable source whose active quads were approved by a human."""

    sample_id: str
    source_family_id: str
    source_checksum_sha256: str
    source_relative_path: str
    canonical_width: int
    canonical_height: int
    active_board_slots: tuple[int, ...]
    approved_quads: tuple[SourceQuad, ...]
    approval_kind: Literal["manual_approved"]

    def __post_init__(self) -> None:
        if not self.sample_id.strip() or not self.source_family_id.strip():
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_SAMPLE_IDENTITY_INVALID",
                "A keypoint sample requires stable sample and source-family identities.",
            )
        if _SHA256.fullmatch(self.source_checksum_sha256) is None:
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_SOURCE_CHECKSUM_INVALID",
                "A keypoint sample requires a lowercase source SHA-256.",
            )
        path = PurePosixPath(self.source_relative_path.replace("\\", "/"))
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or ":" in path.parts[0]
        ):
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_SOURCE_PATH_UNSAFE",
                "A keypoint sample path must be a safe managed relative path.",
            )
        if self.canonical_width < 1 or self.canonical_height < 1:
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_SOURCE_DIMENSIONS_INVALID",
                "A keypoint sample requires positive canonical dimensions.",
            )
        if self.active_board_slots != tuple(range(len(self.active_board_slots))) or not (
            1 <= len(self.active_board_slots) <= 9
        ):
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_ACTIVE_SLOTS_INVALID",
                "Active keypoint slots must be a non-empty row-major prefix of nine slots.",
            )
        if len(self.approved_quads) != len(self.active_board_slots):
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_QUADS_INCOMPLETE",
                "Every active keypoint slot requires one manually approved quad.",
            )
        for quad in self.approved_quads:
            if any(
                point.x < 0
                or point.x > self.canonical_width
                or point.y < 0
                or point.y > self.canonical_height
                for point in quad.corners
            ):
                raise KeypointGeometryDatasetError(
                    "KEYPOINT_GEOMETRY_QUAD_OUT_OF_BOUNDS",
                    "Approved keypoint quads must lie inside the canonical source.",
                )

    def to_payload(self, *, split: KeypointSplit) -> dict[str, object]:
        return {
            "activeBoardSlots": list(self.active_board_slots),
            "approvalKind": self.approval_kind,
            "approvedQuads": [quad.to_dict() for quad in self.approved_quads],
            "canonicalHeight": self.canonical_height,
            "canonicalWidth": self.canonical_width,
            "sampleId": self.sample_id,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceFamilyId": self.source_family_id,
            "sourceRelativePath": PurePosixPath(
                self.source_relative_path.replace("\\", "/")
            ).as_posix(),
            "split": split,
        }


@dataclass(frozen=True, slots=True)
class FrozenKeypointGeometryDataset:
    samples: tuple[tuple[ApprovedKeypointGeometrySample, KeypointSplit], ...]
    manifest_checksum_sha256: str
    split_seed: str
    dataset_version: str = KEYPOINT_GEOMETRY_DATASET_VERSION
    split_version: str = KEYPOINT_GEOMETRY_SPLIT_VERSION

    def to_payload(self) -> dict[str, object]:
        return {
            "datasetVersion": self.dataset_version,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
            "samples": [sample.to_payload(split=split) for sample, split in self.samples],
            "splitSeed": self.split_seed,
            "splitVersion": self.split_version,
        }

    def samples_for(self, split: KeypointSplit) -> tuple[ApprovedKeypointGeometrySample, ...]:
        return tuple(sample for sample, assigned in self.samples if assigned == split)


def freeze_keypoint_geometry_dataset(
    samples: tuple[ApprovedKeypointGeometrySample, ...],
    *,
    split_seed: str = KEYPOINT_GEOMETRY_SPLIT_SEED,
) -> FrozenKeypointGeometryDataset:
    """Freeze human-approved quads with stable source-family split assignment."""

    if not split_seed.strip():
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SPLIT_SEED_INVALID",
            "The keypoint split seed cannot be empty.",
        )
    if not samples:
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_COHORT_EMPTY",
            "At least one manually approved keypoint sample is required.",
        )
    sample_ids: set[str] = set()
    source_families_by_checksum: dict[str, str] = {}
    for sample in samples:
        if sample.approval_kind != "manual_approved":
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_APPROVAL_REQUIRED",
                "Only manually approved source quads may enter keypoint training.",
            )
        if sample.sample_id in sample_ids:
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_SAMPLE_DUPLICATE",
                "Keypoint sample identities must be unique.",
            )
        sample_ids.add(sample.sample_id)
        existing_family = source_families_by_checksum.get(sample.source_checksum_sha256)
        if existing_family is not None:
            code = (
                "KEYPOINT_GEOMETRY_SOURCE_DUPLICATE"
                if existing_family == sample.source_family_id
                else "KEYPOINT_GEOMETRY_SOURCE_FAMILY_CONFLICT"
            )
            raise KeypointGeometryDatasetError(
                code,
                "Identical source bytes may enter the frozen keypoint cohort only once.",
            )
        source_families_by_checksum[sample.source_checksum_sha256] = sample.source_family_id

    families = sorted({sample.source_family_id for sample in samples})
    if len(families) < 3:
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_FAMILIES_INSUFFICIENT",
            "Keypoint training requires at least three source families for disjoint splits.",
        )
    assignments = _source_family_assignments(families, split_seed=split_seed)
    ordered = tuple(
        (sample, assignments[sample.source_family_id])
        for sample in sorted(samples, key=lambda value: value.sample_id)
    )
    payload = {
        "datasetVersion": KEYPOINT_GEOMETRY_DATASET_VERSION,
        "samples": [sample.to_payload(split=split) for sample, split in ordered],
        "splitSeed": split_seed,
        "splitVersion": KEYPOINT_GEOMETRY_SPLIT_VERSION,
    }
    checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return FrozenKeypointGeometryDataset(
        samples=ordered,
        manifest_checksum_sha256=checksum,
        split_seed=split_seed,
    )


def load_approved_keypoint_source(
    data_root: Path,
    sample: ApprovedKeypointGeometrySample,
) -> NDArray[np.uint8]:
    """Read one immutable managed JPEG and apply EXIF exactly once for training."""

    try:
        root = data_root.resolve(strict=True)
        candidate = root.joinpath(
            *PurePosixPath(sample.source_relative_path.replace("\\", "/")).parts
        )
        if candidate.is_symlink():
            raise KeypointGeometryDatasetError(
                "KEYPOINT_GEOMETRY_SOURCE_PATH_UNSAFE",
                "The approved keypoint source cannot be a symlink.",
            )
        source = candidate.resolve(strict=True)
    except KeypointGeometryDatasetError:
        raise
    except OSError as error:
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_MISSING",
            "The approved keypoint source is unavailable.",
        ) from error
    if not source.is_relative_to(root) or not source.is_file():
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_PATH_UNSAFE",
            "The approved keypoint source resolves outside managed storage.",
        )
    digest = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_MISSING",
            "The approved keypoint source cannot be read.",
        ) from error
    if digest.hexdigest() != sample.source_checksum_sha256:
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_CHECKSUM_MISMATCH",
            "The approved keypoint source differs from the frozen manifest.",
        )
    try:
        with Image.open(source) as image:
            if image.format != "JPEG":
                raise KeypointGeometryDatasetError(
                    "KEYPOINT_GEOMETRY_SOURCE_FORMAT_UNSUPPORTED",
                    "Keypoint training currently accepts managed JPEG sources only.",
                )
            image.load()
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_DECODE_FAILED",
            "The approved keypoint source cannot be decoded.",
        ) from error
    if rgb.shape != (sample.canonical_height, sample.canonical_width, 3):
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_SOURCE_DIMENSIONS_MISMATCH",
            "The approved keypoint source dimensions differ from the frozen manifest.",
        )
    return np.ascontiguousarray(rgb)


def _source_family_assignments(
    families: list[str],
    *,
    split_seed: str,
) -> dict[str, KeypointSplit]:
    ranked = sorted(
        families,
        key=lambda value: hashlib.sha256(f"{split_seed}\0{value}".encode()).hexdigest(),
    )
    validation_count = max(1, len(ranked) // 10)
    test_count = max(1, len(ranked) // 10)
    assignments: dict[str, KeypointSplit] = {}
    for family in ranked[:validation_count]:
        assignments[family] = "validation"
    for family in ranked[validation_count : validation_count + test_count]:
        assignments[family] = "test"
    for family in ranked[validation_count + test_count :]:
        assignments[family] = "train"
    return assignments


__all__ = [
    "KEYPOINT_GEOMETRY_DATASET_VERSION",
    "KEYPOINT_GEOMETRY_SPLIT_SEED",
    "KEYPOINT_GEOMETRY_SPLIT_VERSION",
    "ApprovedKeypointGeometrySample",
    "FrozenKeypointGeometryDataset",
    "KeypointGeometryDatasetError",
    "KeypointSplit",
    "freeze_keypoint_geometry_dataset",
    "load_approved_keypoint_source",
]
