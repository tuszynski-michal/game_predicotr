"""TASK-1005: grid-training presets, cohort cost, GPU lease and run admission."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from game_predictor_worker.training_core import grid_training_admission as admission
from game_predictor_worker.training_core.gpu_lease import (
    GpuLease,
    GpuLeaseError,
    lease_path,
)
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_ONLY_V1,
    PRESETS,
    SCREEN_GRID_V1,
    SMOKE_MAX_SECONDS,
    SMOKE_MAX_STEPS,
    SMOKE_STARTUP_SECONDS,
    SMOKE_TRAIN_SECONDS,
    CohortCounts,
    GridRunBudgetError,
    RunBudget,
    RuntimeFacts,
    estimate_cohort_cost,
    evaluate_admission,
    preset_for_mode,
)
from game_predictor_worker.training_core.process_identity import process_created

GPU = RuntimeFacts(
    cuda_available=True,
    torch_version="2.12.1+cu130",
    torchvision_version="0.27.1+cu130",
    cuda_version="13.0",
    device_name="NVIDIA GeForce RTX 4050 Laptop GPU",
    total_vram_bytes=6_439_305_216,
    free_vram_bytes=6_200_000_000,
)
MINIMUM = CohortCounts("grid-only", 30, 10, 0, 15, 5, 15, 5)
SRC = Path(__file__).resolve().parents[1] / "src"


def admit(**overrides: object) -> admission.AdmissionDecision:
    values: dict[str, object] = {
        "preset_id": GRID_ONLY_V1.preset_id,
        "preset_fingerprint": GRID_ONLY_V1.fingerprint,
        "purpose": "train",
        "runtime": GPU,
        "lease_state": "free",
        "counts": MINIMUM,
    }
    values.update(overrides)
    return evaluate_admission(**values)  # type: ignore[arg-type]


def test_presets_are_versioned_distinct_and_fingerprint_their_parameters() -> None:
    assert set(PRESETS) == {"grid-only-v1", "screen-grid-v1"}
    assert GRID_ONLY_V1.mode == "grid-only" and SCREEN_GRID_V1.mode == "screen+grid"
    assert GRID_ONLY_V1.frozen_modules == ("detector", "batchnorm")
    assert GRID_ONLY_V1.fingerprint != SCREEN_GRID_V1.fingerprint
    assert len(GRID_ONLY_V1.fingerprint) == 64
    # The approval record is not a training parameter; every parameter is.
    assert replace(GRID_ONLY_V1, approved=False).fingerprint == GRID_ONLY_V1.fingerprint
    assert replace(GRID_ONLY_V1, max_steps=1).fingerprint != GRID_ONLY_V1.fingerprint
    assert preset_for_mode("grid-only") is GRID_ONLY_V1
    assert preset_for_mode("screen+grid") is SCREEN_GRID_V1
    assert preset_for_mode("unknown") is None
    assert preset_for_mode("grid-only", {"x": replace(GRID_ONLY_V1, approved=False)}) is None


def test_cohort_cost_uses_boards_for_grid_only_and_full_photos_for_screen() -> None:
    small = estimate_cohort_cost(GRID_ONLY_V1, MINIMUM)
    assert (small.train_items, small.steps_per_epoch) == (30, 1)
    assert small.planned_train_seconds == 600.0  # 10 photos x 60 s, above the 300 s floor
    assert small.planned_steps == 1200
    assert small.evaluations_planned == 2
    assert small.estimated_run_seconds == 180 + 600 + 2 * 90 + 60
    assert small.within_budget
    large = estimate_cohort_cost(GRID_ONLY_V1, CohortCounts("grid-only", 900, 120, 90))
    assert large.planned_train_seconds == 1800.0 and large.planned_steps == 3600
    assert large.within_budget
    screen = estimate_cohort_cost(SCREEN_GRID_V1, CohortCounts("screen+grid", 99, 12, 11))
    assert (screen.train_items, screen.steps_per_epoch) == (11, 1)
    assert estimate_cohort_cost(GRID_ONLY_V1, CohortCounts("grid-only", 0, 0, 0)).planned_steps == 0


def test_admitted_train_run_starts_its_first_attempt_with_a_fresh_budget() -> None:
    decision = admit()
    assert decision.admitted and decision.reasons == ()
    assert decision.budget is not None
    assert decision.budget.attempts == 1
    assert decision.budget.max_steps == GRID_ONLY_V1.max_steps
    assert decision.budget.max_seconds == GRID_ONLY_V1.max_run_seconds
    assert decision.cost is not None and decision.cost.train_items == 30


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"runtime": None}, "GRID_RUN_GPU_UNAVAILABLE"),
        (
            {"runtime": RuntimeFacts(cuda_available=False, torch_version="2.12.1+cpu")},
            "GRID_RUN_GPU_UNAVAILABLE",
        ),
        ({"runtime": replace(GPU, torch_version="2.12.1+cu128")}, "GRID_RUN_RUNTIME_INCOMPATIBLE"),
        ({"runtime": replace(GPU, cuda_version="12.8")}, "GRID_RUN_RUNTIME_INCOMPATIBLE"),
        ({"runtime": replace(GPU, torchvision_version=None)}, "GRID_RUN_RUNTIME_INCOMPATIBLE"),
        ({"runtime": replace(GPU, free_vram_bytes=4_000_000_000)}, "GRID_RUN_VRAM_INSUFFICIENT"),
        ({"runtime": replace(GPU, total_vram_bytes=None)}, "GRID_RUN_VRAM_INSUFFICIENT"),
        ({"lease_state": "held"}, "GRID_RUN_LEASE_BUSY"),
        ({"lease_state": "unknown"}, "GRID_RUN_LEASE_UNKNOWN"),
        ({"preset_id": "grid-only-v0"}, "GRID_RUN_PRESET_NOT_APPROVED"),
        ({"preset_fingerprint": "0" * 64}, "GRID_RUN_PRESET_NOT_APPROVED"),
        (
            {"presets": {"grid-only-v1": replace(GRID_ONLY_V1, approved=False)}},
            "GRID_RUN_PRESET_NOT_APPROVED",
        ),
        ({"counts": replace(MINIMUM, mode="screen+grid")}, "GRID_RUN_COHORT_MODE_MISMATCH"),
        ({"counts": None}, "GRID_RUN_COHORT_EMPTY"),
        ({"counts": CohortCounts("grid-only", 0, 0, 0)}, "GRID_RUN_COHORT_EMPTY"),
        (
            {"presets": {"grid-only-v1": replace(GRID_ONLY_V1, max_run_seconds=600.0)}},
            "GRID_RUN_COHORT_COST_EXCEEDS_BUDGET",
        ),
    ],
)
def test_each_missing_resource_or_approval_blocks_the_run(
    overrides: dict[str, object], reason: str
) -> None:
    presets = overrides.get("presets")
    if isinstance(presets, dict):
        # Same parameters keep the same fingerprint unless a parameter changed.
        overrides.setdefault("preset_fingerprint", presets["grid-only-v1"].fingerprint)
    decision = admit(**overrides)
    assert not decision.admitted
    assert reason in decision.reasons
    assert decision.budget is None or decision.budget.attempts == 0


def test_reasons_are_all_collected_in_a_fixed_order() -> None:
    decision = admit(runtime=None, lease_state="held", counts=replace(MINIMUM, mode="screen+grid"))
    assert decision.reasons == (
        "GRID_RUN_COHORT_MODE_MISMATCH",
        "GRID_RUN_GPU_UNAVAILABLE",
        "GRID_RUN_LEASE_BUSY",
    )


def test_stale_lease_does_not_block_admission_because_acquire_takes_it_over() -> None:
    assert admit(lease_state="stale").admitted


def test_smoke_needs_a_known_preset_but_not_its_approval_and_has_its_own_limits() -> None:
    unapproved = {"screen-grid-v1": replace(SCREEN_GRID_V1, approved=False)}
    decision = evaluate_admission(
        preset_id="screen-grid-v1",
        preset_fingerprint=SCREEN_GRID_V1.fingerprint,
        purpose="smoke",
        runtime=GPU,
        lease_state="free",
        presets=unapproved,
    )
    assert decision.admitted and decision.cost is None
    assert decision.budget is not None
    assert (decision.budget.max_steps, decision.budget.max_seconds) == (50, 600.0)
    assert (SMOKE_MAX_STEPS, SMOKE_TRAIN_SECONDS, SMOKE_STARTUP_SECONDS, SMOKE_MAX_SECONDS) == (
        50,
        120.0,
        300.0,
        600.0,
    )
    unknown = evaluate_admission(
        preset_id="screen-grid-v9",
        preset_fingerprint="0" * 64,
        purpose="smoke",
        runtime=GPU,
        lease_state="free",
    )
    assert unknown.reasons == ("GRID_RUN_PRESET_NOT_APPROVED",)


def test_resume_keeps_used_steps_and_seconds_across_a_durable_round_trip() -> None:
    first = admit()
    assert first.budget is not None
    used = first.budget
    for _ in range(7):
        used = used.reserve_step()
    used = used.charge(321.5)
    stored = json.loads(json.dumps(used.to_payload()))
    restored = RunBudget.from_payload(stored)
    resumed = admit(stored_budget=restored)
    assert resumed.admitted and resumed.budget is not None
    assert resumed.budget.reserved_steps == 7
    assert resumed.budget.used_seconds == 321.5
    assert resumed.budget.attempts == 2
    assert resumed.budget.remaining_seconds == GRID_ONLY_V1.max_run_seconds - 321.5


def test_resume_of_an_exhausted_or_foreign_budget_is_blocked() -> None:
    fresh = RunBudget.for_preset(GRID_ONLY_V1, "train")
    exhausted = fresh.charge(GRID_ONLY_V1.max_run_seconds)
    assert admit(stored_budget=exhausted).reasons == ("GRID_RUN_BUDGET_EXHAUSTED",)
    steps = replace(fresh, reserved_steps=fresh.max_steps)
    assert admit(stored_budget=steps).reasons == ("GRID_RUN_BUDGET_EXHAUSTED",)
    smoke = RunBudget.for_preset(GRID_ONLY_V1, "smoke")
    assert admit(stored_budget=smoke).reasons == ("GRID_RUN_BUDGET_PRESET_MISMATCH",)
    other = RunBudget.for_preset(SCREEN_GRID_V1, "train")
    assert admit(stored_budget=other).reasons == ("GRID_RUN_BUDGET_PRESET_MISMATCH",)
    with pytest.raises(GridRunBudgetError, match="GRID_RUN_BUDGET_EXHAUSTED"):
        exhausted.start_attempt()
    with pytest.raises(GridRunBudgetError, match="GRID_RUN_BUDGET_EXHAUSTED"):
        steps.reserve_step()


@pytest.mark.parametrize("seconds", [-1.0, float("nan"), float("inf")])
def test_clock_moving_back_exhausts_the_budget(seconds: float) -> None:
    assert RunBudget.for_preset(GRID_ONLY_V1, "train").charge(seconds).exhausted


def test_corrupt_budget_payload_is_rejected() -> None:
    envelope = RunBudget.for_preset(GRID_ONLY_V1, "train").charge(10).to_payload()
    tampered = json.loads(json.dumps(envelope))
    tampered["payload"]["used_seconds"] = 0.0
    with pytest.raises(GridRunBudgetError, match="GRID_RUN_BUDGET_CORRUPT"):
        RunBudget.from_payload(tampered)
    with pytest.raises(GridRunBudgetError, match="GRID_RUN_BUDGET_CORRUPT"):
        RunBudget.from_payload({"payload": "x", "sha256": "y"})


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_lease_is_exclusive_and_survives_a_new_lease_object(tmp_path: Path) -> None:
    clock = Clock()
    path = lease_path(tmp_path)
    lease = GpuLease(path, clock=clock, probe=lambda pid: "created-1")
    record = lease.acquire("train", "run-1", pid=11, created="created-1")
    assert lease.observe().state == "held"
    reopened = GpuLease(path, clock=clock, probe=lambda pid: "created-1")
    assert reopened.observe().state == "held"
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_BUSY"):
        reopened.acquire("smoke", "smoke-1", pid=12, created="created-2")
    renewed = lease.renew(record)
    assert renewed.expires_at == clock.now + 60.0
    lease.release(record)
    assert lease.observe().state == "free" and not path.exists()


def test_live_owner_keeps_an_expired_lease_and_a_dead_one_is_taken_over(tmp_path: Path) -> None:
    clock = Clock()
    alive = {"value": "created-1"}
    path = lease_path(tmp_path)
    lease = GpuLease(path, clock=clock, probe=lambda pid: alive["value"])
    old = lease.acquire("train", "run-1", pid=11, created="created-1")
    clock.now += 120.0
    assert lease.observe().state == "held"
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_BUSY"):
        lease.acquire("train", "run-2", pid=12, created="created-2")
    alive["value"] = None  # the owning process ended without releasing
    assert lease.observe().state == "stale"
    new = lease.acquire("train", "run-2", pid=12, created="created-2")
    assert new.token != old.token
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_LOST"):
        lease.renew(old)
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_LOST"):
        lease.release(old)  # a foreign token never removes the current holder
    assert path.exists()
    alive["value"] = "reused-pid-other-process"
    clock.now += 120.0
    assert lease.observe().state == "stale"  # PID reuse with another creation time


def test_unreadable_record_or_unknown_process_state_blocks_without_removal(tmp_path: Path) -> None:
    path = lease_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    lease = GpuLease(path, probe=lambda pid: "x")
    assert lease.observe().state == "unknown"
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_UNKNOWN"):
        lease.acquire("train", "run-1", pid=1, created="x")
    assert path.read_text(encoding="utf-8") == "{"

    def broken(pid: int) -> str | None:
        raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE")

    path.unlink()
    clock = Clock()
    first = GpuLease(path, clock=clock, probe=lambda pid: "x")
    first.acquire("train", "run-1", pid=1, created="x")
    clock.now += 120.0
    second = GpuLease(path, clock=clock, probe=broken)
    assert second.observe().state == "unknown"
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_UNKNOWN"):
        second.acquire("train", "run-2", pid=2, created="y")


HOLDER = """
import sys, time
from pathlib import Path
from game_predictor_worker.training_core.gpu_lease import GpuLease
lease = GpuLease(Path(sys.argv[1]))
lease.acquire("train", "child-run")
print("held", flush=True)
sys.stdin.readline()
"""


def test_real_child_process_holds_the_lease_until_it_exits(tmp_path: Path) -> None:
    path = lease_path(tmp_path)
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    child = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=environment,
        text=True,
    )
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "held"
        clock = Clock()
        clock.now = 10.0**12  # far past the term: only the live process keeps the lease
        parent = GpuLease(path, clock=clock)
        assert parent.observe().state == "held"
        with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_BUSY"):
            parent.acquire("smoke", "parent")
    finally:
        assert child.stdin is not None
        child.stdin.write("\n")
        child.stdin.flush()
        child.wait(timeout=30)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert process_created(record["pid"]) != record["process_created"]
    assert parent.observe().state == "stale"
    taken = parent.acquire("smoke", "parent")
    assert taken.pid == os.getpid()
    parent.release(taken)


def test_smoke_without_a_gpu_is_blocked_before_the_lease_and_writes_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_worker.vision_lab import grid_training_smoke

    monkeypatch.setattr(
        grid_training_smoke, "probe_runtime", lambda: RuntimeFacts(cuda_available=False)
    )
    report = tmp_path / "report.json"
    code = grid_training_smoke.run_smoke(tmp_path / "snapshot", tmp_path, report, "screen-grid-v1")
    assert code == 2
    value = json.loads(report.read_text(encoding="utf-8"))
    assert value["status"] == "blocked"
    assert value["admission"]["reasons"] == ["GRID_RUN_GPU_UNAVAILABLE"]
    assert not lease_path(tmp_path).exists()


@pytest.mark.parametrize(
    "field",
    [
        {"expires_at": None},
        {"expires_at": "soon"},
        {"expires_at": float("inf")},
        {"acquired_at": True},
        {"pid": True},
        {"pid": 0},
        {"pid": "11"},
        {"token": ""},
        {"run_kind": "eval"},
        {"process_created": 5},
    ],
)
def test_semantically_invalid_record_is_unknown_and_kept(
    tmp_path: Path, field: dict[str, object]
) -> None:
    path = lease_path(tmp_path)
    lease = GpuLease(path, probe=lambda pid: "x")
    record = lease.acquire("train", "run-1", pid=11, created="x")
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update(field)
    text = json.dumps(value)  # inf is written as Infinity, which json.loads accepts
    path.write_text(text, encoding="utf-8")
    assert lease.observe().state == "unknown"
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_UNKNOWN"):
        lease.acquire("smoke", "smoke-1", pid=12, created="y")
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_UNKNOWN"):
        lease.renew(record)
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_UNKNOWN"):
        lease.release(record)
    assert path.read_text(encoding="utf-8") == text


def test_release_of_a_missing_record_is_a_lost_lease(tmp_path: Path) -> None:
    lease = GpuLease(lease_path(tmp_path), probe=lambda pid: "x")
    record = lease.acquire("train", "run-1", pid=11, created="x")
    lease.release(record)
    with pytest.raises(GpuLeaseError, match="GRID_RUN_LEASE_LOST"):
        lease.release(record)


def watchdog_for(tmp_path: Path, report: dict[str, object], clock: Clock, exits: list[int]):
    from game_predictor_worker.vision_lab.grid_training_smoke import SmokeWatchdog

    return SmokeWatchdog(
        clock.now,
        report,  # type: ignore[arg-type]
        tmp_path / "report.json",
        clock=clock,
        exit_process=exits.append,
        poll_seconds=0.01,
    )


def test_watchdog_enforces_startup_training_and_run_limits(tmp_path: Path) -> None:
    clock, exits = Clock(), []
    report: dict[str, object] = {"phases": {}}
    watchdog = watchdog_for(tmp_path, report, clock, exits)
    start = clock.now
    assert watchdog.expired(start + 330.0) is None
    assert watchdog.expired(start + 330.5) == "startup_timeout"
    report["phases"] = {"first_step_done": 111.0}
    assert watchdog.expired(start + 111.0 + 150.0) is None
    assert watchdog.expired(start + 111.0 + 150.5) == "train_timeout"
    report["phases"] = {"first_step_done": 500.0}
    assert watchdog.expired(start + 630.5) == "watchdog_timeout"
    clock.now = start + 111.0 + 151.0
    report["phases"] = {"first_step_done": 111.0}
    assert watchdog.check() is True
    assert exits == [124]
    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written["status"] == "train_timeout"


def test_stopped_watchdog_never_writes_or_exits(tmp_path: Path) -> None:
    clock, exits = Clock(), []
    report: dict[str, object] = {"phases": {}, "status": "completed"}
    watchdog = watchdog_for(tmp_path, report, clock, exits)
    watchdog.start()
    watchdog.stop()
    clock.now += 10_000.0
    assert watchdog.check() is False
    assert watchdog._thread is not None and not watchdog._thread.is_alive()
    assert exits == [] and not (tmp_path / "report.json").exists()
    assert report["status"] == "completed"


def test_failed_measurement_stops_the_watchdog_and_releases_the_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_worker.vision_lab import grid_training_smoke

    events: list[str] = []

    class Recorder:
        def __init__(self, *arguments: object, **keywords: object) -> None:
            pass

        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    def broken(*arguments: object) -> int:
        assert lease_path(tmp_path).exists()
        raise RuntimeError("boom")

    monkeypatch.setattr(grid_training_smoke, "probe_runtime", lambda: GPU)
    monkeypatch.setattr(grid_training_smoke, "SmokeWatchdog", Recorder)
    monkeypatch.setattr(grid_training_smoke, "_measure", broken)
    with pytest.raises(RuntimeError, match="boom"):
        grid_training_smoke.run_smoke(tmp_path, tmp_path, tmp_path / "r.json", "screen-grid-v1")
    assert events == ["start", "stop"]
    assert not lease_path(tmp_path).exists()
