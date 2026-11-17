"""Actual-work watchdog, preserved grants and serialization across fresh processes."""

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from game_predictor_worker.images.grid_training_child import Watchdog
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_CORRECTIONS_V1,
    RunBudget,
    digest,
)
from game_predictor_worker.training_core.run_activity import (
    PROGRESS_LIMIT_POLICY,
    ActivityObserver,
    ActivityPublisher,
)
from game_predictor_worker.training_core.run_progress_supervision import (
    prepare_supervision,
    verify_supervision,
)


def row():
    preset = GRID_CORRECTIONS_V1
    budget = replace(
        RunBudget.for_preset(preset, "train"), reserved_steps=800, used_seconds=7200, attempts=1
    )
    return {
        "id": "00000000-0000-4000-8000-000000001244",
        "game_id": "g",
        "job_type": "grid_training",
        "status": "cancelled",
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "input_payload": {
            "training_kind": "grid-training-run-v1",
            "preset_id": preset.preset_id,
            "preset_fingerprint": preset.fingerprint,
            "mode": "grid-only",
            "planned_steps": 3600,
        },
        "checkpoint_payload": {
            "format": "grid-training-state-v1",
            "budget": budget.to_payload(),
            "attempt": 1,
            "chargedAt": None,
            "checkpoint": None,
            "history": [],
            "other": {"pin": 1},
        },
    }


def grant(value):
    return prepare_supervision(
        value,
        {"path": "a" * 64 + ".pt", "sha256": "a" * 64, "step": 600},
        at="2026-11-17T15:00:00+00:00",
        reason="Explicit operator approval",
    )


def test_policy_preserves_all_consumption_and_survives_fresh_process(tmp_path):
    source = row()
    before = deepcopy(source)
    preview = grant(source)
    assert source == before
    state = preview["payload"]["afterState"]
    budget = RunBudget.from_payload(state["budget"])
    assert (budget.max_seconds, budget.used_seconds, budget.reserved_steps, budget.attempts) == (
        None,
        7200,
        800,
        1,
    )
    assert budget.max_steps == 8000 and budget.remaining_steps == 7200
    assert not budget.charge(100_000).exhausted
    assert budget.charge(100_000).used_seconds == 107_200
    assert budget.with_current_limits(GRID_CORRECTIONS_V1) == budget
    assert state["other"] == before["checkpoint_payload"]["other"]
    saved = tmp_path / "budget.json"
    saved.write_text(json.dumps(budget.to_payload(), allow_nan=False))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys\n"
            "from game_predictor_worker.training_core.grid_training_admission import RunBudget\n"
            "b=RunBudget.from_payload(json.load(open(sys.argv[1])))\n"
            "assert b.max_seconds is None\n"
            "assert not b.charge(100000).exhausted\n"
            "print(b.reserved_steps)\n",
            str(saved),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert result.stdout.strip() == "800"


def test_grant_replay_does_not_replenish_consumption_and_detects_drift():
    source = row()
    preview = grant(source)
    assert verify_supervision(source, preview, preview["sha256"])
    applied = deepcopy(source)
    applied["checkpoint_payload"] = deepcopy(preview["payload"]["afterState"])
    budget = RunBudget.from_payload(applied["checkpoint_payload"]["budget"])
    applied["checkpoint_payload"]["budget"] = budget.charge(30).reserve_step().to_payload()
    applied["status"] = "processing"
    assert not verify_supervision(applied, preview, preview["sha256"])
    drifted = deepcopy(source)
    drifted["checkpoint_payload"]["other"]["pin"] = 2
    with pytest.raises(ValueError, match="RUN_STATE_DRIFT"):
        verify_supervision(drifted, preview, preview["sha256"])


@pytest.mark.parametrize(
    "change,code",
    [
        ({"status": "processing"}, "RUN_NOT_STOPPED"),
        ({"lease_token": "active"}, "RUN_LEASE_ACTIVE"),
        ({"status": "completed"}, "RUN_NOT_STOPPED"),
    ],
)
def test_active_and_completed_jobs_cannot_receive_a_grant(change, code):
    value = row()
    value.update(change)
    with pytest.raises(ValueError, match=code):
        grant(value)


