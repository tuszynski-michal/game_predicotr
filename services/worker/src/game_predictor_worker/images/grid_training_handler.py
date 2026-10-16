"""Supervisor of one application grid-training job in the ``grid_training`` lane (D-558).

The supervisor owns the job lease, the durable budget and the database work; the GPU
trainer is a child process in the configured CUDA interpreter (``grid_training_child``).
State that must survive a restart lives in ``jobs.checkpoint_payload``: the budget
envelope, the published checkpoint pointer, the export and the registered version. On a
re-claim after a lost lease the time since the last persisted charge is charged in full,
an exported candidate is installed and registered idempotently, and training resumes
from the last valid checkpoint. A corrupt pointed checkpoint fails the job without a
candidate. Publication, activation and default changes are never performed here.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

from game_predictor_api.domain.jobs import Job

from ..jobs.runtime import JobExecutionContext, JobHandlerError, _ExecutionStopped
from ..training_core.gpu_lease import GpuLease, lease_path
from ..training_core.grid_training_admission import (
    PRESETS,
    CohortCounts,
    RunBudget,
    RuntimeFacts,
    evaluate_admission,
)
from ..training_core.process_identity import own_identity
from .grid_training_child import (
    RECIPE_FILE,
    RECIPE_FINGERPRINT,
    SPEC_FORMAT,
    canonical,
    sha256_bytes,
    sha256_file,
    write_json_atomic,
)

STATE_FORMAT = "grid-training-state-v1"
POLL_SECONDS = 5.0
# Steps are reserved in the job payload before the trainer may run them (P0-2 R2).
ALLOWANCE_STEPS = 200
# The trainer stops itself 60 s after the supervisor heartbeat goes stale; its watchdog
# allows 30 s more for the step checkpoint before it ends the process.
UNCONFIRMED_LIMIT_SECONDS = 60.0 + 30.0 + 2 * POLL_SECONDS
CANCEL_WAIT_SECONDS = 180.0
PROBE_TIMEOUT_SECONDS = 90.0
RUNS_DIRECTORY = ("grid-training", "runs")
CHILD_MODULE = "game_predictor_worker.images.grid_training_child"
_NAMESPACE = UUID("b9a2d6f4-1c3e-4c58-9a0f-6f1e5d0c9b27")


class GridTrainingStore(Protocol):
    """Database facts the supervisor needs; the SQL implementation lives in the worker CLI."""

    def cohort(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]: ...

    def eligibility(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]: ...

    def base_version(self, version_id: UUID) -> Mapping[str, Any]: ...

    def register(self, key: UUID, payload: dict[str, Any]) -> Mapping[str, Any]: ...


@dataclass
class RunState:
    budget: RunBudget
    attempt: int = 0
    charged_at: str | None = None
    checkpoint: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    registered: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    attempt_start: dict[str, int] | None = None

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,  # the job checkpoint contract (domain ``checkpoint_job``)
            "format": STATE_FORMAT,
            "budget": self.budget.to_payload(),
            "attempt": self.attempt,
            "chargedAt": self.charged_at,
            "checkpoint": self.checkpoint,
            "export": self.export,
            "registered": self.registered,
            "history": self.history,
            "attemptStart": self.attempt_start,
        }

    @classmethod
    def load(cls, value: Mapping[str, Any] | None, initial: RunBudget) -> RunState:
        if not value:
            return cls(budget=initial)
        if value.get("format") != STATE_FORMAT:
            raise JobHandlerError("GRID_TRAINING_STATE_CORRUPT", "Run state format differs.")
        try:
            budget = RunBudget.from_payload(value["budget"])
        except (KeyError, ValueError) as error:
            raise JobHandlerError(
                "GRID_TRAINING_STATE_CORRUPT", "Run budget is corrupt."
            ) from error
        return cls(
            budget=budget,
            attempt=int(value.get("attempt", 0)),
            charged_at=value.get("chargedAt"),
            checkpoint=value.get("checkpoint"),
            export=value.get("export"),
            registered=value.get("registered"),
            history=list(value.get("history") or []),
            attempt_start=value.get("attemptStart"),
        )


def _payload(job: Job) -> dict[str, Any]:
    return cast(dict[str, Any], job.input_payload)


def counts_from_header(header: Mapping[str, Any]) -> CohortCounts:
    """Per-role eligible counts of a frozen cohort header (the TASK-0995 summary)."""
    roles = {item["role"]: item for item in header["summary"]["roles"]}

    def value(role: str, key: str) -> int:
        return int(roles.get(role, {}).get(key, 0))

    return CohortCounts(
        mode=str(header["mode"]),
        train_boards=value("TRAIN", "eligibleBoards"),
        train_photos=value("TRAIN", "eligiblePhotos"),
        train_full_photos=value("TRAIN", "eligibleFullPhotos"),
        validation_boards=value("VALIDATION", "eligibleBoards"),
        validation_photos=value("VALIDATION", "eligiblePhotos"),
        regression_boards=value("REGRESSION", "eligibleBoards"),
        regression_photos=value("REGRESSION", "eligiblePhotos"),
    )


def run_directory(artifact_root: Path, job_id: UUID) -> Path:
    return artifact_root.joinpath(*RUNS_DIRECTORY, str(job_id))


def deterministic_ids(job_id: UUID, checkpoint_sha256: str) -> tuple[UUID, str, UUID]:
    """(versionId, version, idempotency key) of the candidate of one checkpoint."""
    version_id = uuid.uuid5(_NAMESPACE, f"{job_id}:{checkpoint_sha256}")
    version = f"r{job_id.hex[:8]}-{checkpoint_sha256[:8]}"
    key = uuid.uuid5(_NAMESPACE, f"{job_id}:export:{checkpoint_sha256}")
    return version_id, version, key


ChildLauncher = Callable[[list[str], Mapping[str, str], Path], Any]


def _default_launcher(command: list[str], environment: Mapping[str, str], cwd: Path) -> Any:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


class GridTrainingJobHandler:
    def __init__(
        self,
        store: GridTrainingStore,
        *,
        artifact_root: Path,
        python: Path | None,
        pythonpath: str,
        repository_root: Path,
        launcher: ChildLauncher = _default_launcher,
        probe: Callable[[], RuntimeFacts] | None = None,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self.store = store
        self.artifact_root = artifact_root.resolve()
        self.python, self.pythonpath = python, pythonpath
        self.repository_root = repository_root
        self.launcher = launcher
        self._probe = probe
        self.wall_clock, self.monotonic, self.sleep = wall_clock, monotonic, sleep
        self.poll_seconds = poll_seconds

    # --- entry point ---------------------------------------------------------------------------

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        payload = _payload(job)
        if (payload.get("schema_version"), payload.get("training_kind")) != (
            1,
            "grid-training-run-v1",
        ) or job.game_id is None:
            raise JobHandlerError("GRID_TRAINING_PAYLOAD_INVALID", "Pinned run payload differs.")
        preset = PRESETS.get(str(payload["preset_id"]))
        if preset is None or preset.fingerprint != payload["preset_fingerprint"]:
            raise JobHandlerError("GRID_RUN_PRESET_NOT_APPROVED", "Preset is unknown or changed.")
        state = RunState.load(job.checkpoint_payload, RunBudget.for_preset(preset, "train"))
        run_dir = run_directory(self.artifact_root, job.id)
        run_dir.mkdir(parents=True, exist_ok=True)
        if state.registered is not None:
            return self._finish(context, state)
        self._recover_previous_attempt(context, job, state, run_dir)
        if state.export is None:
            self._train(context, job, state, run_dir)
        self._install_and_register(context, job, state, run_dir)
        self._finish(context, state)

    # --- budget and persistence ----------------------------------------------------------------

    def _now_iso(self) -> str:
        return self.wall_clock().isoformat()

    def _recover_previous_attempt(
        self, context: JobExecutionContext, job: Job, state: RunState, run_dir: Path
    ) -> None:
        """Settle an attempt whose supervisor was lost, in this order: wait until its trainer
        has ended, charge the whole unconfirmed time (including that wait), charge the steps
        it reported with or without a newer checkpoint, adopt a newer intact checkpoint and
        recover a finished export, which then needs no new training budget."""
        if state.attempt == 0:
            state.charged_at = None
            return
        waited_from = self.monotonic()
        self._wait_for_own_trainer(context, job)
        waited = self.monotonic() - waited_from
        if state.charged_at is not None:
            elapsed = (self.wall_clock() - datetime.fromisoformat(state.charged_at)).total_seconds()
            state.budget = state.budget.charge(
                elapsed if elapsed < 0 else min(elapsed, UNCONFIRMED_LIMIT_SECONDS + waited)
            )
        state.charged_at = None
        progress = self._read_json(run_dir / "progress.json")
        if progress is not None and progress.get("attempt") == state.attempt:
            start = state.attempt_start
            if start is not None:
                done = int(start["reserved"]) + int(progress.get("step") or 0) - int(start["step"])
                if done > state.budget.reserved_steps:
                    state.budget = replace(
                        state.budget, reserved_steps=min(done, state.budget.max_steps)
                    )
            self._adopt_pointer(state, run_dir, progress.get("checkpoint"))
        result = self._read_json(run_dir / f"result-{state.attempt}.json")
        if (
            result is not None
            and not result.get("watchdog")
            and isinstance(result.get("steps"), int)
        ):
            self._settle_steps(state, int(result["steps"]))  # the orphan's own final count
        if state.export is None and (result is None or result.get("status") != "exported"):
            result = self._verified_export_without_result(job, run_dir) or result
        if state.export is None and result is not None and result.get("status") == "exported":
            self._verify_export(run_dir, result["export"])
            self._adopt_pointer(state, run_dir, result.get("checkpoint"))
            state.export = {
                **result["export"],
                "checkpoint": result["checkpoint"],
                "metric": result.get("metric"),
                "bestMetric": result.get("bestMetric"),
            }
            state.history.append(
                {"attempt": state.attempt, "status": "exported", "recovered": True}
            )
        self._persist(context, state, "recovered", 0, None)

    def _persist(
        self,
        context: JobExecutionContext,
        state: RunState,
        stage: str,
        step: int,
        total: int | None,
        *,
        acknowledge_cancellation: bool = True,
    ) -> None:
        # Job counters never decrease (domain rule): progress is the highest step reached
        # against the planned steps, kept across attempts and complete after export.
        planned = int(_payload(context.job)["planned_steps"])
        finished = stage in {"exported", "descriptor", "registered", "completed"}
        reached = planned if finished else step
        current = max(context.job.progress_current, min(max(reached, 0), planned))
        context.checkpoint(
            checkpoint_payload=state.payload(),
            stage=stage,
            current=current,
            total=planned,
            success_count=1 if state.registered else 0,
            failure_count=0,
            review_count=0,
            acknowledge_cancellation=acknowledge_cancellation,
        )

    # --- admission and training ----------------------------------------------------------------

    def probe(self) -> RuntimeFacts:
        if self._probe is not None:
            return self._probe()
        if self.python is None:
            return RuntimeFacts(cuda_available=False, probe_error="GRID_TRAINING_PYTHON_UNSET")
        try:
            completed = subprocess.run(
                [str(self.python), "-m", CHILD_MODULE, "--probe"],
                cwd=self.repository_root,
                env=self._environment(),
                capture_output=True,
                timeout=PROBE_TIMEOUT_SECONDS,
                check=False,
            )
            return RuntimeFacts(**json.loads(completed.stdout.decode("utf-8")))
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            return RuntimeFacts(cuda_available=False, probe_error="GRID_TRAINING_PROBE_FAILED")

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = self.pythonpath
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    def _wait_for_own_trainer(self, context: JobExecutionContext, job: Job) -> Any:
        """After a lost supervisor its trainer may still hold the GPU for up to the stale
        interval; wait for it instead of failing. Another holder blocks admission."""
        lease = GpuLease(lease_path(self.artifact_root))
        deadline = self.monotonic() + UNCONFIRMED_LIMIT_SECONDS + CANCEL_WAIT_SECONDS
        observation = lease.observe()
        while (
            observation.state == "held"
            and observation.record is not None
            and observation.record.run_id == str(job.id)
            and self.monotonic() < deadline
        ):
            context.heartbeat()
            self.sleep(self.poll_seconds)
            observation = lease.observe()
        return observation

    def _admit(
        self, context: JobExecutionContext, job: Job, state: RunState
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        payload, game = _payload(job), job.game_id
        assert game is not None
        cohort_id = UUID(str(payload["cohort_id"]))
        cohort = self.store.cohort(game, cohort_id)
        if (
            cohort["status"] != "frozen"
            or cohort["manifestSha256"] != payload["cohort_manifest_sha256"]
            or cohort["mode"] != payload["mode"]
            or str(cohort["baseVersionId"]) != str(payload["base_version_id"])
        ):
            raise JobHandlerError(
                "GRID_TRAINING_COHORT_DRIFT", "Frozen cohort differs from the run."
            )
        eligibility = self.store.eligibility(game, cohort_id)
        if eligibility["qualification"] != "eligible":
            reasons = list(eligibility.get("reasons") or [])
            raise JobHandlerError(
                reasons[0] if reasons else "GRID_RUN_COHORT_NOT_QUALIFIED",
                "The cohort no longer qualifies for new training use.",
            )
        base = self.store.base_version(UUID(str(payload["base_version_id"])))
        lease = GpuLease(lease_path(self.artifact_root)).observe()
        counts = counts_from_header(cohort)
        decision = evaluate_admission(
            preset_id=str(payload["preset_id"]),
            preset_fingerprint=str(payload["preset_fingerprint"]),
            purpose="train",
            runtime=self.probe(),
            lease_state=lease.state,
            counts=counts,
            stored_budget=state.budget,
        )
        if not decision.admitted or decision.budget is None:
            raise JobHandlerError(decision.reasons[0], "Run admission refused.")
        state.budget = decision.budget
        state.attempt += 1
        return cohort, base

    def _spec(
        self, job: Job, state: RunState, cohort: Mapping[str, Any], base: Mapping[str, Any]
    ) -> dict[str, Any]:
        payload = _payload(job)
        pid, created = own_identity()
        training = {item["name"]: item for item in base["trainingArtifacts"]}
        return {
            "format": SPEC_FORMAT,
            "jobId": str(job.id),
            "attempt": state.attempt,
            "artifactRoot": str(self.artifact_root),
            "cohort": {
                "gameId": str(job.game_id),
                "cohortId": str(payload["cohort_id"]),
                "manifestPath": cohort["manifestPath"],
                "manifestSha256": cohort["manifestSha256"],
            },
            "base": {
                "versionId": str(payload["base_version_id"]),
                "managedDirectory": base["managedDirectory"],
                "weightsSha256": training["weights.pt"]["sha256"],
                "presetSha256": training["preset.json"]["sha256"],
            },
            "preset": {"id": payload["preset_id"], "fingerprint": payload["preset_fingerprint"]},
            "seed": int(payload["seed"]),
            "plannedSteps": int(payload["planned_steps"]),
            "budget": {
                "remainingSeconds": state.budget.remaining_seconds,
                "remainingSteps": state.budget.remaining_steps,
            },
            "supervisor": {"pid": pid, "created": created},
            "resume": state.checkpoint,
        }

    def _verified_export_without_result(self, job: Job, run_dir: Path) -> dict[str, Any] | None:
        """A trainer that crashed after publishing its export directory but before writing its
        result still leaves a complete candidate; accept it only when every recorded hash,
        the checkpoint copy, the run identity and the passed parity agree."""
        candidates = []
        for directory in run_dir.glob("export-*"):
            try:
                bundle = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
                provenance = bundle["provenance"]
                expected = {
                    **dict(bundle["files"]),
                    "checkpoint.pt": provenance["checkpointSha256"],
                }
                if (
                    provenance.get("runId") != str(job.id)
                    or (directory / "preset.json").read_bytes() != RECIPE_FILE.read_bytes()
                    or bundle.get("preset_fingerprint") != RECIPE_FINGERPRINT
                    or provenance.get("presetFingerprint") != RECIPE_FINGERPRINT
                    or not bundle.get("parity", {}).get("passed")
                    or expected.get("weights.pt") != provenance["weightsSha256"]
                    or any(sha256_file(directory / name) != sha for name, sha in expected.items())
                ):
                    continue
                names = (
                    "screen.onnx",
                    "board.onnx",
                    "weights.pt",
                    "checkpoint.pt",
                    "preset.json",
                    "bundle.json",
                )
                files = {
                    name: {
                        "sha256": sha256_file(directory / name),
                        "sizeBytes": (directory / name).stat().st_size,
                    }
                    for name in names
                }
            except (OSError, ValueError, KeyError, TypeError):
                continue
            candidates.append((directory.stat().st_mtime, directory, bundle, provenance, files))
        if not candidates:
            return None
        _, directory, bundle, provenance, files = max(candidates, key=lambda item: item[0])
        checkpoint = {
            "path": f"{provenance['checkpointSha256']}.pt",
            "sha256": provenance["checkpointSha256"],
        }
        return {
            "status": "exported",
            "steps": None,
            "bestStep": provenance.get("bestStep"),
            "metric": None,
            "bestMetric": None,
            "checkpoint": checkpoint,
            "export": {"directory": directory.name, "provenance": dict(provenance), "files": files},
        }

    def _adopt_pointer(self, state: RunState, run_dir: Path, pointer: Any) -> None:
        """Adopt a newer intact checkpoint published by a trainer whose supervisor never
        persisted it. The trainer re-validates its binding on load."""
        if not isinstance(pointer, dict) or pointer == state.checkpoint:
            return
        current = -1 if state.checkpoint is None else int(state.checkpoint["step"])
        path = run_dir / "checkpoints" / str(pointer.get("path"))
        if (
            int(pointer.get("step", -1)) > current
            and path.parent == run_dir / "checkpoints"
            and path.is_file()
            and sha256_file(path) == pointer.get("sha256")
        ):
            state.checkpoint = {
                "path": str(pointer["path"]),
                "sha256": str(pointer["sha256"]),
                "step": int(pointer["step"]),
            }

    def _train(
        self, context: JobExecutionContext, job: Job, state: RunState, run_dir: Path
    ) -> None:
        if state.checkpoint is not None:
            path = run_dir / "checkpoints" / state.checkpoint["path"]
            if not path.is_file() or sha256_file(path) != state.checkpoint["sha256"]:
                raise JobHandlerError(
                    "GRID_TRAINING_CHECKPOINT_CORRUPT", "The pointed checkpoint is not intact."
                )
        cohort, base = self._admit(context, job, state)
        spec = self._spec(job, state, cohort, base)
        spec_path = run_dir / "spec.json"
        write_json_atomic(spec_path, {"payload": spec, "sha256": sha256_bytes(canonical(spec))})
        (run_dir / "cancel.intent").unlink(missing_ok=True)
        heartbeat = run_dir / "supervisor.heartbeat"
        heartbeat.write_text(self._now_iso(), encoding="utf-8")
        # Budget steps are cumulative over attempts: steps repeated after a resume from an
        # earlier checkpoint are charged again, never hidden behind the sampler position.
        start_step = int(state.checkpoint["step"]) if state.checkpoint else 0
        state.attempt_start = {"reserved": state.budget.reserved_steps, "step": start_step}
        allowance = self._reserve(state, start_step)
        state.charged_at = self._now_iso()  # a crash before the first progress write is charged
        self._persist(context, state, "admitted", 0, int(_payload(job)["planned_steps"]))
        self._write_allowance(run_dir, state.attempt, allowance)
        if self.python is None:
            raise JobHandlerError("GRID_TRAINING_PYTHON_UNSET", "No CUDA interpreter configured.")
        child = self.launcher(
            [str(self.python), "-m", CHILD_MODULE, "--spec", str(spec_path)],
            self._environment(),
            self.repository_root,
        )
        result = self._supervise(
            context,
            job,
            state,
            run_dir,
            child,
            heartbeat,
            state.attempt_start["reserved"],
            start_step,
        )
        state.history.append(
            {
                "attempt": state.attempt,
                **{
                    k: result.get(k)
                    for k in ("status", "code", "stopReason", "steps", "bestStep", "bestMetric")
                },
            }
        )
        if result["status"] == "exported":
            export = result["export"]
            self._verify_export(run_dir, export)
            state.export = {
                **export,
                "checkpoint": result["checkpoint"],
                "metric": result.get("metric"),
                "bestMetric": result.get("bestMetric"),
            }
            self._persist(
                context,
                state,
                "exported",
                int(result["steps"]),
                int(_payload(job)["planned_steps"]),
            )
            return
        code = str(result.get("code") or "GRID_TRAINING_FAILED")
        state.charged_at = None
        self._persist(context, state, "stopped", 0, None)
        raise JobHandlerError(code, "The trainer stopped without a candidate.")

    def _reserve(self, state: RunState, allowance: int) -> int:
        """Extend the step allowance by one bounded block and charge it before use."""
        extra = min(ALLOWANCE_STEPS, state.budget.remaining_steps)
        if extra > 0:
            state.budget = replace(state.budget, reserved_steps=state.budget.reserved_steps + extra)
        return allowance + extra

    @staticmethod
    def _write_allowance(run_dir: Path, attempt: int, step: int) -> None:
        write_json_atomic(run_dir / "allowance.json", {"attempt": attempt, "step": step})

    def _settle_steps(self, state: RunState, reported: int) -> None:
        """Replace the reserved block by the confirmed count once the trainer has ended."""
        start = state.attempt_start
        if start is None:
            return
        confirmed = int(start["reserved"]) + max(0, reported - int(start["step"]))
        state.budget = replace(
            state.budget,
            reserved_steps=max(min(confirmed, state.budget.max_steps), int(start["reserved"])),
        )

    def _stop_child(self, run_dir: Path, child: Any, reason: str) -> None:
        (run_dir / "cancel.intent").write_text(reason, encoding="utf-8")
        deadline = self.monotonic() + CANCEL_WAIT_SECONDS
        while child.poll() is None and self.monotonic() < deadline:
            self.sleep(min(self.poll_seconds, 1.0))
        if child.poll() is None:
            child.kill()
            child.wait(timeout=30)

    def _supervise(
        self,
        context: JobExecutionContext,
        job: Job,
        state: RunState,
        run_dir: Path,
        child: Any,
        heartbeat: Path,
        reserved_before: int,
        start_step: int,
    ) -> dict[str, Any]:
        result_path = run_dir / f"result-{state.attempt}.json"
        last = self.monotonic()
        cancel_written = False
        deadline = math.inf
        planned = int(_payload(job)["planned_steps"])
        allowance = (
            int(state.attempt_start["step"])
            + (state.budget.reserved_steps - int(state.attempt_start["reserved"]))
            if state.attempt_start
            else start_step
        )
        step = start_step
        while True:
            heartbeat.write_text(self._now_iso(), encoding="utf-8")
            now = self.monotonic()
            state.budget = state.budget.charge(now - last)
            last = now
            state.charged_at = self._now_iso()
            context.heartbeat()
            cancel_requested = context.job.cancel_requested_at is not None
            if (cancel_requested or state.budget.remaining_seconds <= 0) and not cancel_written:
                (run_dir / "cancel.intent").write_text(
                    "cancel" if cancel_requested else "budget", encoding="utf-8"
                )
                cancel_written = True
                deadline = self.monotonic() + CANCEL_WAIT_SECONDS
            exited = child.poll() is not None
            progress = self._read_json(run_dir / "progress.json")
            if progress and progress.get("attempt") == state.attempt:
                step = max(step, int(progress.get("step") or 0))
                self._adopt_pointer(state, run_dir, progress.get("checkpoint"))
            extend = (
                not cancel_written
                and not exited
                and step + ALLOWANCE_STEPS // 2 >= allowance
                and state.budget.remaining_steps > 0
            )
            if extend:
                allowance = self._reserve(state, allowance)
            if exited:
                break
            if cancel_written and self.monotonic() >= deadline:
                child.kill()
                child.wait(timeout=30)
                break
            if not cancel_requested:
                try:
                    self._persist(
                        context, state, "training", step, planned, acknowledge_cancellation=False
                    )
                except _ExecutionStopped:
                    # The store acknowledged a cancel that arrived after the heartbeat: stop
                    # the trainer at its next step and keep its final checkpoint on disk; a
                    # resume adopts it from the progress file.
                    self._stop_child(run_dir, child, "cancel")
                    raise
                if extend:
                    self._write_allowance(run_dir, state.attempt, allowance)
            self.sleep(self.poll_seconds)
        result = self._read_json(result_path)
        final = self._read_json(run_dir / "progress.json")
        if final and final.get("attempt") == state.attempt:
            step = max(step, int(final.get("step") or 0))
            self._adopt_pointer(state, run_dir, final.get("checkpoint"))
        if (
            result is not None
            and not result.get("watchdog")
            and isinstance(result.get("steps"), int)
        ):
            self._settle_steps(state, int(result["steps"]))
        # Otherwise (killed, crashed or ended by the watchdog) the reservation stays charged.
        if cancel_requested:
            state.charged_at = None
            self._persist(context, state, "cancelled", 0, None)  # acknowledges the cancel
        if result is None:
            return {"status": "failed", "code": "GRID_TRAINING_CHILD_EXITED"}
        return result

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    # --- install and register ------------------------------------------------------------------

    def _verify_export(self, run_dir: Path, export: Mapping[str, Any]) -> None:
        directory = run_dir / export["directory"]
        for name, item in export["files"].items():
            path = directory / name
            if (
                not path.is_file()
                or path.stat().st_size != item["sizeBytes"]
                or sha256_file(path) != item["sha256"]
            ):
                raise JobHandlerError("GRID_TRAINING_EXPORT_CORRUPT", "Exported files differ.")

    def _descriptor(
        self, job: Job, state: RunState, base: Mapping[str, Any]
    ) -> tuple[UUID, dict[str, Any]]:
        export = state.export
        assert export is not None
        files = export["files"]
        provenance = export["provenance"]
        checkpoint_sha = provenance["checkpointSha256"]
        version_id, version, key = deterministic_ids(job.id, checkpoint_sha)
        profile = base["inferenceManifest"]["profile"]
        bundle = json.loads(
            (
                run_directory(self.artifact_root, job.id) / export["directory"] / "bundle.json"
            ).read_text(encoding="utf-8")
        )

        def entry(name: str) -> dict[str, Any]:
            return {
                "name": name,
                "sha256": files[name]["sha256"],
                "sizeBytes": files[name]["sizeBytes"],
            }

        inference_files = [
            entry(name) for name in ("screen.onnx", "board.onnx", "bundle.json", "preset.json")
        ]
        reports: list[dict[str, str]] = []
        identity = {
            key_name: provenance[key_name]
            for key_name in (
                "runId",
                "exportId",
                "presetFingerprint",
                "weightsSha256",
                "checkpointSha256",
                "snapshotId",
            )
        }
        manifest = {
            "schemaVersion": "grid-engine-model-manifest-v1",
            "profile": profile,
            "version": version,
            "modelKind": "neural_grid",
            "modelVersion": base["modelVersion"],
            "bundleFormat": base["bundleFormat"],
            **identity,
            "preset": str(bundle["preset"].get("name", base["inferenceManifest"]["preset"])),
            "frozenOn": self.wall_clock().date().isoformat(),
            "selectionReason": (
                f"Application run {job.id}: best VALIDATION {export.get('metric')} "
                f"{export.get('bestMetric')} at step {provenance.get('bestStep')}; not evaluated."
            )[:1000],
            "report": "TASK-0996 application run; evaluation by TASK-0997",
            "reportResults": reports,
            "files": inference_files,
        }
        payload = {
            "schemaVersion": "grid-model-catalogue-v1",
            "familyId": base["familyId"],
            "familyCode": base["familyCode"],
            "familyLabel": base["familyLabel"],
            "versionId": str(version_id),
            "version": version,
            "modelKind": "neural_grid",
            "modelVersion": base["modelVersion"],
            "bundleFormat": base["bundleFormat"],
            "preprocessingVersion": base["preprocessingVersion"],
            "decodingPolicyVersion": base["decodingPolicyVersion"],
            "topology": base["topology"],
            "capabilities": base["capabilities"],
            "baseVersionId": str(_payload(job)["base_version_id"]),
            "cohortId": str(_payload(job)["cohort_id"]),
            "admission": "not_evaluated",
            "provenance": identity,
            "historicalReports": reports,
            "managedDirectory": f"models/grid-engine/{profile}/{version}",
            "inferenceManifest": manifest,
            "files": inference_files,
            "trainingArtifacts": [
                entry("checkpoint.pt"),
                entry("weights.pt"),
                entry("bundle.json"),
                entry("preset.json"),
            ],
        }
        return key, payload

    def _install(
        self, run_dir: Path, export: Mapping[str, Any], payload: Mapping[str, Any]
    ) -> None:
        from game_predictor_api.storage.grid_engine_model_store import receipt_bytes
        from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector

        target = self.artifact_root / payload["managedDirectory"]
        if target.exists():
            available, reason = GridModelArtifactInspector(self.artifact_root).inspect(
                dict(payload)
            )
            if available:
                return
            raise JobHandlerError("GRID_TRAINING_INSTALL_CONFLICT", reason)
        source = run_dir / export["directory"]
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".{target.name}.installing-{uuid.uuid4().hex}"
        try:
            (staging / "training-base").mkdir(parents=True)
            for name in ("screen.onnx", "board.onnx", "bundle.json", "preset.json"):
                shutil.copyfile(source / name, staging / name)
            (staging / "manifest.json").write_text(
                json.dumps(payload["inferenceManifest"], indent=2, sort_keys=True), encoding="utf-8"
            )
            training = staging / "training-base"
            names = ("checkpoint.pt", "weights.pt", "bundle.json", "preset.json")
            for name in names:
                shutil.copyfile(source / name, training / name)
            identity = {
                "schemaVersion": "grid-engine-training-base-v1",
                "model": payload["inferenceManifest"],
                "files": payload["trainingArtifacts"],
                "sources": {name: str((source / name).resolve()) for name in names},
            }
            (training / "receipt.json").write_bytes(receipt_bytes(identity))
            for path in [*staging.iterdir(), *training.iterdir()]:
                if path.is_file():
                    with path.open("r+b") as stream:  # Windows fsync needs a writable handle
                        os.fsync(stream.fileno())
            os.replace(staging, target)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        available, reason = GridModelArtifactInspector(self.artifact_root).inspect(dict(payload))
        if not available:
            raise JobHandlerError("GRID_TRAINING_INSTALL_INVALID", reason)

    def _install_and_register(
        self, context: JobExecutionContext, job: Job, state: RunState, run_dir: Path
    ) -> None:
        assert state.export is not None
        self._verify_export(run_dir, state.export)
        base = self.store.base_version(UUID(str(_payload(job)["base_version_id"])))
        stored = state.export.get("descriptor")
        if stored is None:
            # Persist the exact descriptor before any file is installed, so a retry on
            # another day reproduces the same manifest instead of a conflicting one.
            key, payload = self._descriptor(job, state, base)
            state.export["descriptor"] = {"key": str(key), "payload": payload}
            self._persist(context, state, "descriptor", 1, 1)
        else:
            key, payload = UUID(stored["key"]), dict(stored["payload"])
        self._install(run_dir, state.export, payload)
        view = self.store.register(key, payload)
        state.registered = {
            "versionId": payload["versionId"],
            "version": payload["version"],
            "manifestSha256": view.get("manifestSha256"),
            "idempotencyKey": str(key),
        }
        self._persist(context, state, "registered", 1, 1)

    def _finish(self, context: JobExecutionContext, state: RunState) -> None:
        state.charged_at = None
        self._persist(context, state, "completed", 1, 1)
