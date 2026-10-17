"""TASK-0996: grid-training supervisor; the trainer child is replaced by a file-writing fake."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_model_registry import historical_catalogue, validate_manifest
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector
from game_predictor_worker.images.grid_training_child import RECIPE_FILE, RECIPE_FINGERPRINT
from game_predictor_worker.images.grid_training_handler import (
    GridTrainingJobHandler,
    RunState,
    deterministic_ids,
    run_directory,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.training_core.gpu_lease import GpuLease, lease_path
from game_predictor_worker.training_core.grid_training_admission import (
    GRID_ONLY_V1,
    RunBudget,
    RuntimeFacts,
)

GPU = RuntimeFacts(
    cuda_available=True,
    torch_version="2.12.1+cu130",
    torchvision_version="0.27.1+cu130",
    cuda_version="13.0",
    total_vram_bytes=6_439_305_216,
    free_vram_bytes=6_000_000_000,
)
BASE = historical_catalogue()[0]
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def job(checkpoint: dict[str, object] | None = None) -> Any:
    value = create_job(
        JobType.GRID_TRAINING,
        game_id=UUID("11111111-1111-4111-8111-111111111111"),
        input_payload={
            "schema_version": 1,
            "training_kind": "grid-training-run-v1",
            "idempotency_key": str(uuid4()),
            "cohort_id": "22222222-2222-4222-8222-222222222222",
            "cohort_manifest_sha256": "c" * 64,
            "mode": "grid-only",
            "family_id": BASE["familyId"],
            "base_version_id": BASE["versionId"],
            "preset_id": GRID_ONLY_V1.preset_id,
            "preset_fingerprint": GRID_ONLY_V1.fingerprint,
            "seed": 7,
            "planned_steps": 30,
        },
    )
    return replace(value, status=JobStatus.PROCESSING, checkpoint_payload=checkpoint)


class Stopped(RuntimeError):
    pass


class Context:
    def __init__(self, current: Any, cancel_after_heartbeats: int | None = None) -> None:
        self._job = current
        self.payloads: list[tuple[str, dict[str, Any]]] = []
        self.heartbeats = 0
        self.cancel_after = cancel_after_heartbeats

    @property
    def job(self) -> Any:
        return self._job

    def heartbeat(self) -> None:
        self.heartbeats += 1
        if self.cancel_after is not None and self.heartbeats >= self.cancel_after:
            self._job = replace(self._job, cancel_requested_at=NOW)

    def checkpoint(self, *, checkpoint_payload: dict[str, Any], stage: str, **_: Any) -> None:
        assert checkpoint_payload["schema_version"] == 1  # domain checkpoint_job contract
        current, total = _["current"], _["total"]
        assert current >= self._job.progress_current and current <= total  # never decreases
        self._job = replace(self._job, progress_current=current, progress_total=total)
        self.payloads.append((stage, json.loads(json.dumps(checkpoint_payload))))
        # Like the store: a pending cancel is acknowledged unless the caller defers it.
        if self._job.cancel_requested_at is not None and _.get("acknowledge_cancellation", True):
            raise Stopped("cancelled")


class Store:
    def __init__(self, root: Path, *, qualification: str = "eligible") -> None:
        self.root = root
        self.qualification = qualification
        self.registered: list[tuple[UUID, dict[str, Any]]] = []
        self.fail_register = False

    def cohort(self, game_id: UUID, cohort_id: UUID) -> dict[str, Any]:
        return {
            "status": "frozen",
            "manifestSha256": "c" * 64,
            "manifestPath": "data/grid-training-cohorts/x/manifest.json",
            "mode": "grid-only",
            "baseVersionId": BASE["versionId"],
            "summary": {
                "roles": [
                    {
                        "role": "TRAIN",
                        "eligibleBoards": 30,
                        "eligiblePhotos": 10,
                        "eligibleFullPhotos": 0,
                    },
                    {
                        "role": "VALIDATION",
                        "eligibleBoards": 45,
                        "eligiblePhotos": 5,
                        "eligibleFullPhotos": 5,
                    },
                ]
            },
        }

    def eligibility(self, game_id: UUID, cohort_id: UUID) -> dict[str, Any]:
        reasons = [] if self.qualification == "eligible" else ["SOURCE_REMOVED_NEW_USE_BLOCKED"]
        return {"qualification": self.qualification, "reasons": reasons}

    def base_version(self, version_id: UUID) -> dict[str, Any]:
        assert str(version_id) == BASE["versionId"]
        return BASE

    def register(self, key: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        validate_manifest(payload)  # the real registry descriptor contract
        available, reason = GridModelArtifactInspector(self.root).inspect(payload)
        assert available, reason
        if self.fail_register:
            raise RuntimeError("crash after install")
        for existing_key, existing in self.registered:
            if existing_key == key:
                assert existing == payload
                return {"manifestSha256": "m" * 64}
        self.registered.append((key, payload))
        return {"manifestSha256": "m" * 64}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeChild:
    """Writes what the real trainer writes: checkpoint, progress, export and result."""

    def __init__(self, outcome: str = "exported", *, wait_for_cancel: bool = False) -> None:
        self.outcome = outcome
        self.wait_for_cancel = wait_for_cancel
        self.launches: list[dict[str, Any]] = []

    def __call__(self, command: list[str], environment: Any, cwd: Path) -> Any:
        spec_path = Path(command[command.index("--spec") + 1])
        spec = json.loads(spec_path.read_text(encoding="utf-8"))["payload"]
        self.launches.append(spec)
        run_dir = spec_path.parent
        attempt = spec["attempt"]
        checkpoints = run_dir / "checkpoints"
        checkpoints.mkdir(exist_ok=True)
        content = f"checkpoint {attempt}".encode()
        sha = hashlib.sha256(content).hexdigest()
        (checkpoints / f"{sha}.pt").write_bytes(content)
        pointer = {"path": f"{sha}.pt", "sha256": sha, "step": 30}
        (run_dir / "progress.json").write_text(
            json.dumps({"attempt": attempt, "step": 30, "checkpoint": pointer}), "utf-8"
        )
        child = self

        class Process:
            def poll(self) -> int | None:
                if child.wait_for_cancel and not (run_dir / "cancel.intent").exists():
                    return None
                child._finish(run_dir, spec, sha, pointer)
                return 0

            def kill(self) -> None:
                pass

            def wait(self, timeout: float) -> int:
                return 0

        return Process()

    def _finish(
        self, run_dir: Path, spec: dict[str, Any], sha: str, pointer: dict[str, Any]
    ) -> None:
        attempt = spec["attempt"]
        if self.outcome != "exported":
            result = {"status": "interrupted", "code": self.outcome}
        else:
            export = run_dir / f"export-{sha[:16]}"
            export.mkdir(exist_ok=True)
            for name in ("screen.onnx", "board.onnx", "weights.pt"):
                (export / name).write_bytes(f"{name} {sha}".encode())
            (export / "checkpoint.pt").write_bytes(
                (run_dir / "checkpoints" / pointer["path"]).read_bytes()
            )
            (export / "preset.json").write_bytes(RECIPE_FILE.read_bytes())
            provenance = {
                "runId": spec["jobId"],
                "exportId": str(uuid4()),
                "presetFingerprint": RECIPE_FINGERPRINT,
                "weightsSha256": _sha(export / "weights.pt"),
                "checkpointSha256": sha,
                "snapshotId": spec["cohort"]["manifestSha256"],
                "bestStep": 30,
            }
            bundle_files = {
                name: _sha(export / name) for name in ("screen.onnx", "board.onnx", "weights.pt")
            }
            (export / "bundle.json").write_text(
                json.dumps(
                    {
                        "preset": {"name": "D"},
                        "preset_fingerprint": RECIPE_FINGERPRINT,
                        "provenance": provenance,
                        "files": bundle_files,
                        "parity": {"passed": True},
                    }
                ),
                "utf-8",
            )
            files = {
                name: {"sha256": _sha(export / name), "sizeBytes": (export / name).stat().st_size}
                for name in (
                    "screen.onnx",
                    "board.onnx",
                    "weights.pt",
                    "checkpoint.pt",
                    "preset.json",
                    "bundle.json",
                )
            }
            result = {
                "status": "exported",
                "steps": 30,
                "bestStep": 30,
                "bestMetric": 0.5,
                "metric": "validation.board_correct_rate",
                "checkpoint": {"path": pointer["path"], "sha256": sha},
                "export": {"directory": export.name, "provenance": provenance, "files": files},
            }
        (run_dir / f"result-{attempt}.json").write_text(json.dumps(result), "utf-8")


def handler(root: Path, store: Store, child: FakeChild, **kwargs: Any) -> GridTrainingJobHandler:
    return GridTrainingJobHandler(
        store,
        artifact_root=root,
        python=Path("python.exe"),
        pythonpath="",
        repository_root=root,
        launcher=child,
        probe=lambda: GPU,
        wall_clock=lambda: NOW,
        sleep=lambda seconds: None,
        poll_seconds=0.0,
        **kwargs,
    )


def test_run_trains_installs_and_registers_one_not_evaluated_candidate(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    current = job()
    context = Context(current)
    handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    assert len(child.launches) == 1 and child.launches[0]["resume"] is None
    assert len(store.registered) == 1
    key, payload = store.registered[0]
    stage, last = context.payloads[-1]
    assert stage == "completed"
    checkpoint_sha = last["checkpoint"]["sha256"]
    version_id, version, expected_key = deterministic_ids(current.id, checkpoint_sha)
    assert (key, payload["versionId"], payload["version"]) == (
        expected_key,
        str(version_id),
        version,
    )
    assert payload["admission"] == "not_evaluated" and payload["baseVersionId"] == BASE["versionId"]
    assert payload["cohortId"] == current.input_payload["cohort_id"]
    assert last["registered"]["versionId"] == str(version_id)
    budget = RunBudget.from_payload(last["budget"])
    assert budget.attempts == 1 and budget.reserved_steps == 30
    assert last["chargedAt"] is None
    # A replay of the completed job neither trains nor registers again.
    again = Context(replace(current, checkpoint_payload=last))
    handler(tmp_path, store, child)(again, again.job)  # type: ignore[arg-type]
    assert len(child.launches) == 1 and len(store.registered) == 1


def test_crash_after_export_registers_the_same_version_once_without_retraining(
    tmp_path: Path,
) -> None:
    store, child = Store(tmp_path), FakeChild()
    store.fail_register = True
    current = job()
    context = Context(current)
    with pytest.raises(RuntimeError, match="crash after install"):
        handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    exported = [payload for stage, payload in context.payloads if stage == "exported"][-1]
    store.fail_register = False
    resumed = Context(replace(current, checkpoint_payload=exported))
    handler(tmp_path, store, child)(resumed, resumed.job)  # type: ignore[arg-type]
    assert len(child.launches) == 1  # no second training attempt
    assert len(store.registered) == 1
    payload = store.registered[0][1]
    assert (tmp_path / payload["managedDirectory"] / "training-base" / "receipt.json").is_file()


def test_corrupt_pointed_checkpoint_fails_without_a_candidate(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    current = job()
    run = run_directory(tmp_path, current.id) / "checkpoints"
    run.mkdir(parents=True)
    (run / "x.pt").write_bytes(b"changed")
    state = RunState(
        budget=RunBudget.for_preset(GRID_ONLY_V1, "train"),
        checkpoint={"path": "x.pt", "sha256": "0" * 64, "step": 6},
    )
    resumed = Context(replace(current, checkpoint_payload=state.payload()))
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(resumed, resumed.job)  # type: ignore[arg-type]
    assert error.value.code == "GRID_TRAINING_CHECKPOINT_CORRUPT"
    assert child.launches == [] and store.registered == []


def test_resume_passes_the_valid_checkpoint_and_charges_only_the_unconfirmed_interval(
    tmp_path: Path,
) -> None:
    store, child = Store(tmp_path), FakeChild()
    current = job()
    run = run_directory(tmp_path, current.id) / "checkpoints"
    run.mkdir(parents=True)
    (run / "c.pt").write_bytes(b"step six")
    budget = RunBudget.for_preset(GRID_ONLY_V1, "train").start_attempt().charge(100.0)
    state = RunState(
        budget=budget,
        attempt=1,
        charged_at=(NOW - timedelta(hours=8)).isoformat(),
        checkpoint={"path": "c.pt", "sha256": _sha(run / "c.pt"), "step": 6},
    )
    resumed = Context(replace(current, checkpoint_payload=state.payload()))
    handler(tmp_path, store, child)(resumed, resumed.job)  # type: ignore[arg-type]
    spec = child.launches[0]
    assert spec["resume"]["path"] == "c.pt" and spec["attempt"] == 2
    assert spec["budget"]["remainingSeconds"] == pytest.approx(3600 - 100 - 100)
    final = RunBudget.from_payload(resumed.payloads[-1][1]["budget"])
    assert final.attempts == 2 and final.used_seconds >= 200


def test_removed_source_blocks_new_training_use(tmp_path: Path) -> None:
    store, child = Store(tmp_path, qualification="blocked"), FakeChild()
    current = job()
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    assert error.value.code == "SOURCE_REMOVED_NEW_USE_BLOCKED"
    assert child.launches == []


def test_gpu_held_by_another_run_blocks_admission(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    GpuLease(lease_path(tmp_path), probe=lambda pid: "x").acquire(
        "smoke", "other", pid=4, created="x"
    )
    current = job()
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    assert error.value.code == "GRID_RUN_LEASE_BUSY"


def test_cancel_writes_the_intent_and_acknowledges_after_the_trainer_stops(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild("RUN_CANCELLED", wait_for_cancel=True)
    current = job()
    context = Context(current, cancel_after_heartbeats=2)
    with pytest.raises(Stopped):
        handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    run = run_directory(tmp_path, current.id)
    assert (run / "cancel.intent").read_text(encoding="utf-8") == "cancel"
    stage, payload = context.payloads[-1]
    assert stage == "cancelled" and payload["chargedAt"] is None
    assert store.registered == []


def test_trainer_failure_reports_its_code_without_a_candidate(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild("GRID_TRAINING_LOSS_NONFINITE")
    current = job()
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(Context(current), current)  # type: ignore[arg-type]
    assert error.value.code == "GRID_TRAINING_LOSS_NONFINITE"
    assert store.registered == []


def test_descriptor_is_persisted_before_install_and_reused_on_another_day(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    store.fail_register = True
    current = job()
    context = Context(current)
    with pytest.raises(RuntimeError, match="crash after install"):
        handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    stages = [stage for stage, _ in context.payloads]
    assert stages.index("descriptor") < len(stages)
    persisted = [payload for stage, payload in context.payloads if stage == "descriptor"][-1]
    frozen_on = persisted["export"]["descriptor"]["payload"]["inferenceManifest"]["frozenOn"]
    store.fail_register = False
    later = Context(replace(current, checkpoint_payload=persisted))
    next_day = GridTrainingJobHandler(
        store,
        artifact_root=tmp_path,
        python=Path("python.exe"),
        pythonpath="",
        repository_root=tmp_path,
        launcher=child,
        probe=lambda: GPU,
        wall_clock=lambda: NOW + timedelta(days=1),
        sleep=lambda seconds: None,
        poll_seconds=0.0,
    )
    next_day(later, later.job)  # type: ignore[arg-type]
    registered = store.registered[0][1]
    assert registered["inferenceManifest"]["frozenOn"] == frozen_on
    assert len(store.registered) == 1 and len(child.launches) == 1


def test_steps_repeated_after_a_resume_are_charged_again(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    current = job()
    run = run_directory(tmp_path, current.id) / "checkpoints"
    run.mkdir(parents=True)
    (run / "c.pt").write_bytes(b"step ten")
    budget = replace(
        RunBudget.for_preset(GRID_ONLY_V1, "train").start_attempt(), reserved_steps=100
    )
    state = RunState(
        budget=budget,
        attempt=1,
        checkpoint={"path": "c.pt", "sha256": _sha(run / "c.pt"), "step": 10},
    )
    resumed = Context(replace(current, checkpoint_payload=state.payload()))
    handler(tmp_path, store, child)(resumed, resumed.job)  # type: ignore[arg-type]
    assert child.launches[0]["budget"]["remainingSteps"] == GRID_ONLY_V1.max_steps - 100
    final = RunBudget.from_payload(resumed.payloads[-1][1]["budget"])
    assert final.reserved_steps == 100 + (30 - 10)  # 20 more steps, not max(100, 30)


def test_newer_checkpoint_of_an_orphaned_trainer_is_adopted_on_reclaim(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    budget = RunBudget.for_preset(GRID_ONLY_V1, "train").start_attempt()

    def prepared(progress_step: int, pointer_sha: str | None) -> Context:
        current = job()
        run = run_directory(tmp_path, current.id) / "checkpoints"
        run.mkdir(parents=True)
        (run / "old.pt").write_bytes(b"old")
        (run / "new.pt").write_bytes(b"new")
        old = {"path": "old.pt", "sha256": _sha(run / "old.pt"), "step": 5}
        new = {
            "path": "new.pt",
            "sha256": pointer_sha or _sha(run / "new.pt"),
            "step": progress_step,
        }
        (run.parent / "progress.json").write_text(
            json.dumps({"attempt": 1, "step": progress_step, "checkpoint": new}), "utf-8"
        )
        state = RunState(budget=budget, attempt=1, checkpoint=old)
        return Context(replace(current, checkpoint_payload=state.payload()))

    adopted = prepared(12, None)
    handler(tmp_path, store, child)(adopted, adopted.job)  # type: ignore[arg-type]
    assert child.launches[0]["resume"]["path"] == "new.pt"
    assert child.launches[0]["resume"]["step"] == 12
    rejected = prepared(99, "0" * 64)
    handler(tmp_path, store, child)(rejected, rejected.job)  # type: ignore[arg-type]
    assert child.launches[1]["resume"]["path"] == "old.pt"  # an unverifiable pointer is ignored


def test_adopted_orphan_steps_are_charged_from_the_attempt_start(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    current = job()
    run = run_directory(tmp_path, current.id)
    (run / "checkpoints").mkdir(parents=True)
    (run / "checkpoints" / "late.pt").write_bytes(b"late")
    late = {"path": "late.pt", "sha256": _sha(run / "checkpoints" / "late.pt"), "step": 26}
    (run / "progress.json").write_text(
        json.dumps({"attempt": 1, "step": 26, "checkpoint": late}), "utf-8"
    )
    budget = replace(RunBudget.for_preset(GRID_ONLY_V1, "train").start_attempt(), reserved_steps=20)
    state = RunState(budget=budget, attempt=1, attempt_start={"reserved": 0, "step": 0})
    resumed = Context(replace(current, checkpoint_payload=state.payload()))
    handler(tmp_path, store, child)(resumed, resumed.job)  # type: ignore[arg-type]
    assert child.launches[0]["resume"]["step"] == 26
    assert child.launches[0]["budget"]["remainingSteps"] == GRID_ONLY_V1.max_steps - 26
    final = RunBudget.from_payload(resumed.payloads[-1][1]["budget"])
    assert final.reserved_steps == 26 + (30 - 26)


def _resumable(tmp_path: Path, **state_fields: Any) -> tuple[Context, Path]:
    current = job()
    run = run_directory(tmp_path, current.id)
    (run / "checkpoints").mkdir(parents=True)
    (run / "checkpoints" / "old.pt").write_bytes(b"old")
    old = {"path": "old.pt", "sha256": _sha(run / "checkpoints" / "old.pt"), "step": 10}
    budget = RunBudget.for_preset(GRID_ONLY_V1, "train").start_attempt()
    fields = {"budget": budget, "attempt": 1, "checkpoint": old, **state_fields}
    state = RunState(**fields)
    return Context(replace(current, checkpoint_payload=state.payload())), run


def test_reported_steps_are_charged_even_without_a_newer_checkpoint(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    budget = replace(
        RunBudget.for_preset(GRID_ONLY_V1, "train").start_attempt(), reserved_steps=100
    )
    context, run = _resumable(tmp_path, budget=budget, attempt_start={"reserved": 90, "step": 10})
    old = json.loads(json.dumps(context.job.checkpoint_payload))["checkpoint"]
    (run / "progress.json").write_text(
        json.dumps({"attempt": 1, "step": 150, "checkpoint": old}), "utf-8"
    )
    handler(tmp_path, store, child)(context, context.job)  # type: ignore[arg-type]
    spec = child.launches[0]
    assert spec["resume"]["step"] == 10  # same checkpoint, but its 140 extra steps were charged
    assert spec["budget"]["remainingSteps"] == GRID_ONLY_V1.max_steps - (90 + 140)


def test_reclaim_waits_for_the_old_trainer_then_adopts_its_last_checkpoint(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    context, run = _resumable(
        tmp_path, attempt_start={"reserved": 0, "step": 0}, charged_at=NOW.isoformat()
    )
    lease = GpuLease(lease_path(tmp_path), probe=lambda pid: "alive")
    record = lease.acquire("train", str(context.job.id), pid=77, created="alive")
    clock = {"now": 0.0}
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += 40.0
        if len(sleeps) == 2:  # the old trainer publishes its last checkpoint, then exits
            (run / "checkpoints" / "last.pt").write_bytes(b"last")
            last = {"path": "last.pt", "sha256": _sha(run / "checkpoints" / "last.pt"), "step": 18}
            (run / "progress.json").write_text(
                json.dumps({"attempt": 1, "step": 18, "checkpoint": last}), "utf-8"
            )
            lease.release(record)

    supervisor = GridTrainingJobHandler(
        store,
        artifact_root=tmp_path,
        python=Path("python.exe"),
        pythonpath="",
        repository_root=tmp_path,
        launcher=child,
        probe=lambda: GPU,
        wall_clock=lambda: NOW + timedelta(seconds=clock["now"]),
        monotonic=lambda: clock["now"],
        sleep=sleep,
        poll_seconds=0.0,
    )
    supervisor(context, context.job)  # type: ignore[arg-type]
    spec = child.launches[0]
    assert spec["resume"]["path"] == "last.pt"
    # The 80 s spent waiting for the old trainer are charged in full, beyond the 100 s bound.
    assert spec["budget"]["remainingSeconds"] == pytest.approx(GRID_ONLY_V1.max_run_seconds - 80)


def test_finished_export_of_a_lost_supervisor_is_registered_without_new_budget(
    tmp_path: Path,
) -> None:
    store, child = Store(tmp_path), FakeChild()
    first = job()
    first_context = Context(first)
    handler(tmp_path, store, child)(first_context, first)  # type: ignore[arg-type]
    store.registered.clear()
    # Same run, but its supervisor died after the trainer wrote result-1.json.
    admitted = [payload for stage, payload in first_context.payloads if stage == "admitted"][-1]
    spent = RunBudget.from_payload(admitted["budget"]).charge(GRID_ONLY_V1.max_run_seconds)
    admitted = {**admitted, "budget": spent.to_payload(), "chargedAt": NOW.isoformat()}
    import shutil

    for name in ("models",):
        shutil.rmtree(tmp_path / name, ignore_errors=True)
    lost = Context(replace(first, checkpoint_payload=admitted))
    handler(tmp_path, store, child)(lost, lost.job)  # type: ignore[arg-type]
    assert len(child.launches) == 1  # no new training attempt
    assert len(store.registered) == 1
    assert lost.payloads[-1][0] == "completed"


def test_cancel_arriving_during_a_progress_write_waits_for_the_trainer_first(
    tmp_path: Path,
) -> None:
    store, child = Store(tmp_path), FakeChild("RUN_CANCELLED", wait_for_cancel=True)
    current = job()
    run = run_directory(tmp_path, current.id)
    order: list[str] = []

    class LateCancel(Context):
        def checkpoint(
            self, *, checkpoint_payload: dict[str, Any], stage: str, **rest: Any
        ) -> None:
            if stage == "training" and self._job.cancel_requested_at is None:
                # The request arrives after the heartbeat: the progress write keeps it pending.
                assert rest["acknowledge_cancellation"] is False
                self._job = replace(self._job, cancel_requested_at=NOW)
            if stage == "cancelled":
                order.append("result" if (run / "result-1.json").is_file() else "no-result")
            super().checkpoint(checkpoint_payload=checkpoint_payload, stage=stage, **rest)

    context = LateCancel(current)
    with pytest.raises(Stopped):
        handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    assert (run / "cancel.intent").read_text(encoding="utf-8") == "cancel"
    assert order == ["result"]  # acknowledged only after the trainer had stopped
    assert [stage for stage, _ in context.payloads][-1] == "cancelled"


class SilentChild(FakeChild):
    """A trainer killed hard after reporting progress: no result file at all."""

    def _finish(
        self, run_dir: Path, spec: dict[str, Any], sha: str, pointer: dict[str, Any]
    ) -> None:
        return None


def test_unconfirmed_steps_of_a_killed_trainer_keep_their_reservation(tmp_path: Path) -> None:
    store, child = Store(tmp_path), SilentChild()
    current = job()
    context = Context(current)
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    assert error.value.code == "GRID_TRAINING_CHILD_EXITED"
    budget = RunBudget.from_payload(context.payloads[-1][1]["budget"])
    assert budget.reserved_steps == 200  # the reserved block stays charged, not progress 30


def test_interrupted_result_without_steps_settles_nothing(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild("RUN_CANCELLED")
    current = job()
    context = Context(current)
    with pytest.raises(JobHandlerError):
        handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    budget = RunBudget.from_payload(context.payloads[-1][1]["budget"])
    assert budget.reserved_steps == 200


def test_admitted_attempt_is_charged_even_before_the_first_progress_write(tmp_path: Path) -> None:
    store, child = Store(tmp_path), FakeChild()
    current = job()
    context = Context(current)
    handler(tmp_path, store, child)(context, current)  # type: ignore[arg-type]
    admitted = [payload for stage, payload in context.payloads if stage == "admitted"][-1]
    assert admitted["chargedAt"] == NOW.isoformat()


def test_verified_export_without_a_result_file_is_registered_without_new_budget(
    tmp_path: Path,
) -> None:
    import shutil

    store, child = Store(tmp_path), FakeChild()
    first = job()
    first_context = Context(first)
    handler(tmp_path, store, child)(first_context, first)  # type: ignore[arg-type]
    store.registered.clear()
    shutil.rmtree(tmp_path / "models", ignore_errors=True)
    run = run_directory(tmp_path, first.id)
    (run / "result-1.json").unlink()  # crashed after the export, before its result
    admitted = [payload for stage, payload in first_context.payloads if stage == "admitted"][-1]
    spent = RunBudget.from_payload(admitted["budget"]).charge(GRID_ONLY_V1.max_run_seconds)
    lost = Context(replace(first, checkpoint_payload={**admitted, "budget": spent.to_payload()}))
    handler(tmp_path, store, child)(lost, lost.job)  # type: ignore[arg-type]
    assert len(child.launches) == 1 and len(store.registered) == 1
    export = next(run.glob("export-*"))
    preset = export / "preset.json"
    original = preset.read_bytes()
    preset.write_bytes(original.replace(b"board", b"BOARD", 1))  # a changed recipe is refused
    store.registered.clear()
    shutil.rmtree(tmp_path / "models", ignore_errors=True)
    changed = Context(replace(first, checkpoint_payload={**admitted, "budget": spent.to_payload()}))
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(changed, changed.job)  # type: ignore[arg-type]
    assert error.value.code == "GRID_RUN_BUDGET_EXHAUSTED" and store.registered == []
    preset.write_bytes(original)
    (export / "board.onnx").write_bytes(b"damaged")  # a damaged export is never adopted
    store.registered.clear()
    shutil.rmtree(tmp_path / "models", ignore_errors=True)
    other = Context(replace(first, checkpoint_payload={**admitted, "budget": spent.to_payload()}))
    with pytest.raises(JobHandlerError) as error:
        handler(tmp_path, store, child)(other, other.job)  # type: ignore[arg-type]
    assert error.value.code == "GRID_RUN_BUDGET_EXHAUSTED" and store.registered == []
