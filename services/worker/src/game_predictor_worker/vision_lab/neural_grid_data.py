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
import math
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

from .neural_grid_protocol import (
    COORDINATE_SPACE,
    SNAPSHOT_FORMAT,
    SNAPSHOT_POLICY,
    AugmentationPreset,
    BoardPreset,
    Preset,
    RoleForbiddenError,
    ScreenPreset,
    require_roles,
)
from .snapshot import safe_file

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


def corners(nodes: FloatArray) -> FloatArray:
    return np.asarray(nodes, dtype=np.float32)[list(CORNERS)]


def lattice_homography(quad: FloatArray) -> NDArray[np.float64]:
    return np.asarray(
        cv2.getPerspectiveTransform(LATTICE[list(CORNERS)], np.asarray(quad, np.float32)),
        dtype=np.float64,
    )


def grid_from_quad(quad: FloatArray) -> FloatArray:
    """24 projective nodes of a quad (the snapshot labels are exactly this, residual 1e-4 px)."""

    return transform_points(LATTICE, lattice_homography(quad))


def quad_centre(quad: FloatArray) -> FloatArray:
    centre = transform_points(np.array([[2.5, 1.5]], np.float32), lattice_homography(quad))
    return np.asarray(centre[0], dtype=np.float32)


def transform_points(points: FloatArray, matrix: NDArray[np.float64]) -> FloatArray:
    values = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.concatenate([values, np.ones((len(values), 1))], axis=1) @ matrix.T
    w = homogeneous[:, 2:3]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    return np.asarray(homogeneous[:, :2] / w, dtype=np.float32)


def quad_is_usable(quad: FloatArray, min_area: float = 16.0) -> bool:
    quad = np.asarray(quad, dtype=np.float32)
    return (
        bool(np.isfinite(quad).all())
        and bool(cv2.isContourConvex(quad.reshape(-1, 1, 2)))
        and float(cv2.contourArea(quad, oriented=True)) > min_area
    )


def screen_geometry(width: int, height: int, long_side: int, pad: int) -> tuple[int, int, int, int]:
    """Resized size and padded canvas size of the screen stage."""

    scale = long_side / max(width, height)
    resized_w = max(1, round(width * scale))
    resized_h = max(1, round(height * scale))
    return (
        resized_w,
        resized_h,
        int(math.ceil(resized_w / pad) * pad),
        int(math.ceil(resized_h / pad) * pad),
    )


def screen_input(rgb: ByteImage, screen: ScreenPreset) -> tuple[ByteImage, float, float]:
    """Inference preprocessing: area resize to the long side, pad right/bottom to 32."""

    height, width = rgb.shape[:2]
    resized_w, resized_h, canvas_w, canvas_h = screen_geometry(
        width, height, screen.long_side, screen.pad_multiple
    )
    canvas = np.full((canvas_h, canvas_w, 3), PAD_VALUE, dtype=np.uint8)
    canvas[:resized_h, :resized_w] = cv2.resize(
        rgb, (resized_w, resized_h), interpolation=cv2.INTER_AREA
    )
    return canvas, resized_w / width, resized_h / height


def board_rectifier(quad: FloatArray, board: BoardPreset) -> NDArray[np.float64]:
    """Homography source -> crop; the quad lands on the inner rectangle (margin per side)."""

    width, height = board.canvas
    left = width * board.margin / (1 + 2 * board.margin)
    top = height * board.margin / (1 + 2 * board.margin)
    target = np.array(
        [[left, top], [width - left, top], [width - left, height - top], [left, height - top]],
        dtype=np.float32,
    )
    return np.asarray(
        cv2.getPerspectiveTransform(np.asarray(quad, np.float32), target), dtype=np.float64
    )


def crop_board(rgb: ByteImage, matrix: NDArray[np.float64], board: BoardPreset) -> ByteImage:
    return np.asarray(
        cv2.warpPerspective(
            rgb,
            matrix,
            tuple(board.canvas),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(PAD_VALUE, PAD_VALUE, PAD_VALUE),
        ),
        dtype=np.uint8,
    )


# --- augmentations ---------------------------------------------------------------------------


