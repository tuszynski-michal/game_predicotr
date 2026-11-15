"""TASK-1205/D-612: a correction run must beat its own base network on VALIDATION."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from game_predictor_worker.training_core.grid_training import (
    TrainingInterrupted,
    TrainingPlan,
    TrainingResult,
    train,
)
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_CORRECTIONS_V1,
    GRID_ONLY_V1,
)
from test_durable_v3_grid_training import Control, Tiny, batches, losses

RULE = "validation-board-correct-photo-macro-error-earliest-v1"
PRESET = replace(
    GRID_CORRECTIONS_V1,
    learning_rate=1e-2,
    steps_per_second_estimate=1.0,
    early_stopping=replace(GRID_CORRECTIONS_V1.early_stopping, evaluation_interval_seconds=3.0),
)


def plan() -> TrainingPlan:
    value = TrainingPlan.of("run-floor", 5, PRESET, 12, {"x": 1})
    assert value.evaluation_steps == 3
    return value


class Scripted:
    """VALIDATION measures in call order; the first call is step 0 when the floor is on."""

    def __init__(self, *measures: tuple[float, float]) -> None:
        self.measures = list(measures)
        self.calls = 0

    def __call__(self, network: Any) -> dict[str, float]:
        rate, error = self.measures[self.calls]
        self.calls += 1
        return {"boardCorrectRate": rate, "normalizedError": error}


def run(tmp_path: Path, evaluate: Scripted, **kwargs: Any) -> TrainingResult:
    return train(
        network=Tiny(),
        preset=PRESET,
        plan=plan(),
        batches=batches,
        losses=losses,
        evaluate=evaluate,
        control=kwargs.pop("control", Control()),
        checkpoint_directory=tmp_path,
        baseline_floor=True,
        **kwargs,
    )


def test_checkpoints_below_the_base_do_not_beat_the_floor(tmp_path: Path) -> None:
    # The 12ffda06 shape: base 0.678, every trained checkpoint lower.
    evaluate = Scripted(
        (0.678, 0.018), (0.573, 0.0197), (0.52, 0.02), (0.573, 0.0192), (0.626, 0.0188)
    )
    result = run(tmp_path, evaluate)
    assert result.baseline_floor == {"boardCorrectRate": 0.678, "normalizedError": 0.018}
    assert result.best_step == 12 and not result.beats_baseline
    # The floor neither enters the history nor changes the selection of trained steps.
    assert [entry["step"] for entry in result.history] == [3, 6, 9, 12]
    assert result.checkpoint_selection is not None
    assert result.checkpoint_selection["rule"] == RULE
    assert result.checkpoint_selection["step"] == 12


@pytest.mark.parametrize(
    ("trained", "beats"),
    [
        ((0.7, 0.03), True),  # more correct boards
        ((0.6, 0.019), True),  # equal rate, lower error
        ((0.6, 0.02), False),  # exact tie is no gain
        ((0.6, 0.021), False),
    ],
)
def test_strictly_better_checkpoint_beats_the_floor(
    tmp_path: Path, trained: tuple[float, float], beats: bool
) -> None:
    evaluate = Scripted((0.6, 0.02), trained, (0.1, 0.5), (0.1, 0.5), (0.1, 0.5))
    result = run(tmp_path, evaluate)
    assert result.best_step == 3
    assert result.beats_baseline is beats


def test_resume_keeps_the_stored_floor_without_measuring_the_trained_network(
    tmp_path: Path,
) -> None:
    control = Control(stop_at=7)
    with pytest.raises(TrainingInterrupted):
        run(tmp_path / "a", Scripted((0.678, 0.018), (0.5, 0.02), (0.55, 0.02)), control=control)
    path, sha, step = control.published[-1]
    assert step == 7
    resumed_evaluate = Scripted((0.6, 0.02), (0.6, 0.02))
    result = run(tmp_path / "a", resumed_evaluate, resume=(path, sha))
    assert resumed_evaluate.calls == 2  # steps 9 and 12 only, no second step-0 measure
    assert result.baseline_floor == {"boardCorrectRate": 0.678, "normalizedError": 0.018}
    assert not result.beats_baseline


def test_pre_floor_checkpoint_resumes_without_a_floor(tmp_path: Path) -> None:
    control = Control(stop_at=7)
    with pytest.raises(TrainingInterrupted):
        train(
            network=Tiny(),
            preset=PRESET,
            plan=plan(),
            batches=batches,
            losses=losses,
            evaluate=Scripted((0.5, 0.02), (0.55, 0.02)),
            control=control,
            checkpoint_directory=tmp_path,
        )
    path, sha, _ = control.published[-1]
    result = run(tmp_path, Scripted((0.6, 0.02), (0.6, 0.02)), resume=(path, sha))
    assert result.baseline_floor is None and result.beats_baseline


def test_floor_is_limited_to_the_correction_rule(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="GRID_TRAINING_BASELINE_FLOOR_UNSUPPORTED"):
        train(
            network=Tiny(),
            preset=replace(GRID_ONLY_V1, steps_per_second_estimate=1.0),
            plan=TrainingPlan.of("run-x", 5, GRID_ONLY_V1, 12, {"x": 1}),
            batches=batches,
            losses=losses,
            evaluate=lambda network: 0.0,
            control=Control(),
            checkpoint_directory=tmp_path,
            baseline_floor=True,
        )


def test_invalid_floor_measure_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="GRID_TRAINING_SELECTION_INVALID"):
        run(tmp_path, Scripted((1.5, 0.02)))


def correction_cohort(root: Path) -> Any:
    from test_grid_cohort_dataset import SnapshotFixture

    fixture = SnapshotFixture(root)
    for _ in range(2):
        fixture.source("TRAIN")
    fixture.source("VALIDATION", full=True)
    fixture.source("REGRESSION", full=True)
    fixture.publish(
        change=lambda manifest: manifest.update(
            schemaVersion="application-grid-snapshot-v2",
            policyVersion="application-grid-corrections-v2",
        )
    )
    return fixture


@pytest.mark.parametrize("beaten", [False, True])
def test_child_exports_only_a_checkpoint_that_beats_its_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, beaten: bool
) -> None:
    from game_predictor_worker.images import grid_training_child as child
    from game_predictor_worker.images import grid_training_data
    from game_predictor_worker.training_core import grid_training_admission as admission
    from test_grid_training_child import spec

    preset = replace(
        GRID_CORRECTIONS_V1,
        batch_items=4,
        data_workers=1,
        steps_per_second_estimate=1.0,
        early_stopping=replace(GRID_CORRECTIONS_V1.early_stopping, evaluation_interval_seconds=1.0),
    )
    monkeypatch.setitem(admission.PRESETS, preset.preset_id, preset)
    base_measure = (0.5, 0.02) if beaten else (1.0, 0.0)
    scripted = Scripted(base_measure, (0.75, 0.01), (0.75, 0.01))
    monkeypatch.setattr(
        grid_training_data, "correction_evaluator", lambda *args, **kwargs: scripted
    )
    exported: list[Any] = []

    def export(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # The real export (ONNX, parity, consistency proof) has its own tests.
        exported.append(args[6])
        return {"directory": "export-stub"}

    monkeypatch.setattr(child, "_export", export)
    path = spec(tmp_path, correction_cohort(tmp_path), preset)
    assert child.run(path) == (0 if beaten else 3)
    result = json.loads((path.parent / "result-1.json").read_text(encoding="utf-8"))
    assert result["baselineFloor"] == {
        "boardCorrectRate": base_measure[0],
        "normalizedError": base_measure[1],
    }
    if beaten:
        assert result["status"] == "exported", result
        assert len(exported) == 1 and exported[0].beats_baseline
        assert result["export"] == {"directory": "export-stub"}
    else:
        assert result["status"] == "no_improvement", result
        assert result["code"] == "GRID_TRAINING_NO_IMPROVEMENT"
        assert result["checkpointSelection"]["rule"] == RULE and "export" not in result
        assert exported == [] and not list(path.parent.glob("export-*"))
