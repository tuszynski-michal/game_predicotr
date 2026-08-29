"""Small heatmap model and deterministic CPU training for geometry fallback."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn
from torch.nn import functional
from torch.utils.data import DataLoader, Dataset

from .dataset import (
    ApprovedKeypointGeometrySample,
    FrozenKeypointGeometryDataset,
    KeypointGeometryDatasetError,
)

KEYPOINT_GEOMETRY_MODEL_VERSION: Final = "keypoint-geometry-heatmaps-9x4-v1"
KEYPOINT_SLOT_COUNT: Final = 9
KEYPOINT_CORNER_COUNT: Final = 4


@dataclass(frozen=True, slots=True)
class KeypointGeometryModelConfiguration:
    input_size: int = 128
    heatmap_size: int = 32
    gaussian_sigma: float = 1.5

    def __post_init__(self) -> None:
        if (
            self.input_size < 64
            or self.input_size % 4 != 0
            or self.heatmap_size != self.input_size // 4
            or not math.isfinite(self.gaussian_sigma)
            or self.gaussian_sigma <= 0
        ):
            raise ValueError("The keypoint model configuration is invalid.")


DEFAULT_KEYPOINT_MODEL_CONFIGURATION = KeypointGeometryModelConfiguration()


@dataclass(frozen=True, slots=True)
class KeypointTrainingConfiguration:
    epochs: int = 20
    batch_size: int = 8
    learning_rate: float = 0.001
    seed: int = 319

    def __post_init__(self) -> None:
        if (
            self.epochs < 1
            or self.batch_size < 1
            or not math.isfinite(self.learning_rate)
            or self.learning_rate <= 0
            or self.seed < 0
        ):
            raise ValueError("The keypoint training configuration is invalid.")


DEFAULT_KEYPOINT_TRAINING_CONFIGURATION = KeypointTrainingConfiguration()


@dataclass(frozen=True, slots=True)
class EncodedKeypointTrainingSample:
    image: NDArray[np.float32]
    heatmaps: NDArray[np.float32]
    slot_presence: NDArray[np.float32]
    active_corner_mask: NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class KeypointTrainingResult:
    model: KeypointGeometryHeatmapNetwork
    losses: tuple[float, ...]
    training_sample_count: int
    model_version: str = KEYPOINT_GEOMETRY_MODEL_VERSION


class KeypointGeometryHeatmapNetwork(nn.Module):  # type: ignore[misc]
    """Bounded fully-convolutional encoder with corner and presence heads."""

    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=5, stride=2, padding=2),
            nn.ReLU(inplace=False),
            nn.Conv2d(16, 24, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=False),
            nn.Conv2d(24, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=False),
        )
        self.heatmap_head = nn.Conv2d(
            32,
            KEYPOINT_SLOT_COUNT * KEYPOINT_CORNER_COUNT,
            kernel_size=1,
        )
        self.presence_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.presence_head = nn.Linear(32, KEYPOINT_SLOT_COUNT)

    def forward(self, images: Tensor) -> tuple[Tensor, Tensor]:
        features = self.encoder(images)
        batch = images.shape[0]
        heatmaps = self.heatmap_head(features).reshape(
            batch,
            KEYPOINT_SLOT_COUNT,
            KEYPOINT_CORNER_COUNT,
            features.shape[2],
            features.shape[3],
        )
        pooled = self.presence_pool(features).flatten(1)
        return heatmaps, self.presence_head(pooled)


def encode_keypoint_training_sample(
    sample: ApprovedKeypointGeometrySample,
    rgb: NDArray[np.uint8],
    *,
    configuration: KeypointGeometryModelConfiguration = (DEFAULT_KEYPOINT_MODEL_CONFIGURATION),
) -> EncodedKeypointTrainingSample:
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape != (sample.canonical_height, sample.canonical_width, 3)
    ):
        raise ValueError("Training RGB does not match the approved canonical source.")
    resized = cv2.resize(
        rgb,
        (configuration.input_size, configuration.input_size),
        interpolation=cv2.INTER_AREA,
    )
    image = np.ascontiguousarray(resized.transpose(2, 0, 1), dtype=np.float32) / 255.0
    heatmaps: NDArray[np.float32] = np.zeros(
        (
            KEYPOINT_SLOT_COUNT,
            KEYPOINT_CORNER_COUNT,
            configuration.heatmap_size,
            configuration.heatmap_size,
        ),
        dtype=np.float32,
    )
    presence: NDArray[np.float32] = np.zeros((KEYPOINT_SLOT_COUNT,), dtype=np.float32)
    corner_mask: NDArray[np.float32] = np.zeros(
        (KEYPOINT_SLOT_COUNT, KEYPOINT_CORNER_COUNT), dtype=np.float32
    )
    for slot, quad in zip(sample.active_board_slots, sample.approved_quads, strict=True):
        presence[slot] = 1.0
        corner_mask[slot, :] = 1.0
        for corner_index, point in enumerate(quad.corners):
            x = _source_to_heatmap(point.x, sample.canonical_width, configuration.heatmap_size)
            y = _source_to_heatmap(point.y, sample.canonical_height, configuration.heatmap_size)
            heatmaps[slot, corner_index] = _gaussian_heatmap(
                x,
                y,
                size=configuration.heatmap_size,
                sigma=configuration.gaussian_sigma,
            )
    return EncodedKeypointTrainingSample(
        image=image,
        heatmaps=heatmaps,
        slot_presence=presence,
        active_corner_mask=corner_mask,
    )


class _EncodedDataset(
    Dataset[tuple[Tensor, Tensor, Tensor, Tensor]]  # type: ignore[misc]
):
    def __init__(self, values: Sequence[EncodedKeypointTrainingSample]) -> None:
        self._values = tuple(values)

    def __len__(self) -> int:
        return len(self._values)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        sample = self._values[index]
        return (
            torch.from_numpy(sample.image),
            torch.from_numpy(sample.heatmaps),
            torch.from_numpy(sample.slot_presence),
            torch.from_numpy(sample.active_corner_mask),
        )


def train_keypoint_geometry_model(
    dataset: FrozenKeypointGeometryDataset,
    *,
    load_rgb: Callable[[ApprovedKeypointGeometrySample], NDArray[np.uint8]],
    model_configuration: KeypointGeometryModelConfiguration = (
        DEFAULT_KEYPOINT_MODEL_CONFIGURATION
    ),
    training_configuration: KeypointTrainingConfiguration = (
        DEFAULT_KEYPOINT_TRAINING_CONFIGURATION
    ),
) -> KeypointTrainingResult:
    samples = dataset.samples_for("train")
    if not samples:
        raise ValueError("The frozen keypoint dataset has no training split.")
    if any(sample.approval_kind != "manual_approved" for sample in samples):
        raise KeypointGeometryDatasetError(
            "KEYPOINT_GEOMETRY_APPROVAL_REQUIRED",
            "Keypoint training accepts only manually approved source quads.",
        )
    torch.manual_seed(training_configuration.seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True, warn_only=True)
    encoded = tuple(
        encode_keypoint_training_sample(
            sample,
            load_rgb(sample),
            configuration=model_configuration,
        )
        for sample in samples
    )
    model = KeypointGeometryHeatmapNetwork()
    optimizer = torch.optim.AdamW(model.parameters(), lr=training_configuration.learning_rate)
    generator = torch.Generator(device="cpu")
    generator.manual_seed(training_configuration.seed)
    loader = DataLoader(
        _EncodedDataset(encoded),
        batch_size=min(training_configuration.batch_size, len(encoded)),
        shuffle=True,
        generator=generator,
        num_workers=0,
    )
    losses: list[float] = []
    model.train()
    for _ in range(training_configuration.epochs):
        epoch_loss = 0.0
        batches = 0
        for images, target_heatmaps, target_presence, corner_mask in loader:
            optimizer.zero_grad(set_to_none=True)
            predicted_heatmaps, predicted_presence = model(images)
            heatmap_loss_values = functional.binary_cross_entropy_with_logits(
                predicted_heatmaps,
                target_heatmaps,
                reduction="none",
            )
            expanded_mask = corner_mask[:, :, :, None, None]
            active_elements = expanded_mask.sum() * (model_configuration.heatmap_size**2)
            heatmap_loss = (heatmap_loss_values * expanded_mask).sum() / active_elements
            presence_loss = functional.binary_cross_entropy_with_logits(
                predicted_presence,
                target_presence,
            )
            loss = heatmap_loss + 0.25 * presence_loss
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach().cpu().item())
            batches += 1
        losses.append(epoch_loss / batches)
    model.eval()
    return KeypointTrainingResult(
        model=model,
        losses=tuple(losses),
        training_sample_count=len(encoded),
    )


def prepare_keypoint_model_input(
    rgb: NDArray[np.uint8],
    *,
    input_size: int,
) -> NDArray[np.float32]:
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
        or rgb.shape[0] < 1
        or rgb.shape[1] < 1
    ):
        raise ValueError("Keypoint inference requires non-empty RGB uint8 pixels.")
    resized = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(resized.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0


def _source_to_heatmap(value: float, extent: int, heatmap_size: int) -> float:
    denominator = max(1, extent - 1)
    return min(heatmap_size - 1.0, max(0.0, value / denominator * (heatmap_size - 1)))


def _gaussian_heatmap(x: float, y: float, *, size: int, sigma: float) -> NDArray[np.float32]:
    coordinates: NDArray[np.float32] = np.arange(size, dtype=np.float32)
    xx: NDArray[np.float32]
    yy: NDArray[np.float32]
    xx, yy = np.meshgrid(coordinates, coordinates)
    values = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2.0 * sigma**2))
    return np.asarray(values, dtype=np.float32)


__all__ = [
    "DEFAULT_KEYPOINT_MODEL_CONFIGURATION",
    "DEFAULT_KEYPOINT_TRAINING_CONFIGURATION",
    "KEYPOINT_CORNER_COUNT",
    "KEYPOINT_GEOMETRY_MODEL_VERSION",
    "KEYPOINT_SLOT_COUNT",
    "EncodedKeypointTrainingSample",
    "KeypointGeometryHeatmapNetwork",
    "KeypointGeometryModelConfiguration",
    "KeypointTrainingConfiguration",
    "KeypointTrainingResult",
    "encode_keypoint_training_sample",
    "prepare_keypoint_model_input",
    "train_keypoint_geometry_model",
]