def random_homography(
    width: int, height: int, augmentation: AugmentationPreset, rng: np.random.Generator
) -> NDArray[np.float64]:
    """Similarity (scale, rotation, translation) plus per-corner perspective jitter."""

    centre = np.array([width / 2, height / 2])
    scale = rng.uniform(*augmentation.scale_range)
    angle = math.radians(rng.uniform(-augmentation.rotation_degrees, augmentation.rotation_degrees))
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    shift = rng.uniform(-augmentation.translate, augmentation.translate, 2) * [width, height]
    source = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float64)
    moved = (source - centre) @ (rotation * scale).T + centre + shift
    moved += rng.uniform(-augmentation.perspective, augmentation.perspective, (4, 2)) * [
        width,
        height,
    ]
    return np.asarray(
        cv2.getPerspectiveTransform(source.astype(np.float32), moved.astype(np.float32)),
        dtype=np.float64,
    )


def _color(image: FloatArray, augmentation: AugmentationPreset, rng: np.random.Generator) -> None:
    hsv = cv2.cvtColor(np.clip(image, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(
        np.float32
    )
    hsv[..., 0] = (hsv[..., 0] + rng.uniform(-1, 1) * augmentation.hue_degrees / 2) % 180
    hsv[..., 1] *= 1 + rng.uniform(-augmentation.saturation, augmentation.saturation)
    rgb = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
    contrast = 1 + rng.uniform(-augmentation.contrast, augmentation.contrast)
    brightness = 1 + rng.uniform(-augmentation.brightness, augmentation.brightness)
    mean = rgb.mean()
    image[...] = ((rgb - mean) * contrast + mean) * brightness


def _glare(image: FloatArray, augmentation: AugmentationPreset, rng: np.random.Generator) -> None:
    height, width = image.shape[:2]
    short = min(height, width)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    for _ in range(int(rng.integers(1, augmentation.glare_max_count + 1))):
        radius = rng.uniform(*augmentation.glare_radius_range) * short
        cx, cy = rng.uniform(0, width), rng.uniform(0, height)
        stretch = rng.uniform(0.5, 2.0)
        blob = np.exp(-(((xs - cx) / stretch) ** 2 + ((ys - cy) * stretch) ** 2) / (2 * radius**2))
        strength = rng.uniform(*augmentation.glare_strength_range)
        tint = np.array([255, 255, rng.uniform(220, 255)], dtype=np.float32)
        image += (tint - image) * (blob * strength)[..., None]


def _occlusion(
    image: FloatArray, augmentation: AugmentationPreset, rng: np.random.Generator
) -> None:
    height, width = image.shape[:2]
    short = min(height, width)
    for _ in range(int(rng.integers(1, augmentation.occlusion_max_count + 1))):
        w = rng.uniform(*augmentation.occlusion_size_range) * short * rng.uniform(0.6, 1.6)
        h = rng.uniform(*augmentation.occlusion_size_range) * short * rng.uniform(0.6, 1.6)
        cx, cy = rng.uniform(0, width), rng.uniform(0, height)
        box = cv2.boxPoints(((cx, cy), (w, h), rng.uniform(0, 180))).astype(np.int32)
        if rng.random() < 0.5:
            color = rng.uniform(0, 255, 3)
            cv2.fillConvexPoly(image, box, color.tolist())
        else:
            mask = np.zeros((height, width), np.uint8)
            cv2.fillConvexPoly(mask, box, 1)
            noise = rng.uniform(0, 255, (height, width, 3)).astype(np.float32)
            noise = np.asarray(cv2.GaussianBlur(noise, (0, 0), 2.0), np.float32)
            image[mask > 0] = noise[mask > 0]


def _pt(point: NDArray[np.float64]) -> tuple[int, int]:
    return int(round(float(point[0]))), int(round(float(point[1])))


def _hand(image: FloatArray, augmentation: AugmentationPreset, rng: np.random.Generator) -> None:
    """Palm ellipse plus four fingers and a thumb in a skin tone, with soft shading."""

    height, width = image.shape[:2]
    size = rng.uniform(*augmentation.hand_size_range) * min(height, width)
    mask = np.zeros((height, width), np.uint8)
    cx, cy = rng.uniform(0, width), rng.uniform(0, height)
    angle = rng.uniform(0, 2 * math.pi)
    direction = np.array([math.cos(angle), math.sin(angle)])
    normal = np.array([-direction[1], direction[0]])
    palm = (int(cx), int(cy))
    cv2.ellipse(
        mask,
        palm,
        (max(1, int(size * 0.45)), max(1, int(size * 0.55))),
        math.degrees(angle) + 90,
        0,
        360,
        1,
        -1,
    )
    thickness = max(2, int(size * 0.16))
    for index in range(4):
        base = np.array([cx, cy]) + direction * size * 0.45 + normal * size * (index - 1.5) * 0.2
        tip = base + direction * size * rng.uniform(0.45, 0.75)
        cv2.line(mask, _pt(base), _pt(tip), 1, thickness)
        cv2.circle(mask, _pt(tip), thickness // 2, 1, -1)
    thumb_base = np.array([cx, cy]) - normal * size * 0.4
    thumb_tip = thumb_base - normal * size * 0.4 + direction * size * 0.25
    cv2.line(mask, _pt(thumb_base), _pt(thumb_tip), 1, thickness)
    skin = np.array(
        [rng.uniform(170, 240), rng.uniform(110, 185), rng.uniform(80, 150)], dtype=np.float32
    )
    shade = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), max(1.0, size * 0.08))
    layer = skin * (0.75 + 0.25 * shade[..., None])
    image[mask > 0] = layer[mask > 0]


def photometric(
    image: ByteImage, augmentation: AugmentationPreset, rng: np.random.Generator
) -> ByteImage:
    work = image.astype(np.float32)
    if rng.random() < augmentation.color_probability:
        _color(work, augmentation, rng)
    if augmentation.glare_max_count and rng.random() < augmentation.glare_probability:
        _glare(work, augmentation, rng)
    if augmentation.occlusion_max_count and rng.random() < augmentation.occlusion_probability:
        _occlusion(work, augmentation, rng)
    if rng.random() < augmentation.hand_probability:
        _hand(work, augmentation, rng)
    if rng.random() < augmentation.blur_probability:
        work = np.asarray(
            cv2.GaussianBlur(
                work, (0, 0), rng.uniform(0.3, max(0.31, augmentation.blur_max_sigma))
            ),
            np.float32,
        )
    if rng.random() < augmentation.noise_probability:
        work += rng.normal(0, rng.uniform(0, augmentation.noise_max_std), work.shape).astype(
            np.float32
        )
    result = np.clip(work, 0, 255).astype(np.uint8)
    if rng.random() < augmentation.jpeg_probability:
        quality = int(
            rng.integers(augmentation.jpeg_quality_range[0], augmentation.jpeg_quality_range[1] + 1)
        )
        ok, encoded = cv2.imencode(".jpg", result[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, quality])
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR) if ok else None
        if decoded is not None:
            result = np.ascontiguousarray(decoded[:, :, ::-1], dtype=np.uint8)
    return result