def test_grant_rejects_checkpoint_and_input_tampering():
    value = row()
    preview = grant(value)
    preview["payload"]["afterState"]["other"]["pin"] = 2
    preview["sha256"] = digest(preview["payload"])
    with pytest.raises(ValueError, match="PREVIEW_CHANGE_INVALID"):
        verify_supervision(value, preview, preview["sha256"])
    value["input_payload"]["content_experiment"] = {"arm": 1}
    with pytest.raises(ValueError, match="RUN_POLICY_UNSUPPORTED"):
        grant(value)


def test_only_completed_work_renews_the_stall_window(tmp_path):
    now = [0.0]

    def clock():
        return now[0]

    observer = ActivityObserver(tmp_path, "run", 2, clock=clock)
    old = ActivityPublisher(tmp_path, "run", 1, clock=clock)
    old.advance("index", 1)
    now[0] = 299
    assert not observer.stalled()
    now[0] = 300
    assert observer.stalled()  # old-attempt work does not renew
    publisher = ActivityPublisher(tmp_path, "run", 2, clock=clock)
    publisher.advance("index", 10)
    assert not observer.stalled()
    now[0] += 299
    publisher.advance("index", 10)  # repeated heartbeat/report is not completed work
    assert not observer.stalled()
    now[0] += 1
    assert observer.stalled()
    publisher.advance("index", 11)
    assert not observer.stalled()


def test_replayed_or_malformed_activity_does_not_renew(tmp_path):
    now = [0.0]
    observer = ActivityObserver(tmp_path, "run", 1, clock=lambda: now[0])
    publisher = ActivityPublisher(tmp_path, "run", 1, clock=lambda: now[0])
    publisher.advance("optimizer", 600)
    assert not observer.stalled()
    path = tmp_path / "activity.json"
    value = json.loads(path.read_text())
    value["sequence"] += 1
    now[0] = 299
    path.write_text(json.dumps(value))
    assert not observer.stalled()
    now[0] = 300
    assert observer.stalled()
    path.write_text("{" + "x" * 20000)
    assert observer.stalled()


def test_watchdog_keeps_supervisor_loss_and_stall_protection(tmp_path):
    now = [0.0]
    alive = [True]
    spec = {
        "jobId": "run",
        "attempt": 1,
        "budget": {
            "remainingSeconds": None,
            "timePolicy": PROGRESS_LIMIT_POLICY,
            "stallSeconds": 300,
        },
    }
    watchdog = Watchdog(
        spec,
        tmp_path,
        tmp_path / "result.json",
        clock=lambda: now[0],
        alive=lambda *_: alive[0],
        exit_process=lambda _: None,
    )
    activity = ActivityPublisher(tmp_path, "run", 1, clock=lambda: now[0])
    for step in range(40):
        now[0] += 250
        activity.advance("optimizer", step)
        assert watchdog.expired() is None
    assert now[0] > 7200
    alive[0] = False
    assert watchdog.expired() is None
    now[0] += 100
    assert watchdog.expired() == "RUN_SUPERVISOR_LOST"


def test_null_time_ceiling_requires_the_explicit_policy():
    budget = replace(RunBudget.for_preset(GRID_CORRECTIONS_V1, "train"), max_seconds=None)
    with pytest.raises(ValueError):
        RunBudget.from_payload(budget.to_payload())


def test_child_watchdog_records_and_exits_on_completed_work_stall(tmp_path):
    now = [0.0]
    exits = []
    spec = {
        "jobId": "run",
        "attempt": 2,
        "budget": {
            "remainingSeconds": None,
            "timePolicy": PROGRESS_LIMIT_POLICY,
            "stallSeconds": 300,
        },
    }
    watchdog = Watchdog(
        spec,
        tmp_path,
        tmp_path / "result.json",
        clock=lambda: now[0],
        alive=lambda *_: True,
        exit_process=exits.append,
    )
    activity = ActivityPublisher(tmp_path, "run", 2, clock=lambda: now[0])
    activity.advance("optimizer", 600)
    assert watchdog.expired() is None
    now[0] = 300
    assert watchdog.expired() == "RUN_PROGRESS_STALLED"
    assert watchdog.check()
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["watchdog"] is True and result["attempt"] == 2
    assert result["code"] == "RUN_PROGRESS_STALLED" and result["status"] == "interrupted"
    assert exits == [4]


