"""Frozen-cohort batches and validation for the V3 grid trainer (TASK-0996).

Composes the neutral training core with the TASK-0995 cohort reader; nothing here opens
the database. A batch is a pure function of ``(seed, step)``: the photo order comes from
``StepSampler`` and every augmentation from ``step_rng``. Future steps are prepared in a
small thread pool, which changes timing only. Validation crops use the true corners
without jitter or photometric changes; REGRESSION is never read.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import numpy as np
import torch

from ..geometry_core.inference import DecodeSettings, NeuralGridEngine
from ..geometry_core.preprocessing import board_rectifier, corners, crop_board, transform_points
from ..training_core.grid_training import (
    StepSampler,
    board_correct,
    photo_complete_correct,
    step_rng,
)
from ..training_core.neural_grid_augmentation import (
    build_board_crop,
    build_screen_item_with_indices,
)
from ..training_core.neural_grid_network import BoardExport, NeuralGridNetwork, ScreenExport
from .grid_cohort_dataset import GridBoardDataset, GridCohortSnapshot

PREFETCH_STEPS = 4
PARITY_CROPS = 8


class GridTrainingDataError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CohortPhotos:
    """Metadata index of one role; pixels are decoded per use through the role guard."""

    def __init__(self, snapshot: GridCohortSnapshot, role: str, *, full_only: bool) -> None:
        self.snapshot, self.role = snapshot, role
        rows = GridBoardDataset(snapshot, role).indexed()
        if full_only:
            rows = [row for row in rows if row[0].get("screenEligible") is True]
        if not rows:
            raise GridTrainingDataError("GRID_TRAINING_EMPTY_ROLE")
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def rgb(self, index: int) -> np.ndarray:
        source, _ = self.rows[index]
        return np.ascontiguousarray(self.snapshot.frame(source, self.role).rgb)

    def targets(self, index: int) -> list[tuple[np.ndarray, int]]:
        return self.rows[index][1]


class _Prefetched:
    def __init__(self, build: Any, workers: int) -> None:
        self.build = build
        self.pool = ThreadPoolExecutor(max_workers=max(1, workers))
        self.pending: dict[int, Future[dict[str, torch.Tensor]]] = {}

    def __call__(self, step: int) -> dict[str, torch.Tensor]:
        for ahead in range(step, step + PREFETCH_STEPS):
            if ahead not in self.pending:
                self.pending[ahead] = self.pool.submit(self.build, ahead)
        for stale in [key for key in self.pending if key < step]:
            self.pending.pop(stale).cancel()
        return self.pending.pop(step).result()

    def close(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=True)


def _crop_tensor(crops: list[np.ndarray]) -> torch.Tensor:
    return torch.from_numpy(np.ascontiguousarray(np.stack(crops).transpose(0, 3, 1, 2)))


class GridOnlyBatches(_Prefetched):
    """``photos`` TRAIN photos per step, up to ``boards_per_image`` crops each; a photo with
    fewer complete boards is padded with zero-weight copies, never with duplicated weight."""

    def __init__(
        self, photos: CohortPhotos, recipe: Any, batch_boards: int, seed: int, workers: int
    ) -> None:
        self.photos, self.recipe, self.seed = photos, recipe, seed
        self.k = int(recipe.board.boards_per_image)
        self.sampler = StepSampler(len(photos), max(1, batch_boards // self.k), seed)
        super().__init__(self._build, workers)

    def _build(self, step: int) -> dict[str, torch.Tensor]:
        crops: list[np.ndarray] = []
        nodes: list[np.ndarray] = []
        weights: list[float] = []
        for slot, index in enumerate(self.sampler.indices(step)):
            rng = step_rng(self.seed, step, slot)
            rgb, targets = self.photos.rgb(index), self.photos.targets(index)
            chosen = rng.choice(len(targets), size=min(self.k, len(targets)), replace=False)
            for position in chosen:
                label, weight = targets[int(position)]
                crop, crop_nodes = build_board_crop(
                    rgb, label.astype(np.float32), self.recipe.board, self.recipe.augmentation, rng
                )
                crops.append(crop)
                nodes.append(crop_nodes)
                weights.append(float(weight))
            for _ in range(self.k - len(chosen)):
                crops.append(crops[-1])
                nodes.append(nodes[-1])
                weights.append(0.0)
        return {
            "crops": _crop_tensor(crops),
            "nodes": torch.from_numpy(np.stack(nodes).astype(np.float32)),
            "weights": torch.tensor(weights, dtype=torch.float32),
        }


class ScreenGridBatches(_Prefetched):
    """Full TRAIN photos with detector targets of all nine boards plus weighted crops."""

    def __init__(
        self, photos: CohortPhotos, recipe: Any, batch_photos: int, seed: int, workers: int
    ) -> None:
        self.photos, self.recipe, self.seed = photos, recipe, seed
        self.sampler = StepSampler(len(photos), batch_photos, seed)
        super().__init__(self._build, workers)

    def _build(self, step: int) -> dict[str, torch.Tensor]:
        items, weights = [], []
        for slot, index in enumerate(self.sampler.indices(step)):
            rng = step_rng(self.seed, step, slot)
            targets = self.photos.targets(index)
            boards = [(label.astype(np.float32), ()) for label, _ in targets]
            item, chosen = build_screen_item_with_indices(
                self.photos.rgb(index),
                boards,
                self.recipe.screen,
                self.recipe.board,
                self.recipe.augmentation,
                rng,
            )
            seen: set[int] = set()
            row = []
            for position in chosen:  # repeated crops carry no extra weight
                row.append(0.0 if position in seen else float(targets[position][1]))
                seen.add(position)
            items.append(item)
            weights.append(row)
        batch = {
            key: torch.from_numpy(np.stack([item[key] for item in items]))
            for key in ("image", "heat", "offsets", "offset_weight", "crops", "nodes")
        }
        batch["weights"] = torch.tensor(weights, dtype=torch.float32)
        return batch


def validation_crops(photos: CohortPhotos, recipe: Any) -> tuple[np.ndarray, np.ndarray]:
    """True-corner crops (uint8 NCHW) and nodes in crop pixels of every VALIDATION board."""
    crops, labels = [], []
    for index in range(len(photos)):
        rgb = photos.rgb(index)
        for label, _ in photos.targets(index):
            matrix = board_rectifier(corners(label), recipe.board)
            crops.append(crop_board(rgb, matrix, recipe.board))
            labels.append(transform_points(label, matrix))
    return (
        np.ascontiguousarray(np.stack(crops).transpose(0, 3, 1, 2)),
        np.stack(labels).astype(np.float64),
    )


def board_evaluator(crops: np.ndarray, labels: np.ndarray, device: str, chunk: int = 32) -> Any:
    """Share of VALIDATION boards whose nodes are correct (metrics v1 thresholds)."""

    def evaluate(network: NeuralGridNetwork) -> float:
        correct = 0
        graph = BoardExport(network.board).eval()
        for start in range(0, len(crops), chunk):
            batch = torch.from_numpy(crops[start : start + chunk]).to(device).float()
            predicted = graph(batch)[0].float().cpu().numpy()
            for offset, nodes in enumerate(predicted):
                correct += int(board_correct(nodes, labels[start + offset]))
        return correct / len(crops)

    return evaluate


def photo_evaluator(photos: CohortPhotos, recipe: Any, device: str) -> Any:
    """Share of VALIDATION photos decoded completely and correctly from the original frame."""

    def evaluate(network: NeuralGridNetwork) -> float:
        screen_graph = ScreenExport(network.screen).eval()
        board_graph = BoardExport(network.board).eval()

        def screen(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            heat, offsets = screen_graph(torch.from_numpy(pixels).to(device))
            return heat.float().cpu().numpy(), offsets.float().cpu().numpy()

        def board(batch: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            nodes, peak, visibility = board_graph(torch.from_numpy(batch).to(device))
            return (
                nodes.float().cpu().numpy(),
                peak.float().cpu().numpy(),
                visibility.float().cpu().numpy(),
            )

        engine = NeuralGridEngine(screen, board, DecodeSettings.of(recipe))
        correct = 0
        for index in range(len(photos)):
            detections = engine.analyse(photos.rgb(index))
            predicted = [d.nodes for d in detections if d.nodes is not None]
            labels = [label for label, _ in photos.targets(index)]
            correct += int(photo_complete_correct(predicted, labels))
        return correct / len(photos)

    return evaluate


def parity_inputs(
    crops: np.ndarray, photos: CohortPhotos | None, recipe: Any
) -> tuple[np.ndarray, np.ndarray | None]:
    """Float crops for board parity and, when available, one screen input for the detector."""
    from ..geometry_core.preprocessing import screen_input

    board = np.ascontiguousarray(crops[:PARITY_CROPS].astype(np.float32))
    if photos is None:
        return board, None
    canvas, _, _ = screen_input(photos.rgb(0), recipe.screen)
    pixels = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None].astype(np.float32))
    return board, pixels


def planned_steps(train_seconds: float, steps_per_second: float, max_steps: int) -> int:
    return max(1, min(max_steps, math.floor(train_seconds * steps_per_second)))


def frozen_manifest(snapshot: GridCohortSnapshot) -> Mapping[str, Any]:
    return snapshot.manifest