# --- targets -----------------------------------------------------------------------------------


def screen_targets(
    quads: list[FloatArray], canvas_size: tuple[int, int], screen: ScreenPreset
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """CenterNet heatmap (peak 1 at the integer centre cell) and corner offsets.

    Offsets are supervised at every cell whose Gaussian value of its owning board is at
    least ``positive_radius``; they point from the cell centre ``stride * (j + 0.5)`` to the
    four corners, divided by ``offset_scale``. Boards whose centre is outside the map are
    not targets.
    """

    width, height = canvas_size
    stride = screen.stride
    map_w, map_h = width // stride, height // stride
    heat = np.zeros((map_h, map_w), np.float32)
    owner = np.zeros((map_h, map_w), np.float32)
    offsets = np.zeros((8, map_h, map_w), np.float32)
    weight = np.zeros((map_h, map_w), np.float32)
    ys, xs = np.mgrid[0:map_h, 0:map_w].astype(np.float32)
    cell_x = (xs + 0.5) * stride
    cell_y = (ys + 0.5) * stride
    for quad in quads:
        if not quad_is_usable(quad):
            continue
        centre = quad_centre(quad) / stride - 0.5
        cx, cy = int(round(float(centre[0]))), int(round(float(centre[1])))
        if not (0 <= cx < map_w and 0 <= cy < map_h):
            continue
        extent_w = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
        extent_h = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
        sigma = max(
            screen.min_heat_sigma,
            screen.heat_sigma_fraction * min(float(extent_w), float(extent_h)) / stride,
        )
        gaussian = np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * sigma**2)).astype(np.float32)
        np.maximum(heat, gaussian, out=heat)
        take = (gaussian >= screen.positive_radius) & (gaussian > owner)
        owner[take] = gaussian[take]
        for k in range(4):
            offsets[2 * k][take] = (quad[k, 0] - cell_x[take]) / screen.offset_scale
            offsets[2 * k + 1][take] = (quad[k, 1] - cell_y[take]) / screen.offset_scale
        weight[take] = gaussian[take]
    return heat[None], offsets, weight[None]