def test_progress_policy_still_honors_explicit_cancellation(tmp_path):
    from game_predictor_worker.images.grid_training_child import ChildControl
    from game_predictor_worker.training_core.runtime import TrainingInterrupted

    spec = {
        "jobId": "run",
        "attempt": 1,
        "budget": {
            "remainingSeconds": None,
            "remainingSteps": 8000,
            "timePolicy": PROGRESS_LIMIT_POLICY,
            "stallSeconds": 300,
        },
    }
    control = ChildControl(spec, tmp_path, None, None)
    (tmp_path / "cancel.intent").write_text("cancel")
    with pytest.raises(TrainingInterrupted, match="RUN_CANCELLED"):
        control.check()


def test_validation_crop_work_renews_supervision_beyond_total_300_seconds(tmp_path):
    import numpy as np
    from game_predictor_worker.images.grid_training_child import RECIPE_FILE
    from game_predictor_worker.images.grid_training_data import validation_crops
    from game_predictor_worker.training_core.grid_training import namespace

    now = [0.0]
    observer = ActivityObserver(tmp_path, "run", 1, clock=lambda: now[0])
    publisher = ActivityPublisher(tmp_path, "run", 1, clock=lambda: now[0])
    calls = []

    class Photos:
        def __len__(self):
            return 3

        def rgb(self, _index):
            now[0] += 200
            return np.zeros((48, 64, 3), np.uint8)

        def targets(self, _index):
            nodes = np.array(
                [(4 + x * 8, 4 + y * 8) for y in range(4) for x in range(6)], dtype=float
            )
            return [(nodes, 4)]

    def activity(phase, current):
        publisher.advance(phase, current)
        calls.append((phase, current))
        assert not observer.stalled()

    crops, labels = validation_crops(
        Photos(), namespace(json.loads(RECIPE_FILE.read_text())), activity=activity
    )
    assert len(crops) == len(labels) == 3 and now[0] == 600
    assert calls == [("validation-crops", 1), ("validation-crops", 2), ("validation-crops", 3)]
    now[0] += 300
    assert observer.stalled()


@pytest.mark.parametrize("elapsed", [-1, float("nan"), float("inf")])
def test_invalid_recovery_clock_fails_closed_for_progress_policy(elapsed):
    budget = replace(
        RunBudget.for_preset(GRID_CORRECTIONS_V1, "train"),
        max_seconds=None,
        limit_policy=PROGRESS_LIMIT_POLICY,
    )
    with pytest.raises(ValueError, match="GRID_RUN_CLOCK_INVALID"):
        budget.charge(elapsed)


def test_persistent_auxiliary_publication_lock_does_not_crash_or_fake_progress(
    tmp_path, monkeypatch
):
    from game_predictor_worker.training_core import run_activity

    def locked(*_):
        raise PermissionError("Reader holds the auxiliary path")

    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr(run_activity.time, "sleep", lambda _: None)
    now = [0.0]
    observer = ActivityObserver(tmp_path, "run", 1, clock=lambda: now[0])
    ActivityPublisher(tmp_path, "run", 1).advance("optimizer", 600)
    assert not (tmp_path / "activity.json").exists()
    now[0] = 300
    assert observer.stalled()


def test_activity_publication_retries_a_short_windows_reader_lock(tmp_path, monkeypatch):
    original = Path.replace
    attempts = []

    def replace_path(path, target):
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError("Transient Windows reader lock")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", replace_path)
    ActivityPublisher(tmp_path, "run", 1).advance("optimizer", 1)
    assert len(attempts) == 2
    assert json.loads((tmp_path / "activity.json").read_text())["current"] == 1
