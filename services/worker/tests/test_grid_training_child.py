"""TASK-0996: the real trainer child on CPU with a tiny generated frozen cohort.

No operator data, GPU or service: a 64x48 generated cohort (TASK-0995 fixture), a fresh
network as the base, two training steps, a real ONNX export and parity check.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import torch
from game_predictor_worker.images import grid_training_child as child
from game_predictor_worker.training_core import grid_training_admission as admission
from game_predictor_worker.training_core.gpu_lease import lease_path
from game_predictor_worker.training_core.neural_grid_network import NeuralGridNetwork
from game_predictor_worker.training_core.process_identity import own_identity
from test_grid_cohort_dataset import SnapshotFixture

PRESET_FILE = (
    Path(__file__).resolve().parents[1]
    / "src/game_predictor_worker/vision_lab/neural_grid_presets/D.json"
)


def tiny_preset() -> admission.GridTrainingPreset:
    return replace(
        admission.GRID_ONLY_V1,
        preset_id="grid-only-test",
        batch_items=4,
        data_workers=1,
        steps_per_second_estimate=1.0,
        early_stopping=replace(
            admission.GRID_ONLY_V1.early_stopping, evaluation_interval_seconds=1.0
        ),
    )


def base(root: Path) -> dict[str, Any]:
    directory = root / "models/grid-engine/test/v1/training-base"
    directory.mkdir(parents=True)
    torch.manual_seed(0)
    stream = io.BytesIO()
    torch.save(NeuralGridNetwork(4).state_dict(), stream)
    (directory / "weights.pt").write_bytes(stream.getvalue())
    preset = PRESET_FILE.read_bytes()
    (directory / "preset.json").write_bytes(preset)
    return {
        "versionId": "33333333-3333-4333-8333-333333333333",
        "managedDirectory": "models/grid-engine/test/v1",
        "weightsSha256": hashlib.sha256(stream.getvalue()).hexdigest(),
        "presetSha256": hashlib.sha256(preset).hexdigest(),
    }


def spec(root: Path, fixture: SnapshotFixture, preset: admission.GridTrainingPreset) -> Path:
    pid, created = own_identity()
    body = {
        "format": child.SPEC_FORMAT,
        "jobId": "44444444-4444-4444-8444-444444444444",
        "attempt": 1,
        "artifactRoot": str(root),
        "cohort": {
            "gameId": fixture.game,
            "cohortId": fixture.cohort,
            "manifestPath": fixture.manifest_pin["path"],
            "manifestSha256": fixture.manifest_pin["sha256"],
        },
        "base": base(root),
        "preset": {"id": preset.preset_id, "fingerprint": preset.fingerprint},
        "seed": 3,
        "plannedSteps": 2,
        "budget": {"remainingSeconds": 600.0, "remainingSteps": 4000},
        "supervisor": {"pid": pid, "created": created},
        "resume": None,
        "requireCuda": False,
        "device": "cpu",
        "dataWorkers": 1,
    }
    run_dir = root / "grid-training/runs" / body["jobId"]
    run_dir.mkdir(parents=True)
    (run_dir / "supervisor.heartbeat").write_text("now", encoding="utf-8")
    # The supervisor reserves steps before the trainer may run them.
    (run_dir / "allowance.json").write_text(json.dumps({"attempt": 1, "step": 200}), "utf-8")
    path = run_dir / "spec.json"
    path.write_text(
        json.dumps({"payload": body, "sha256": child.sha256_bytes(child.canonical(body))}),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def cohort(tmp_path: Path) -> SnapshotFixture:
    fixture = SnapshotFixture(tmp_path)
    for _ in range(2):
        fixture.source("TRAIN")
    fixture.source("VALIDATION", full=True)
    fixture.source("REGRESSION", full=True)
    fixture.publish()
    return fixture


def test_real_trainer_trains_checkpoints_exports_and_releases_the_gpu_lease(
    tmp_path: Path, cohort: SnapshotFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = tiny_preset()
    monkeypatch.setitem(admission.PRESETS, preset.preset_id, preset)
    path = spec(tmp_path, cohort, preset)
    assert child.run(path) == 0
    result = json.loads((path.parent / "result-1.json").read_text(encoding="utf-8"))
    assert result["status"] == "exported", result
    assert result["steps"] == 2 and len(result["history"]) == 2
    export = path.parent / result["export"]["directory"]
    bundle = json.loads((export / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["parity"]["passed"] is True
    assert bundle["provenance"]["checkpointSha256"] == result["checkpoint"]["sha256"]
    assert bundle["provenance"]["trainingPresetFingerprint"] == preset.fingerprint
    assert bundle["preset"]["name"] == "D"
    for name, item in result["export"]["files"].items():
        assert child.sha256_file(export / name) == item["sha256"], name
    assert not lease_path(tmp_path).exists()
    # The detector stayed frozen: screen weights equal the base, the board stage moved.
    # The export holds the best evaluation (step 1, still at warm-up LR 0), so compare the
    # last checkpoint's live weights after step 2.
    checkpoint = torch.load(
        path.parent / "checkpoints" / result["checkpoint"]["path"],
        map_location="cpu",
        weights_only=True,
    )
    exported = checkpoint["modelState"]
    original = torch.load(
        tmp_path / "models/grid-engine/test/v1/training-base/weights.pt",
        map_location="cpu",
        weights_only=True,
    )
    screen = [key for key in original if key.startswith("screen.")]
    board = [
        key for key in original if key.startswith("board.") and original[key].is_floating_point()
    ]
    assert all(torch.equal(original[key], exported[key]) for key in screen)
    assert any(not torch.equal(original[key], exported[key]) for key in board)


def test_trainer_refuses_a_changed_base_and_writes_a_failed_result(
    tmp_path: Path, cohort: SnapshotFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = tiny_preset()
    monkeypatch.setitem(admission.PRESETS, preset.preset_id, preset)
    path = spec(tmp_path, cohort, preset)
    (tmp_path / "models/grid-engine/test/v1/training-base/preset.json").write_text("{}", "utf-8")
    assert child.run(path) == 3
    result = json.loads((path.parent / "result-1.json").read_text(encoding="utf-8"))
    assert result == {
        "format": child.RESULT_FORMAT,
        "attempt": 1,
        "status": "failed",
        "code": "GRID_TRAINING_BASE_DRIFT",
        "steps": 0,
    }
    assert not lease_path(tmp_path).exists()


def test_cancel_intent_stops_the_trainer_before_the_next_step(
    tmp_path: Path, cohort: SnapshotFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = tiny_preset()
    monkeypatch.setitem(admission.PRESETS, preset.preset_id, preset)
    path = spec(tmp_path, cohort, preset)
    (path.parent / "cancel.intent").write_text("cancel", encoding="utf-8")
    assert child.run(path) == 3
    result = json.loads((path.parent / "result-1.json").read_text(encoding="utf-8"))
    assert (result["status"], result["code"]) == ("interrupted", "RUN_CANCELLED")


def test_trainer_refuses_a_base_whose_decoding_differs_from_the_approved_recipe(
    tmp_path: Path, cohort: SnapshotFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = tiny_preset()
    monkeypatch.setitem(admission.PRESETS, preset.preset_id, preset)
    path = spec(tmp_path, cohort, preset)
    body = json.loads(path.read_text(encoding="utf-8"))["payload"]
    changed = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
    changed["board"]["canvas"] = [256, 160]
    content = json.dumps(changed).encode()
    (tmp_path / "models/grid-engine/test/v1/training-base/preset.json").write_bytes(content)
    body["base"]["presetSha256"] = hashlib.sha256(content).hexdigest()
    path.write_text(
        json.dumps({"payload": body, "sha256": child.sha256_bytes(child.canonical(body))}),
        encoding="utf-8",
    )
    assert child.run(path) == 3
    result = json.loads((path.parent / "result-1.json").read_text(encoding="utf-8"))
    assert result["code"] == "GRID_TRAINING_RECIPE_INCOMPATIBLE"


def test_recovered_export_must_match_its_recorded_hashes(tmp_path: Path) -> None:
    export = tmp_path / "export"
    export.mkdir()
    for name in ("screen.onnx", "board.onnx", "weights.pt"):
        (export / name).write_bytes(name.encode())
    checkpoint = tmp_path / "c.pt"
    checkpoint.write_bytes(b"checkpoint")
    (export / "checkpoint.pt").write_bytes(b"checkpoint")
    preset = b'{"name":"D"}'
    (export / "preset.json").write_bytes(preset)
    files = {
        name: child.sha256_file(export / name)
        for name in ("screen.onnx", "board.onnx", "weights.pt")
    }
    bundle = {
        "files": files,
        "parity": {"passed": True},
        "provenance": {
            "checkpointSha256": child.sha256_file(checkpoint),
            "weightsSha256": files["weights.pt"],
        },
    }
    child._verify_recovered(export, bundle, preset, checkpoint)
    (export / "board.onnx").write_bytes(b"damaged")
    with pytest.raises(child.ChildError, match="GRID_TRAINING_EXPORT_CORRUPT"):
        child._verify_recovered(export, bundle, preset, checkpoint)


def test_watchdog_ends_the_process_when_the_supervisor_disappears(tmp_path: Path) -> None:
    exits: list[int] = []
    body = {"attempt": 3, "budget": {"remainingSeconds": 600.0}, "supervisor": {}}
    result = tmp_path / "result-3.json"
    alive = {"value": True}
    watchdog = child.Watchdog(
        body, tmp_path, result, alive=lambda spec, run: alive["value"], exit_process=exits.append
    )
    assert watchdog.check() is False and exits == []
    alive["value"] = False
    assert watchdog.check() is False and exits == []  # the loop may still publish its checkpoint
    watchdog._lost_since = -1000.0
    assert watchdog.check() is True and exits == [4]
    assert json.loads(result.read_text(encoding="utf-8"))["code"] == "RUN_SUPERVISOR_LOST"
    stopped = child.Watchdog(
        body,
        tmp_path,
        tmp_path / "other.json",
        alive=lambda spec, run: False,
        exit_process=exits.append,
    )
    stopped._lost_since = -1000.0
    stopped.stop()
    assert stopped.check() is False and exits == [4]
    clock = {"now": 0.0}
    timed = child.Watchdog(
        body,
        tmp_path,
        tmp_path / "t.json",
        alive=lambda spec, run: True,
        exit_process=exits.append,
        clock=lambda: clock["now"],
    )
    clock["now"] = 600.0 + child.WATCHDOG_GRACE_SECONDS + 1
    assert timed.check() is True and exits == [4, 4]


def test_trainer_waits_for_reserved_steps_and_stops_without_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(child, "ALLOWANCE_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(child, "ALLOWANCE_POLL_SECONDS", 0.05)
    pid, created = own_identity()
    body = {
        "attempt": 2,
        "budget": {"remainingSeconds": 600.0, "remainingSteps": 4000},
        "supervisor": {"pid": pid, "created": created},
        "resume": {"step": 10},
    }
    (tmp_path / "supervisor.heartbeat").write_text("now", encoding="utf-8")
    control = child.ChildControl(body, tmp_path, None, None)  # type: ignore[arg-type]
    (tmp_path / "allowance.json").write_text(json.dumps({"attempt": 2, "step": 12}), "utf-8")
    control.before_step(10)
    control.before_step(11)
    with pytest.raises(child.TrainingInterrupted, match="RUN_BUDGET_EXHAUSTED"):
        control.before_step(12)
    (tmp_path / "allowance.json").write_text(json.dumps({"attempt": 1, "step": 99}), "utf-8")
    with pytest.raises(child.TrainingInterrupted, match="RUN_BUDGET_EXHAUSTED"):
        control.before_step(12)  # another attempt's allowance never counts


def test_result_is_durable_before_the_gpu_lease_is_released(
    tmp_path: Path, cohort: SnapshotFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_worker.training_core.gpu_lease import GpuLease

    preset = tiny_preset()
    monkeypatch.setitem(admission.PRESETS, preset.preset_id, preset)
    path = spec(tmp_path, cohort, preset)
    (tmp_path / "models/grid-engine/test/v1/training-base/preset.json").write_text("{}", "utf-8")
    seen: list[bool] = []
    original = GpuLease.release

    def release(self: Any, record: Any) -> None:
        seen.append((path.parent / "result-1.json").is_file())
        original(self, record)

    monkeypatch.setattr(GpuLease, "release", release)
    assert child.run(path) == 3
    assert seen == [True]
    result = json.loads((path.parent / "result-1.json").read_text(encoding="utf-8"))
    assert result["steps"] == 0


def test_final_count_follows_every_completed_step_and_checkpoint(tmp_path: Path) -> None:
    pid, created = own_identity()
    body = {
        "attempt": 1,
        "budget": {"remainingSeconds": 600.0, "remainingSteps": 4000},
        "supervisor": {"pid": pid, "created": created},
        "resume": None,
    }
    counter = {"step": 0}
    control = child.ChildControl(body, tmp_path, None, None, counter)  # type: ignore[arg-type]
    control.progress(40, 40, {})  # step 40 completed, export may fail afterwards
    assert counter["step"] == 40
    control.checkpoint_published(tmp_path / "c.pt", "0" * 64, 41)
    assert counter["step"] == 41
