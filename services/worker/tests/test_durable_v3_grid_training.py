"""TASK-0996: step-deterministic resumable grid training core and its data adapters."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from game_predictor_worker.training_core.grid_training import (
    EarlyStopping,
    StepSampler,
    TrainingInterrupted,
    TrainingPlan,
    apply_freeze,
    board_correct,
    learning_rate,
    namespace,
    parity_verdict,
    photo_complete_correct,
    step_rng,
    train,
    train_mode,
    weighted_node_losses,
)
from game_predictor_worker.training_core.grid_training_admission import GRID_ONLY_V1
from torch import nn

PRESET = replace(
    GRID_ONLY_V1,
    learning_rate=1e-2,
    steps_per_second_estimate=1.0,
    early_stopping=replace(GRID_ONLY_V1.early_stopping, evaluation_interval_seconds=3.0),
)


class Tiny(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        torch.manual_seed(7)
        self.board = nn.Sequential(nn.Linear(4, 8), nn.BatchNorm1d(8), nn.Linear(8, 1))
        self.screen = nn.Linear(4, 1)


def batches(step: int) -> dict[str, torch.Tensor]:
    rng = step_rng(11, step, 0)
    x = torch.from_numpy(rng.normal(size=(6, 4)).astype(np.float32))
    return {"x": x, "y": x.sum(dim=1, keepdim=True)}


def losses(network: nn.Module, batch: Any) -> dict[str, torch.Tensor]:
    loss = torch.nn.functional.mse_loss(network.board(batch["x"]), batch["y"])
    return {"total": loss}


def evaluate(network: nn.Module) -> float:
    batch = batches(10_000)
    return -float(torch.nn.functional.mse_loss(network.board(batch["x"]), batch["y"]))


class Control:
    def __init__(self, stop_at: int | None = None) -> None:
        self.stop_at = stop_at
        self.published: list[tuple[Path, str, int]] = []

    def before_step(self, step: int) -> None:
        if self.stop_at is not None and step == self.stop_at:
            raise TrainingInterrupted("RUN_SUPERVISOR_LOST")

    def checkpoint_published(self, path: Path, sha256: str, step: int) -> None:
        self.published.append((path, sha256, step))

    def progress(self, step: int, total: int, values: Any) -> None:
        pass


def plan(frozen: tuple[str, ...] = ()) -> TrainingPlan:
    value = TrainingPlan.of("run-1", 5, replace(PRESET, frozen_modules=frozen), 12, {"x": 1})
    assert value.evaluation_steps == 3
    return value


def state(network: nn.Module) -> dict[str, torch.Tensor]:
    return {k: v.detach().clone() for k, v in network.state_dict().items()}


def test_sampler_is_a_pure_function_of_step_with_one_permutation_per_epoch() -> None:
    sampler = StepSampler(size=5, batch=2, seed=3)
    first = [sampler.indices(step) for step in range(5)]
    assert first == [StepSampler(5, 2, 3).indices(step) for step in range(5)]
    flat = [index for row in first for index in row]
    assert sorted(flat[:5]) == list(range(5)) and sorted(flat[5:10]) == list(range(5))
    assert (
        StepSampler(5, 2, 4).indices(0) != first[0] or StepSampler(5, 2, 4).indices(1) != first[1]
    )
    assert np.array_equal(step_rng(1, 2, 3).random(4), step_rng(1, 2, 3).random(4))
    with pytest.raises(ValueError, match="GRID_TRAINING_EMPTY_DATASET"):
        StepSampler(0, 1, 1).indices(0)


def test_learning_rate_matches_the_lab_curve() -> None:
    assert learning_rate(GRID_ONLY_V1, 0.0) == 0.0
    assert learning_rate(GRID_ONLY_V1, 0.05) == pytest.approx(GRID_ONLY_V1.learning_rate)
    assert learning_rate(GRID_ONLY_V1, 1.0) == pytest.approx(GRID_ONLY_V1.learning_rate * 0.1)


@pytest.mark.parametrize("stop_at", [2, 7])
def test_interrupted_run_resumes_to_the_same_weights_as_an_uninterrupted_run(
    tmp_path: Path, stop_at: int
) -> None:
    straight = Tiny()
    reference = train(
        network=straight,
        preset=PRESET,
        plan=plan(),
        batches=batches,
        losses=losses,
        evaluate=evaluate,
        control=Control(),
        checkpoint_directory=tmp_path / "a",
    )
    interrupted = Tiny()
    control = Control(stop_at=stop_at)
    with pytest.raises(TrainingInterrupted):
        train(
            network=interrupted,
            preset=PRESET,
            plan=plan(),
            batches=batches,
            losses=losses,
            evaluate=evaluate,
            control=control,
            checkpoint_directory=tmp_path / "b",
        )
    path, sha, step = control.published[-1]
    assert step == stop_at  # the interruption itself publishes a step-boundary checkpoint
    restarted = Tiny()  # a new process: fresh module, optimizer and RNG
    torch.manual_seed(999)
    resumed = train(
        network=restarted,
        preset=PRESET,
        plan=plan(),
        batches=batches,
        losses=losses,
        evaluate=evaluate,
        control=Control(),
        checkpoint_directory=tmp_path / "b",
        resume=(path, sha),
    )
    assert resumed.steps == reference.steps == 12
    for name, value in state(straight).items():
        assert torch.allclose(value, state(restarted)[name]), name
    assert [h["metric"] for h in resumed.history] == pytest.approx(
        [h["metric"] for h in reference.history]
    )
    assert resumed.best_step == reference.best_step


def test_corrupt_or_foreign_checkpoint_never_resumes(tmp_path: Path) -> None:
    control = Control()
    train(
        network=Tiny(),
        preset=PRESET,
        plan=plan(),
        batches=batches,
        losses=losses,
        evaluate=evaluate,
        control=control,
        checkpoint_directory=tmp_path,
    )
    path, sha, _ = control.published[0]
    with pytest.raises(ValueError, match="CHECKPOINT_BINDING_MISMATCH"):
        train(
            network=Tiny(),
            preset=PRESET,
            plan=replace(plan(), binding={**plan().binding, "x": 2}),
            batches=batches,
            losses=losses,
            evaluate=evaluate,
            control=Control(),
            checkpoint_directory=tmp_path,
            resume=(path, sha),
        )
    data = bytearray(path.read_bytes())
    data[-10] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="CHECKPOINT_CHECKSUM_MISMATCH"):
        train(
            network=Tiny(),
            preset=PRESET,
            plan=plan(),
            batches=batches,
            losses=losses,
            evaluate=evaluate,
            control=Control(),
            checkpoint_directory=tmp_path,
            resume=(path, sha),
        )


def test_early_stopping_waits_for_patience_and_min_evaluations() -> None:
    stopping = EarlyStopping("maximize", patience=2, min_delta=0.0, min_evaluations=2)
    assert stopping.update(0.5, 1) and not stopping.stop
    assert not stopping.update(0.5, 2) and not stopping.stop
    assert not stopping.update(0.4, 3) and stopping.stop
    assert stopping.state() == {"best": 0.5, "bestStep": 1, "stale": 2, "evaluations": 3}
    restored = EarlyStopping("maximize", 2, 0.0, 2)
    restored.restore(stopping.state())
    assert restored.stop
    with pytest.raises(ValueError, match="GRID_TRAINING_METRIC_NONFINITE"):
        restored.update(float("nan"), 4)


def test_early_stopping_ends_a_run_before_its_planned_steps(tmp_path: Path) -> None:
    result = train(
        network=Tiny(),
        preset=PRESET,
        plan=plan(),
        batches=batches,
        losses=losses,
        evaluate=lambda network: 0.0,  # never improves after the first evaluation
        control=Control(),
        checkpoint_directory=tmp_path,
    )
    assert result.stop_reason == "early_stopping"
    assert result.steps == 9 and result.best_step == 3


def test_freeze_keeps_detector_and_batchnorm_fixed_after_train_mode(tmp_path: Path) -> None:
    network = Tiny()
    before = state(network)
    result = train(
        network=network,
        preset=PRESET,
        plan=plan(("detector", "batchnorm")),
        batches=batches,
        losses=losses,
        evaluate=evaluate,
        control=Control(),
        checkpoint_directory=tmp_path,
    )
    after = state(network)
    assert result.steps == 12
    for name in ("screen.weight", "screen.bias", "board.1.weight", "board.1.bias"):
        assert torch.equal(before[name], after[name]), name
    for name in ("board.1.running_mean", "board.1.running_var"):
        assert torch.equal(before[name], after[name]), name  # BatchNorm statistics frozen
    assert not torch.equal(before["board.0.weight"], after["board.0.weight"])
    train_mode(network, ("detector", "batchnorm"))
    assert not network.screen.training and not network.board[1].training and network.training
    with pytest.raises(ValueError, match="GRID_TRAINING_FREEZE_UNKNOWN"):
        apply_freeze(network, ("encoder",))


def test_weighted_node_losses_equal_the_lab_losses_for_equal_weights() -> None:
    from game_predictor_worker.training_core.neural_grid_network import node_heatmap_loss

    torch.manual_seed(3)
    logits = torch.randn(4, 24, 12, 20)
    predicted = torch.rand(4, 24, 2) * 64
    nodes = torch.rand(4, 24, 2) * 64
    board = namespace(
        {
            "stride": 4,
            "heatmap_sigma": 1.0,
            "coordinate_loss_weight": 0.125,
            "heatmap_loss_weight": 0.05,
        }
    )
    weighted = weighted_node_losses(logits, predicted, nodes, torch.ones(4), board)
    lab_nodes = torch.nn.functional.smooth_l1_loss(predicted, nodes, beta=1.0) * 0.125
    lab_heat = node_heatmap_loss(logits, nodes, 4, 1.0) * 0.05
    assert torch.allclose(weighted["nodes"], lab_nodes)
    assert torch.allclose(weighted["node_heatmap"], lab_heat)
    zero_last = weighted_node_losses(logits, predicted, nodes, torch.tensor([1.0, 1, 1, 0]), board)
    first_three = weighted_node_losses(logits[:3], predicted[:3], nodes[:3], torch.ones(3), board)
    assert torch.allclose(zero_last["nodes"], first_three["nodes"])
    heavy = weighted_node_losses(logits, predicted, nodes, torch.tensor([4.0, 1, 1, 1]), board)
    assert not torch.allclose(heavy["nodes"], weighted["nodes"])


def grid(offset: float = 0.0, scale: float = 1.0) -> np.ndarray:
    lattice = np.array([(c, r) for r in range(4) for c in range(6)], dtype=np.float64)
    return lattice * 20 * scale + offset


def test_board_and_photo_metrics_follow_metrics_v1() -> None:
    label = grid()
    assert board_correct(label + 0.5, label)
    assert not board_correct(label + 10, label)
    assert photo_complete_correct([grid(), grid(500)], [grid(500), grid()])
    assert not photo_complete_correct([grid()], [grid(), grid(500)])  # missing board
    assert not photo_complete_correct([grid(), grid(500), grid(1000)], [grid(), grid(500)])
    assert not photo_complete_correct([grid(), grid(500) + 10], [grid(), grid(500)])


class FakePhotos:
    def __init__(self, targets: list[list[tuple[np.ndarray, int]]]) -> None:
        self._targets = targets

    def __len__(self) -> int:
        return len(self._targets)

    def rgb(self, index: int) -> np.ndarray:
        return np.full((300, 400, 3), 40 + index, dtype=np.uint8)

    def targets(self, index: int) -> list[tuple[np.ndarray, int]]:
        return self._targets[index]


def recipe() -> Any:
    from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset

    return load_preset("D")[0]


def test_grid_only_batches_are_deterministic_and_pad_with_zero_weight() -> None:
    from game_predictor_worker.images.grid_training_data import GridOnlyBatches

    photos = FakePhotos(
        [
            [(grid(30), 4), (grid(160), 1)],
            [(grid(30), 1)],
            [(grid(30), 1), (grid(160), 4), (grid(30, 0.9), 1), (grid(160, 0.9), 1), (grid(40), 1)],
        ]
    )
    first = GridOnlyBatches(photos, recipe(), batch_boards=8, seed=9, workers=2)  # type: ignore[arg-type]
    second = GridOnlyBatches(photos, recipe(), batch_boards=8, seed=9, workers=1)  # type: ignore[arg-type]
    try:
        for step in (0, 3, 1):
            a, b = first(step), second(step)
            assert a.keys() == {"crops", "nodes", "weights"}
            assert a["crops"].shape == (8, 3, 192, 320)
            for key in a:
                assert torch.equal(a[key], b[key]), (step, key)
        weights = first(0)["weights"].tolist() + first(1)["weights"].tolist()
        assert 0.0 in weights and 4.0 in weights
        assert all(value in {0.0, 1.0, 4.0} for value in weights)
    finally:
        first.close()
        second.close()


def test_lab_training_item_is_unchanged_by_the_shared_builder() -> None:
    from types import SimpleNamespace

    from game_predictor_worker.training_core.neural_grid_augmentation import (
        build_screen_item_with_indices,
    )
    from game_predictor_worker.vision_lab.neural_grid_data import build_training_item

    preset = recipe()
    rgb = np.random.default_rng(1).integers(0, 255, (300, 400, 3), dtype=np.uint8)
    boards = [SimpleNamespace(nodes=grid(30).astype(np.float32), unavailable_cells=(2,))]
    sample = SimpleNamespace(boards=boards)
    lab = build_training_item(rgb, sample, preset, np.random.default_rng(5))
    shared, indices = build_screen_item_with_indices(
        rgb,
        [(boards[0].nodes, (2,))],
        preset.screen,
        preset.board,
        preset.augmentation,
        np.random.default_rng(5),
    )
    assert indices == [0] * preset.board.boards_per_image
    for key in lab:
        assert np.array_equal(lab[key], shared[key]), key


def test_export_parity_is_relative_to_the_output_magnitude():
    # D-561 (TASK-1001): node coordinates of ~286 px differ by fp32 rounding alone.
    nodes = np.full((8, 24, 2), 286.1952, np.float32)
    rounded = nodes + np.float32(1.53e-4)
    unit = np.full((8, 24), 0.55, np.float32)
    verdict = parity_verdict([("board.nodes", nodes, rounded), ("board.peak", unit, unit)])
    assert verdict["passed"] and verdict["maxDelta"]["board.nodes"] > 1e-4
    assert verdict["maxScaledDelta"]["board.nodes"] < 1e-6
    assert verdict["toleranceScale"] == "max(1,|torch|)"
    # A real export error stays a failure: 0.05 px at 286 px and 2e-4 on unit outputs.
    assert not parity_verdict([("board.nodes", nodes, nodes + np.float32(0.05))])["passed"]
    assert not parity_verdict([("board.peak", unit, unit + np.float32(2e-4))])["passed"]
    broken = unit.copy()
    broken[0, 0] = np.nan
    assert not parity_verdict([("board.peak", unit, broken)])["passed"]
    assert parity_verdict([("board.peak", unit[:0], unit[:0])])["passed"]
