"""Neural-grid augmentation and training items shared by the laboratory and the application.

Moved unchanged from ``vision_lab/neural_grid_data.py`` (TASK-0996). The preset arguments are
duck-typed: any object with the attributes of the laboratory presets works, so the module has
no laboratory import. The laboratory module re-exports these names.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

from ..geometry_core.preprocessing import (
    board_rectifier,
    corners,
    crop_board,
    quad_centre,
    quad_is_usable,
    screen_geometry,
    transform_points,
)

FloatArray = NDArray[np.float32]
ByteImage = NDArray[np.uint8]
AugmentationPreset = Any
BoardPreset = Any
ScreenPreset = Any

CELL_COUNT: Final = 15
PAD_VALUE: Final = 114


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


def build_training_item(
    rgb: ByteImage, sample: Any, preset: Any, rng: np.random.Generator
) -> dict[str, Any]:
    """Laboratory signature: ``sample.boards`` carry ``nodes`` and ``unavailable_cells``."""
    return build_screen_item(
        rgb,
        [(label.nodes, tuple(label.unavailable_cells)) for label in sample.boards],
        preset.screen,
        preset.board,
        preset.augmentation,
        rng,
    )


def build_screen_item(
    rgb: ByteImage,
    boards: Sequence[tuple[FloatArray, tuple[int, ...]]],
    screen: ScreenPreset,
    board: BoardPreset,
    augmentation: AugmentationPreset,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """One augmented photo with detector targets plus ``board.boards_per_image`` crops."""
    return build_screen_item_with_indices(rgb, boards, screen, board, augmentation, rng)[0]


def build_screen_item_with_indices(
    rgb: ByteImage,
    boards: Sequence[tuple[FloatArray, tuple[int, ...]]],
    screen: ScreenPreset,
    board: BoardPreset,
    augmentation: AugmentationPreset,
    rng: np.random.Generator,
) -> tuple[dict[str, Any], list[int]]:
    """``build_screen_item`` plus the board index of every crop (repeats included)."""
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
    quads = [transform_points(corners(nodes), to_canvas) for nodes, _ in boards]
    heat, offsets, weight = screen_targets(quads, (canvas_w, canvas_h), screen)

    chosen = rng.choice(len(boards), size=min(board.boards_per_image, len(boards)), replace=False)
    crops, nodes, visible = [], [], []
    for index in chosen:
        label_nodes, unavailable = boards[int(index)]
        crop, crop_nodes = build_board_crop(rgb, label_nodes, board, augmentation, rng)
        crops.append(crop)
        nodes.append(crop_nodes)
        mask = np.ones(CELL_COUNT, np.float32)
        mask[list(unavailable)] = 0
        visible.append(mask)
    indices = [int(index) for index in chosen]
    while len(crops) < board.boards_per_image:  # fewer boards than k: repeat the first crop
        crops.append(crops[0])
        nodes.append(nodes[0])
        visible.append(visible[0])
        indices.append(indices[0])
    return {
        "image": np.ascontiguousarray(canvas.transpose(2, 0, 1)),
        "heat": heat,
        "offsets": offsets,
        "offset_weight": weight,
        "crops": np.ascontiguousarray(np.stack(crops).transpose(0, 3, 1, 2)),
        "nodes": np.stack(nodes).astype(np.float32),
        "visible": np.stack(visible),
    }, indices


def build_board_crop(
    rgb: ByteImage,
    label_nodes: FloatArray,
    board: BoardPreset,
    augmentation: AugmentationPreset,
    rng: np.random.Generator,
) -> tuple[ByteImage, FloatArray]:
    """Jittered rectified board crop and its 24 nodes in crop pixels (same RNG draws as before)."""
    quad = perturb_quad(corners(label_nodes), board, rng)
    if not quad_is_usable(quad):
        quad = corners(label_nodes)
    matrix = board_rectifier(quad, board)
    crop = photometric(crop_board(rgb, matrix, board), augmentation, rng)
    return crop, transform_points(label_nodes, matrix)