def perturb_quad(quad: FloatArray, board: BoardPreset, rng: np.random.Generator) -> FloatArray:
    """Label quad with stage-1-like error: global similarity jitter plus per-corner noise."""

    diagonal = float(np.linalg.norm(quad[2] - quad[0]))
    centre = quad.mean(axis=0)
    angle = math.radians(rng.uniform(-board.rotation_jitter_degrees, board.rotation_jitter_degrees))
    scale = 1 + rng.uniform(-board.scale_jitter, board.scale_jitter)
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    moved = (quad - centre) @ (rotation * scale).T + centre
    moved += rng.uniform(-board.shift_jitter, board.shift_jitter, 2) * diagonal
    moved += rng.normal(0, board.corner_jitter, (4, 2)) * diagonal
    return np.asarray(moved, dtype=np.float32)


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


def build_training_item(
    rgb: ByteImage, sample: PhotoSample, preset: Preset, rng: np.random.Generator
) -> dict[str, Any]:
    screen, board, augmentation = preset.screen, preset.board, preset.augmentation
    height, width = rgb.shape[:2]
    canvas_w, canvas_h = screen.train_canvas
    resized_w, resized_h, _, _ = screen_geometry(
        width, height, screen.long_side, screen.pad_multiple
    )
    resized = cv2.resize(rgb, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    scale = np.diag([resized_w / width, resized_h / height, 1.0])
    warp = random_homography(canvas_w, canvas_h, augmentation, rng)
    warped = cv2.warpPerspective(
        resized,
        warp,
        (canvas_w, canvas_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(PAD_VALUE, PAD_VALUE, PAD_VALUE),
    )
    canvas = photometric(np.asarray(warped, dtype=np.uint8), augmentation, rng)
    to_canvas = warp @ scale
    quads = [transform_points(corners(label.nodes), to_canvas) for label in sample.boards]
    heat, offsets, weight = screen_targets(quads, (canvas_w, canvas_h), screen)

    chosen = rng.choice(
        len(sample.boards), size=min(board.boards_per_image, len(sample.boards)), replace=False
    )
    crops, nodes, visible = [], [], []
    for index in chosen:
        label = sample.boards[int(index)]
        quad = perturb_quad(corners(label.nodes), board, rng)
        if not quad_is_usable(quad):
            quad = corners(label.nodes)
        matrix = board_rectifier(quad, board)
        crops.append(photometric(crop_board(rgb, matrix, board), augmentation, rng))
        nodes.append(transform_points(label.nodes, matrix))
        mask = np.ones(CELL_COUNT, np.float32)
        mask[list(label.unavailable_cells)] = 0
        visible.append(mask)
    while len(crops) < board.boards_per_image:  # fewer boards than k: repeat the first crop
        crops.append(crops[0])
        nodes.append(nodes[0])
        visible.append(visible[0])
    return {
        "image": np.ascontiguousarray(canvas.transpose(2, 0, 1)),
        "heat": heat,
        "offsets": offsets,
        "offset_weight": weight,
        "crops": np.ascontiguousarray(np.stack(crops).transpose(0, 3, 1, 2)),
        "nodes": np.stack(nodes).astype(np.float32),
        "visible": np.stack(visible),
    }


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
