from dataclasses import replace

import pytest
import torch
from game_predictor_worker.training_core.grid_correction_metrics import (
    aggregate_checkpoint_metrics,
    photo_selection_key,
)
from game_predictor_worker.training_core.grid_rescue_training import TrainingExposure, rescue_recipe
from game_predictor_worker.training_core.grid_training import (
    PHOTO_CHECKPOINT_RULE,
    EarlyStopping,
    TrainingInterrupted,
    TrainingPlan,
    train,
)
from game_predictor_worker.training_core.grid_training_admission import SCREEN_GRID_CORRECTIONS_V1
from test_durable_v3_grid_training import Control, Tiny, batches


def metrics(photo=0.5, board=0.8, error=0.1):
    return {"photoCorrectRate": photo, "boardCorrectRate": board, "normalizedError": error}


def test_photo_first_ranking_and_strict_metric_state():
    stopping = EarlyStopping("maximize", 9, 0, 2, selection_rule=PHOTO_CHECKPOINT_RULE)
    assert stopping.update(0.5, 1, 0.1, 0.8)
    assert not stopping.update(0.4, 2, 0.0, 1.0)
    assert stopping.update(0.5, 3, 0.2, 0.9)
    assert stopping.update(0.5, 4, 0.1, 0.9)
    assert not stopping.update(0.5, 5, 0.1, 0.9)
    other = EarlyStopping("maximize", 9, 0, 2, selection_rule=PHOTO_CHECKPOINT_RULE)
    other.restore(stopping.state())
    assert other.state() == stopping.state()
    corrupt = stopping.state()
    corrupt.pop("bestBoard")
    with pytest.raises(ValueError):
        other.restore(corrupt)
    assert photo_selection_key(metrics(), 1) > photo_selection_key(metrics(), 2)
    assert aggregate_checkpoint_metrics(
        [metrics(1, 1, 0), metrics(0, 0, 1)], photo_first=True
    ) == metrics(0.5, 0.5, 0.5)


def test_actual_optimizer_exposure_and_restart_do_not_credit_work_after_best(tmp_path):
    preset = replace(
        SCREEN_GRID_CORRECTIONS_V1,
        learning_rate=0.01,
        steps_per_second_estimate=1,
        early_stopping=replace(
            SCREEN_GRID_CORRECTIONS_V1.early_stopping, evaluation_interval_seconds=1, patience=9
        ),
    )
    recipe = rescue_recipe("a" * 64, {"board": {"margin": 0.2}}, {"sha256": "b" * 64})
    plan = TrainingPlan.of("fixture", 7, preset, 3, {"rescueRecipe": recipe})
    assert plan.binding["policy"] == "grid-training-checkpoint-v3"

    def members(step):
        return [
            {
                "gameId": "game",
                "sourceId": "photo",
                "sourceSha256": "c" * 64,
                "cohortSha256": "d" * 64,
            }
        ]

    def loss(network, batch):
        return {
            "total": ((network.screen(batch["x"]) - batch["y"]) ** 2).mean()
            + ((network.board(batch["x"]) - batch["y"]) ** 2).mean()
        }

    def run(network, directory, control, exposure, resume=None):
        return train(
            network=network,
            preset=preset,
            plan=plan,
            batches=batches,
            losses=loss,
            evaluate=lambda network: metrics(),
            control=control,
            checkpoint_directory=directory,
            exposure=exposure,
            exposure_members=members,
            resume=resume,
        )

    uninterrupted = Tiny()
    initial = uninterrupted.screen.weight.detach().clone()
    full = TrainingExposure(recipe)
    result = run(uninterrupted, tmp_path / "full", Control(), full)
    assert not torch.equal(initial, uninterrupted.screen.weight)
    assert full.state()["confirmedSteps"] == 3
    assert result.best_step == 1
    assert result.exposure["lastStep"] == 1
    assert "board:variant" not in result.exposure["games"]["game"]
    assert "board:variant" in full.state()["games"]["game"]
    interrupted = Tiny()
    control = Control(stop_at=2)
    with pytest.raises(TrainingInterrupted):
        run(interrupted, tmp_path / "resume", control, TrainingExposure(recipe))
    path, sha, step = control.published[-1]
    assert step == 2
    restored = TrainingExposure(recipe)
    resumed = run(interrupted, tmp_path / "resume", Control(), restored, (path, sha))
    assert resumed.exposure == result.exposure
    assert restored.state() == full.state()
    assert all(
        torch.equal(value, interrupted.state_dict()[key])
        for key, value in uninterrupted.state_dict().items()
    )
