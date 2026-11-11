"""Frozen-cohort batches and validation for the V3 grid trainer (TASK-0996).

Composes the neutral training core with the TASK-0995 cohort reader; nothing here opens
the database. A batch is a pure function of ``(seed, step)``: the photo order comes from
``StepSampler`` and every augmentation from ``step_rng``. Future steps are prepared in a
small thread pool, which changes timing only. Validation crops use the true corners
without jitter or photometric changes; REGRESSION is never read.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import numpy as np
import torch
from game_predictor_api.domain.grid_visibility_contract import (
    BoardContentReference,
    GridOutputContract,
    visibility_supervision,
)

from ..geometry_core.inference import DecodeSettings, NeuralGridEngine
from ..geometry_core.preprocessing import board_rectifier, corners, crop_board, transform_points
from ..geometry_core.rescue import GridRescueVariantV1, GridRescueVariantV2
from ..training_core.grid_rescue_training import variant_step
from ..training_core.grid_training import (
    BalancedSampler,
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
from .grid_cohort_dataset import (
    GridBoardDataset,
    GridCohortSnapshot,
    frame_rgb_and_box,
)

PREFETCH_STEPS = 4
PARITY_CROPS = 8


class GridTrainingDataError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ContentSelectionDataset(GridBoardDataset):
    """Pinned A targets for content parity; partial photos retain their fixed target scope."""

    def __init__(self, snapshot: GridCohortSnapshot, role: str) -> None:
        if (
            role != "VALIDATION"
            or snapshot.manifest.get("policyVersion") != "application-grid-corrections-v4"
            or snapshot.manifest.get("photoSplit", {}).get("contentSampling", {}).get("policy")
            != "full-symbol-content-sampling-v1"
        ):
            raise GridTrainingDataError("CONTENT_EXPERIMENT_SELECTION_POLICY_REQUIRED")
        super().__init__(snapshot, role)


class CohortPhotos:
    """Metadata index of one role; pixels are decoded per use through the role guard."""

    def __init__(
        self,
        snapshot: GridCohortSnapshot,
        role: str,
        *,
        full_only: bool,
        content_selection: bool = False,
    ) -> None:
        self.snapshot, self.role = snapshot, role
        dataset = ContentSelectionDataset if content_selection else GridBoardDataset
        rows = dataset(snapshot, role).indexed()
        if full_only:
            if snapshot.manifest["policyVersion"] in (
                "application-grid-corrections-v3",
                "application-grid-corrections-v4",
            ) and any(row[0].get("screenEligible") is not True for row in rows):
                raise GridTrainingDataError("GRID_TRAINING_FULL_DATA_DRIFT")
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

    def content_references(self, index: int) -> list[BoardContentReference | None]:
        from .grid_cell_content_reference import frozen_content_reference

        source, targets = self.rows[index]
        if self.role != "TRAIN":
            return [None] * len(targets)
        from uuid import UUID

        labels = sorted(source["targets"], key=lambda target: target["positionIndex"])
        return [
            frozen_content_reference(UUID(self.snapshot.manifest["gameId"]), source, label)
            for label in labels
        ]


class JointPhotos:
    """TRAIN photos of several games in one index space (TASK-1006).

    ``strata[game][recording]`` groups the indices by game and pinned recording group, so
    a ``BalancedSampler`` weighs games and recordings equally whatever their sizes.
    """

    def __init__(self, parts: Sequence[CohortPhotos], groups: Sequence[Mapping[str, str]]) -> None:
        if len(parts) < 2 or len(parts) != len(groups):
            raise GridTrainingDataError("GRID_TRAINING_SHARED_SCOPE_INVALID")
        self.parts = list(parts)
        self.starts: list[int] = []
        strata = []
        start = 0
        for part, mapping in zip(parts, groups, strict=True):
            by_group: dict[str, list[int]] = {}
            for local, (source, _targets) in enumerate(part.rows):
                group = mapping.get(str(source["sourceId"]))
                if group is None:
                    raise GridTrainingDataError("GRID_TRAINING_RECORDING_UNRESOLVED")
                by_group.setdefault(group, []).append(start + local)
            strata.append(tuple(tuple(by_group[key]) for key in sorted(by_group)))
            self.starts.append(start)
            start += len(part)
        self.size = start
        self.strata = tuple(strata)

    def __len__(self) -> int:
        return self.size

    def _locate(self, index: int) -> tuple[CohortPhotos, int]:
        for part, start in zip(reversed(self.parts), reversed(self.starts), strict=True):
            if index >= start:
                return part, index - start
        raise IndexError(index)

    def rgb(self, index: int) -> np.ndarray:
        part, local = self._locate(index)
        return part.rgb(local)

    def targets(self, index: int) -> list[tuple[np.ndarray, int]]:
        part, local = self._locate(index)
        return part.targets(local)


def _sampler(size: int, batch: int, seed: int, strata: Any) -> Any:
    if strata is None:
        return StepSampler(size, batch, seed)
    return BalancedSampler(strata, batch, seed)


def macro_evaluator(evaluators: Sequence[Callable[[Any], float]]) -> Callable[[Any], float]:
    """Shared VALIDATION score: the mean of the per-game scores, each game weighing the same."""

    def evaluate(network: Any) -> float:
        return float(np.mean([evaluator(network) for evaluator in evaluators]))

    return evaluate


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


def content_references(photos: Any, index: int) -> list[BoardContentReference | None]:
    """Optional guarded T2 adapter, aligned with targets; absent never means visible."""
    if isinstance(photos, JointPhotos):
        part, local = photos._locate(index)
        return content_references(part, local)
    reader = getattr(photos, "content_references", None)
    values = [None] * len(photos.targets(index)) if reader is None else reader(index)
    if len(values) != len(photos.targets(index)):
        raise ValueError("GRID_CONTENT_TARGET_ALIGNMENT")
    parsed = [
        None if value is None else BoardContentReference.model_validate(value) for value in values
    ]
    if isinstance(photos, CohortPhotos):
        if photos.role != "TRAIN":
            raise ValueError("GRID_VISIBILITY_TRAIN_ROLE_REQUIRED")
        source = photos.rows[index][0]
        positions = sorted(target["positionIndex"] for target in source["targets"])
        for reference, position in zip(parsed, positions, strict=True):
            if reference is not None and (
                reference.sourceRepresentativeSha256
                != source["sourceIdentity"]["normalized_pixel_checksum_sha256"]
                or reference.positionIndex != position
                or str(reference.gameId) != str(photos.snapshot.manifest["gameId"])
            ):
                raise ValueError("GRID_CONTENT_SOURCE_OR_SLOT_CHANGED")
    return parsed


def require_visibility_contract(photos: Any, contract: GridOutputContract | None) -> None:
    if contract is None:
        return
    if contract.trainedVisibility:
        raise ValueError("GRID_VISIBILITY_INPUT_CANNOT_CLAIM_TRAINING")
    references = [
        value
        for index in range(len(photos))
        for value in content_references(photos, index)
        if value is not None
    ]
    parts = photos.parts if isinstance(photos, JointPhotos) else [photos]
    games = [
        str(part.snapshot.manifest["gameId"]) for part in parts if isinstance(part, CohortPhotos)
    ]
    if visibility_supervision(references, game_ids=games) != contract.supervision:
        raise ValueError("GRID_VISIBILITY_SUPERVISION_CHANGED")


def photo_pixels_and_support(photos: Any, index: int) -> tuple[np.ndarray, np.ndarray]:
    """One frame read per photo, even when it contributes several board crops."""
    if isinstance(photos, JointPhotos):
        part, local = photos._locate(index)
        return photo_pixels_and_support(part, local)
    if isinstance(photos, CohortPhotos):
        rgb, box = frame_rgb_and_box(photos.snapshot.frame(photos.rows[index][0], photos.role))
        support = np.zeros(rgb.shape[:2], np.float32)
        left, top, right, bottom = box
        support[top:bottom, left:right] = 1
        return rgb, support
    rgb = photos.rgb(index)
    reader = getattr(photos, "source_support", None)
    if reader is not None:
        return rgb, np.asarray(reader(index), dtype=np.float32)
    return rgb, np.ones(rgb.shape[:2], np.float32)


class GridOnlyBatches(_Prefetched):
    """``photos`` TRAIN photos per step, up to ``boards_per_image`` crops each; a photo with
    fewer complete boards is padded with zero-weight copies, never with duplicated weight."""

    def __init__(
        self,
        photos: Any,
        recipe: Any,
        batch_boards: int,
        seed: int,
        workers: int,
        strata: Any = None,
        *,
        output_contract: GridOutputContract | None = None,
    ) -> None:
        self.photos, self.recipe, self.seed = photos, recipe, seed
        self.output_contract = output_contract
        require_visibility_contract(photos, output_contract)
        self.k = int(recipe.board.boards_per_image)
        self.sampler = _sampler(len(photos), max(1, batch_boards // self.k), seed, strata)
        super().__init__(self._build, workers)

    def _build(self, step: int) -> dict[str, torch.Tensor]:
        crops: list[np.ndarray] = []
        nodes: list[np.ndarray] = []
        weights: list[float] = []
        supervised: list[dict[str, np.ndarray]] = []
        for slot, index in enumerate(self.sampler.indices(step)):
            rng = step_rng(self.seed, step, slot)
            targets = self.photos.targets(index)
            rgb, support = (
                (self.photos.rgb(index), None)
                if self.output_contract is None
                else photo_pixels_and_support(self.photos, index)
            )
            chosen = rng.choice(len(targets), size=min(self.k, len(targets)), replace=False)
            for position in chosen:
                label, weight = targets[int(position)]
                if self.output_contract is None:
                    crop, crop_nodes = build_board_crop(
                        rgb,
                        label.astype(np.float32),
                        self.recipe.board,
                        self.recipe.augmentation,
                        rng,
                    )
                else:
                    from ..training_core.grid_visibility_targets import supervised_board_crop

                    assert support is not None
                    item = supervised_board_crop(
                        rgb,
                        label.astype(np.float32),
                        self.recipe.board,
                        self.recipe.augmentation,
                        rng,
                        reference=content_references(self.photos, index)[int(position)],
                        supervision=self.output_contract.supervision,
                        source_support=support,
                    )
                    crop, crop_nodes = item["crop"], item["nodes"]
                    supervised.append(item)
                crops.append(crop)
                nodes.append(crop_nodes)
                weights.append(float(weight))
            for _ in range(self.k - len(chosen)):
                crops.append(crops[-1])
                nodes.append(nodes[-1])
                weights.append(0.0)
                if supervised:
                    supervised.append(supervised[-1])
        result = {
            "crops": _crop_tensor(crops),
            "nodes": torch.from_numpy(np.stack(nodes).astype(np.float32)),
            "weights": torch.tensor(weights, dtype=torch.float32),
        }
        if self.output_contract is not None:
            result.update(
                {
                    key: torch.from_numpy(np.stack([item[key] for item in supervised]))
                    for key in ("node_weights", "visibility_targets", "visibility_mask")
                }
            )
            for key in ("node_weights", "visibility_mask"):
                result[key] *= (result["weights"] > 0)[:, None]
        return result


class ScreenGridBatches(_Prefetched):
    """Full TRAIN photos with detector targets of all nine boards plus weighted crops."""

    def __init__(
        self,
        photos: Any,
        recipe: Any,
        batch_photos: int,
        seed: int,
        workers: int,
        strata: Any = None,
        *,
        variant: GridRescueVariantV1 | GridRescueVariantV2 | None = None,
        output_contract: GridOutputContract | None = None,
        content_experiment: bool = False,
        content_auxiliary: bool = False,
    ) -> None:
        self.photos, self.recipe, self.seed = photos, recipe, seed
        self.output_contract = output_contract
        self.content_experiment, self.content_auxiliary = content_experiment, content_auxiliary
        if content_experiment and output_contract is None:
            raise ValueError("CONTENT_TRAINING_OUTPUT_CONTRACT_REQUIRED")
        require_visibility_contract(photos, output_contract)
        self.variant = variant
        if variant is not None:
            variant.require_baseline(recipe.board.margin)
        self.sampler = _sampler(len(photos), batch_photos, seed, strata)
        super().__init__(self._build, workers)

    def _build(self, step: int) -> dict[str, torch.Tensor]:
        items, weights = [], []
        active = self.variant if variant_step(step) else None
        for slot, index in enumerate(self.sampler.indices(step)):
            rng = step_rng(self.seed, step, slot)
            targets = self.photos.targets(index)
            boards = [(label.astype(np.float32), ()) for label, _ in targets]
            rgb, support = (
                (self.photos.rgb(index), None)
                if self.output_contract is None
                else photo_pixels_and_support(self.photos, index)
            )
            item, chosen = build_screen_item_with_indices(
                rgb,
                boards,
                self.recipe.screen,
                self.recipe.board,
                self.recipe.augmentation,
                rng,
                screen_geometry_override=None if active is None else active.screen,
                board_geometry_override=None if active is None else active.board,
                content_references=None
                if self.output_contract is None
                else content_references(self.photos, index),
                visibility_supervision=None
                if self.output_contract is None
                else self.output_contract.supervision,
                source_support=support,
                explicit_skip=self.content_experiment,
                content_auxiliary=self.content_auxiliary,
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
        if self.output_contract is not None:
            batch.update(
                {
                    key: torch.from_numpy(np.stack([item[key] for item in items]))
                    for key in ("node_weights", "visibility_targets", "visibility_mask")
                }
            )
            for key in ("node_weights", "visibility_mask"):
                batch[key] *= (batch["weights"] > 0)[..., None]
        if self.content_experiment:
            batch["crop_skipped"] = torch.from_numpy(
                np.stack([item["crop_skipped"] for item in items])
            )
            batch["weights"] *= 1 - batch["crop_skipped"].to(torch.float32)
        if self.content_auxiliary:
            for key in ("content_quads", "content_quad_mask"):
                batch[key] = torch.from_numpy(np.stack([item[key] for item in items]))
            batch["content_quad_mask"] *= (batch["weights"] > 0)[..., None]
        return batch

    def content_exposure_members(self, step: int, batch: Any, values: Any) -> dict[str, Any]:
        """Only photos contributing a nonzero component enter optimizer receipts."""
        del values
        members = self.exposure_members(step)
        board = []
        for index, member in enumerate(members):
            weights = batch["weights"][index] > 0
            if any(
                bool((batch[key][index] * weights[..., None]).sum() > 0)
                for key in ("node_weights", "visibility_mask", "content_quad_mask")
                if key in batch
            ):
                board.append(member)
        return {"screen": members, "board": board}

    def exposure_members(self, step: int) -> list[dict[str, str]]:
        result = []
        for index in self.sampler.indices(step):
            photos, local = (
                self.photos._locate(index)
                if isinstance(self.photos, JointPhotos)
                else (self.photos, index)
            )
            source = photos.rows[local][0]
            result.append(
                {
                    "gameId": str(photos.snapshot.manifest["gameId"]),
                    "sourceId": str(source["sourceId"]),
                    "sourceSha256": str(source["sourceIdentity"]["checksum_sha256"]),
                    "cohortSha256": str(photos.snapshot.manifest_sha256),
                }
            )
        return result


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


def photo_evaluator(
    photos: CohortPhotos,
    recipe: Any,
    device: str,
    *,
    correction_metrics: bool = False,
    selection: Any = None,
    exposure: Any = None,
    variant: Any = None,
    parts: Sequence[CohortPhotos] | None = None,
) -> Any:
    """Share of VALIDATION photos decoded completely and correctly from the original frame."""

    if selection is not None:
        from .grid_rescue_evaluation import ScreenCorrectionEvaluator

        return ScreenCorrectionEvaluator(
            parts or [photos], recipe, device, variant, selection, exposure
        )
    if correction_metrics:
        return correction_evaluator([photos], recipe, device, photo_first=True)

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


def correction_evaluator(
    parts: Sequence[CohortPhotos], recipe: Any, device: str, *, photo_first: bool = False
) -> Any:
    """Photo-macro VALIDATION from full frames, with equal weight for each game."""
    from .grid_correction_consistency import CorrectionEvaluator

    if any(part.role != "VALIDATION" for part in parts):
        raise GridTrainingDataError("GRID_TRAINING_VALIDATION_ONLY")

    return CorrectionEvaluator(parts, recipe, device, photo_first=photo_first)
