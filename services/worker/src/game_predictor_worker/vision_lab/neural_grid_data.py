"""Snapshot reading behind the role guard, shared geometry, augmentations and targets.

Torch-free: the training dataset is a plain map-style object that ``torch.utils.data``
accepts, so the ONNX engine and the tests import this module without torch.

Coordinates are ``exif-normalized-rgb-pixels-v1`` source pixels. Node order is row-major
on the 6 x 4 lattice of a 5 x 3 board: node ``r * 6 + c``; corners are nodes 0, 5, 23, 18
(TL, TR, BR, BL).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

from game_predictor_worker.geometry_core.preprocessing import (
    board_rectifier as board_rectifier,
)
from game_predictor_worker.geometry_core.preprocessing import (
    corners as corners,
)
from game_predictor_worker.geometry_core.preprocessing import (
    crop_board as crop_board,
)
from game_predictor_worker.geometry_core.preprocessing import (
    grid_from_quad as grid_from_quad,
)
from game_predictor_worker.geometry_core.preprocessing import (
    lattice_homography as lattice_homography,
)
from game_predictor_worker.geometry_core.preprocessing import (
    quad_centre as quad_centre,
)
from game_predictor_worker.geometry_core.preprocessing import (
    quad_is_usable as quad_is_usable,
)
from game_predictor_worker.geometry_core.preprocessing import (
    screen_geometry as screen_geometry,
)
from game_predictor_worker.geometry_core.preprocessing import (
    screen_input as screen_input,
)
from game_predictor_worker.geometry_core.preprocessing import (
    transform_points as transform_points,
)

from ..training_core.neural_grid_augmentation import (
    build_board_crop as build_board_crop,
)
from ..training_core.neural_grid_augmentation import (
    build_screen_item as build_screen_item,
)
from ..training_core.neural_grid_augmentation import (
    build_training_item as build_training_item,
)
from ..training_core.neural_grid_augmentation import (
    perturb_quad as perturb_quad,
)
from ..training_core.neural_grid_augmentation import (
    photometric as photometric,
)
from ..training_core.neural_grid_augmentation import (  # moved in TASK-0996
    random_homography as random_homography,
)
from ..training_core.neural_grid_augmentation import (
    screen_targets as screen_targets,
)
from .neural_grid_protocol import (
    COORDINATE_SPACE as COORDINATE_SPACE,
)
from .neural_grid_protocol import (
    SNAPSHOT_FORMAT as SNAPSHOT_FORMAT,
)
from .neural_grid_protocol import (
    SNAPSHOT_POLICY as SNAPSHOT_POLICY,
)
from .neural_grid_protocol import (
    AugmentationPreset as AugmentationPreset,
)
from .neural_grid_protocol import (
    BoardPreset as BoardPreset,
)
from .neural_grid_protocol import (
    Preset as Preset,
)
from .neural_grid_protocol import (
    RoleForbiddenError as RoleForbiddenError,
)
from .neural_grid_protocol import (
    ScreenPreset as ScreenPreset,
)
from .neural_grid_protocol import (
    require_roles as require_roles,
)
from .snapshot import safe_file as safe_file

FloatArray = NDArray[np.float32]
ByteImage = NDArray[np.uint8]

LATTICE: Final = np.array([(c, r) for r in range(4) for c in range(6)], dtype=np.float32)
CORNERS: Final = (0, 5, 23, 18)
CELL_COUNT: Final = 15
PAD_VALUE: Final = 114
_IMAGE_ID = re.compile(rb'"imageId"\s*:\s*"([^"]+)"')


@dataclass(frozen=True, slots=True)
class BoardLabel:
    nodes: FloatArray  # (24, 2)
    unavailable_cells: tuple[int, ...]
    level: str


@dataclass(frozen=True, slots=True)
class PhotoSample:
    image_id: str
    role: str
    level: str
    path: Path
    sha256: str
    width: int
    height: int
    family_id: str
    boards: tuple[BoardLabel, ...]


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    root: Path
    snapshot_id: str
    files: dict[str, str]


def open_snapshot(root: Path) -> SnapshotInfo:
    manifest = json.loads(safe_file(root, "manifest.json").read_bytes())
    if manifest.get("format") != SNAPSHOT_FORMAT:
        raise ValueError("SNAPSHOT_FORMAT_UNSUPPORTED")
    if manifest.get("policy", {}).get("policyVersion") != SNAPSHOT_POLICY:
        raise ValueError("NEURAL_GRID_SNAPSHOT_POLICY_MISMATCH")
    if root.name != manifest.get("snapshotId"):
        raise ValueError("SNAPSHOT_IDENTITY_MISMATCH")
    return SnapshotInfo(root, str(manifest["snapshotId"]), dict(manifest["files"]))


def _selection_roles(info: SnapshotInfo) -> dict[str, tuple[str, str, str]]:
    path = safe_file(info.root, "split.json")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != info.files.get("split.json"):
        raise ValueError("SNAPSHOT_CHECKSUM_MISMATCH")
    document = json.loads(content)
    if document.get("selectionColumns") != ["imageId", "role", "sourceChecksumSha256", "suffix"]:
        raise ValueError("SNAPSHOT_SPLIT_FORMAT_UNSUPPORTED")
    return {str(row[0]): (str(row[1]), str(row[2]), str(row[3])) for row in document["selection"]}


def load_samples(root: Path, roles: Iterable[str]) -> list[PhotoSample]:
    """Samples of the allowed roles only (guard first, before any file is opened).

    ``samples.jsonl`` holds every role in one file. Lines are hashed for the integrity
    check, but a line is JSON-decoded only after its ``imageId`` resolved, through
    ``split.json``, to an allowed role; no image of another role is ever opened.
    """

    allowed = require_roles(tuple(roles))
    info = open_snapshot(root)
    selection = _selection_roles(info)
    digest = hashlib.sha256()
    result: list[PhotoSample] = []
    with safe_file(root, "samples.jsonl").open("rb") as stream:
        for line in stream:
            digest.update(line)
            match = _IMAGE_ID.search(line)
            if match is None:
                if line.strip():
                    raise ValueError("SNAPSHOT_SAMPLE_INVALID")
                continue
            image_id = match.group(1).decode()
            role, checksum, suffix = selection.get(image_id, ("", "", ""))
            if role not in allowed:
                continue
            row = json.loads(line)
            if row["imageId"] != image_id or row["role"] != role:
                raise ValueError("SNAPSHOT_ROLE_MISMATCH")
            if row["coordinateSpace"] != COORDINATE_SPACE:
                raise ValueError("SNAPSHOT_COORDINATE_SPACE_UNSUPPORTED")
            relative = f"images/{checksum[:2]}/{checksum}{suffix}"
            if row["imagePath"] != relative or row["sourceChecksumSha256"] != checksum:
                raise ValueError("SNAPSHOT_IMAGE_NOT_REGISTERED")
            boards = tuple(
                BoardLabel(
                    np.asarray(board["nodes"], dtype=np.float32).reshape(24, 2),
                    tuple(int(i) for i in board["unavailableCellIndices"]),
                    str(board["level"]),
                )
                for board in row["boards"]
            )
            result.append(
                PhotoSample(
                    image_id=image_id,
                    role=role,
                    level=str(row["imageLevel"]),
                    path=safe_file(root, relative),
                    sha256=checksum,
                    width=int(row["orientedWidth"]),
                    height=int(row["orientedHeight"]),
                    family_id=str(row["familyId"]),
                    boards=boards,
                )
            )
    if digest.hexdigest() != info.files.get("samples.jsonl"):
        raise ValueError("SNAPSHOT_CHECKSUM_MISMATCH")
    for sample in result:
        if sample.role not in allowed:
            raise RoleForbiddenError("NEURAL_GRID_ROLE_FORBIDDEN")
    result.sort(key=lambda item: item.image_id)
    return result


def verify_images(samples: list[PhotoSample], files: dict[str, str], workers: int = 8) -> None:
    """SHA-256 of every allowed image against the snapshot manifest (bytes only)."""

    def check(sample: PhotoSample) -> str | None:
        relative = sample.path.relative_to(sample.path.parents[2]).as_posix()
        if files.get(relative) != sample.sha256:
            return f"{sample.image_id}:SNAPSHOT_IMAGE_NOT_REGISTERED"
        with sample.path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != sample.sha256:
                return f"{sample.image_id}:SNAPSHOT_CHECKSUM_MISMATCH"
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        errors = [error for error in pool.map(check, samples) if error]
    if errors:
        raise ValueError(f"SNAPSHOT_IMAGE_INTEGRITY:{errors[:5]}")


def read_rgb(sample: PhotoSample) -> ByteImage:
    # cv2 applies the EXIF orientation by default, matching exif-normalized coordinates.
    bgr = cv2.imread(str(sample.path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("IMAGE_DECODE_FAILED")
    if bgr.shape[:2] != (sample.height, sample.width):
        raise ValueError("ORIENTED_SIZE_MISMATCH")
    return np.ascontiguousarray(bgr[:, :, ::-1])


# --- geometry shared by training and inference --------------------------------------------


class TrainingDataset:
    """Map-style dataset; each item is one augmented photo plus k rectified board crops."""

    def __init__(self, samples: list[PhotoSample], preset: Preset, seed: int) -> None:
        self.samples = samples
        self.preset = preset
        self.seed = seed
        self.calls = 0

    def __len__(self) -> int:
        return len(self.samples)

    def _rng(self, index: int) -> np.random.Generator:
        worker_seed = 0
        try:
            from torch.utils.data import get_worker_info

            info = get_worker_info()
            if info is not None:
                worker_seed = int(info.seed) % (2**63)
        except ImportError:
            pass
        self.calls += 1
        return np.random.default_rng([self.seed, worker_seed, index, self.calls])

    def __getitem__(self, index: int) -> dict[str, Any]:
        sample = self.samples[index]
        rng = self._rng(index)
        return build_training_item(read_rgb(sample), sample, self.preset, rng)


def prefetch(
    samples: list[PhotoSample], workers: int = 4
) -> Iterable[tuple[PhotoSample, ByteImage | Exception]]:
    """Ordered decode with a small thread pool (cv2 releases the GIL)."""

    def load(sample: PhotoSample) -> ByteImage | Exception:
        try:
            return read_rgb(sample)
        except (ValueError, OSError, cv2.error) as error:
            return error

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(load, sample) for sample in samples[: workers * 2]]
        for index, sample in enumerate(samples):
            result = futures[index].result()
            following = index + workers * 2
            if following < len(samples):
                futures.append(pool.submit(load, samples[following]))
            yield sample, result


Heartbeat = Callable[[], None]
