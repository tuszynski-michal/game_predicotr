"""Single-worker durable runs, process identity, fencing and non-refundable budgets."""

import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import digest, exclusive, read_checked, write_atomic
from .process_identity import own_identity, process_created
from .run_contracts import Artifact, RunMutation, RunPage, RunState, StartRunRequest
from .run_files import publish, verify_artifact
from .snapshot import canonical, safe_file

ACTIVE = {"queued", "running"}
LEASE_SECONDS = 60
LAUNCH_SECONDS = 60
Token = tuple[int, int, str]


@contextmanager
def run_lock(root: Path) -> Iterator[None]:
    """Run-local bounded contention retry; annotation mutation semantics are unchanged."""
    deadline = time.monotonic() + 10
    while True:
        lock = exclusive(root)
        try:
            lock.__enter__()
            break
        except ValueError as error:
            if str(error) != "ANNOTATION_STORE_BUSY" or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def token(run: RunState) -> Token:
    return run.attempt, run.fence, run.lease


def canonical_request(request: StartRunRequest, *, exclude_id: bool = False) -> dict[str, Any]:
    value = request.model_dump(exclude={"request_id"} if exclude_id else set())
    if value.get("protocol_digest") is None:
        value.pop("protocol_digest", None)
    return value


def checkpoint_binding(request: StartRunRequest) -> dict[str, Any]:
    value = canonical_request(request, exclude_id=True)
    fingerprint = digest(value)
    if request.protocol_digest is not None:
        from .hybrid_protocol import protocol

        value["protocol"] = protocol()
    return {"inputFingerprint": fingerprint, "dataSha256": request.manifest_id, **value}


class RunManager:
    def __init__(
        self,
        root: Path,
        *,
        validate: Callable[[StartRunRequest], object],
        models: tuple[str, ...] = (),
        settings: dict[str, str] | None = None,
        launcher: Callable[[RunState], None] | None = None,
        clock: Callable[[], float] = time.time,
        identity: Callable[[int], str | None] = process_created,
        state_type: type[RunState] = RunState,
        admit: Callable[[dict[str, Any], StartRunRequest], None] | None = None,
    ) -> None:
        self.root = root
        self.validate = validate
        self.models = models
        self.settings = settings
        self.launcher = launcher or self._spawn
        self.clock = clock
        self.identity = identity
        # A model family may bind a stricter request contract (state_type) and a durable
        # admission rule evaluated under the run lock against all recorded runs (admit).
        self.state_type = state_type
        self.admit = admit

    def _load(self) -> dict[str, Any]:
        path = safe_file(self.root, "state.json")
        if not path.exists():
            return {"version": 1, "runs": {}, "receipts": {}, "next_fence": 1}
        payload = read_checked(path)
        if payload.get("version") != 1:
            raise ValueError("RUN_STORE_VERSION_UNSUPPORTED")
        return payload

    def _save(self, data: dict[str, Any], run: RunState | None = None) -> None:
        if run is not None:
            data["runs"][run.id] = run.model_dump()
        write_atomic(safe_file(self.root, "state.json"), data)

    def _get(self, data: dict[str, Any], run_id: str) -> RunState:
        if run_id not in data["runs"]:
            raise KeyError("RUN_NOT_FOUND")
        return self.state_type.model_validate(data["runs"][run_id])

    def _account(self, run: RunState, *, conservative: bool = False) -> None:
        now = self.clock()
        if run.last_accounted_at is None:
            return
        remaining = max(0.0, run.request.configuration.max_seconds - run.used_seconds)
        elapsed = now - run.last_accounted_at
        if elapsed < 0 or not (float("-inf") < elapsed < float("inf")):
            elapsed = remaining
            conservative = True
            run.diagnostics = sorted(set([*run.diagnostics, "RUN_CLOCK_UNRELIABLE"]))
        charge = min(remaining, elapsed)
        run.used_seconds += charge
        if conservative:
            run.conservative_seconds += charge
        run.last_accounted_at = now

    def _alive(self, run: RunState) -> bool:
        return (
            run.pid is not None
            and run.process_created is not None
            and self.identity(run.pid) == run.process_created
        )

    def _reconcile(self, data: dict[str, Any]) -> None:
        now = self.clock()
        for run_id in data["runs"]:
            run = self._get(data, run_id)
            if run.status == "queued" and now >= run.launch_deadline:
                run.status, run.error = "failed", "RUN_LAUNCH_EXPIRED"
            elif run.status == "running":
                try:
                    alive = self._alive(run)
                except ValueError:
                    run.diagnostics = ["RUN_PROCESS_IDENTITY_UNAVAILABLE"]
                    data["runs"][run.id] = run.model_dump()
                    continue
                stale = now - (run.heartbeat_at or run.created_at) >= LEASE_SECONDS
                if alive:
                    run.diagnostics = ["RUN_UNRESPONSIVE"] if stale else []
                elif stale or now < (run.heartbeat_at or run.created_at):
                    self._account(run, conservative=True)
                    run.status, run.error = "failed", "RUN_LEASE_EXPIRED"
            data["runs"][run.id] = run.model_dump()

    @staticmethod
    def _receipt(data: dict[str, Any], request_id: str, fingerprint: str) -> str | None:
        receipt = data["receipts"].get(request_id)
        if receipt is None:
            return None
        if receipt["fingerprint"] != fingerprint:
            raise ValueError("REQUEST_ID_CONFLICT")
        return str(receipt["run_id"])

    @staticmethod
    def _record(data: dict[str, Any], request_id: str, fingerprint: str, run: RunState) -> None:
        data["receipts"][request_id] = {
            "fingerprint": fingerprint,
            "run_id": run.id,
            "attempt": run.attempt,
        }

    def create_or_get_run(self, request: StartRunRequest) -> RunState:
        fingerprint = digest(["start", canonical_request(request)])
        with run_lock(self.root):
            data = self._load()
            replay = self._receipt(data, request.request_id, fingerprint)
            if replay:
                return self._get(data, replay)
            self._reconcile(data)
            # Persist recovery even when a later validation fails.
            self._save(data)
            if any(item["status"] in ACTIVE for item in data["runs"].values()):
                raise ValueError("RUN_BUSY")
            if request.model_version not in self.models:
                raise ValueError("RUN_MODEL_NOT_AVAILABLE")
            if self.admit is not None:
                self.admit(data, request)
            self.validate(request)
            if self.settings is not None:
                write_atomic(safe_file(self.root, "settings.json"), self.settings)
            now = self.clock()
            run = self.state_type(
                id=uuid.uuid4().hex,
                request=request,
                fingerprint=digest(canonical_request(request, exclude_id=True)),
                lease=uuid.uuid4().hex,
                fence=data["next_fence"],
                created_at=now,
                launch_deadline=now + LAUNCH_SECONDS,
            )
            data["next_fence"] += 1
            self._record(data, request.request_id, fingerprint, run)
            self._save(data, run)
        self._launch(run)
        return self.detail(run.id)

    def _launch(self, run: RunState) -> None:
        try:
            with run_lock(self.root):
                current = self._get(self._load(), run.id)
                if current.status == "queued" and token(current) == token(run):
                    self.launcher(run)
        except (OSError, ValueError) as error:
            with run_lock(self.root):
                data = self._load()
                current = self._get(data, run.id)
                if token(current) == token(run) and current.status == "queued":
                    current.status, current.error = "failed", "RUN_SPAWN_FAILED"
                    self._save(data, current)
            raise RuntimeError("RUN_SPAWN_FAILED") from error

    def _spawn(self, run: RunState) -> None:
        if self.settings is None:
            raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
        executable = Path(self.settings["python"])
        if not executable.is_file():
            raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
        log_path = safe_file(self.root, f"{run.id}/attempt-{run.attempt}/worker.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            subprocess.Popen(
                [
                    str(executable),
                    "-m",
                    "game_predictor_worker.vision_lab.run_worker",
                    "--root",
                    str(self.root.resolve()),
                    "--run",
                    run.id,
                    "--attempt",
                    str(run.attempt),
                    "--fence",
                    str(run.fence),
                    "--lease",
                    run.lease,
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env={**os.environ, "PYTHONUTF8": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

    def list(self, offset: int = 0, limit: int = 24) -> RunPage:
        with run_lock(self.root):
            data = self._load()
            self._reconcile(data)
            self._save(data)
            runs = [self.state_type.model_validate(value) for value in data["runs"].values()]
            runs.sort(key=lambda item: (item.created_at, item.id), reverse=True)
            for run in runs[offset : offset + limit]:
                self._verify_outputs(run)
            return RunPage(runs=runs[offset : offset + limit], total=len(runs))

    def _verify_outputs(self, run: RunState) -> None:
        for artifact in run.artifacts.values():
            verify_artifact(self.root, artifact)
        if run.status != "succeeded":
            return
        if run.report is None or run.checkpoint is None:
            raise ValueError("RUN_SUCCESS_ARTIFACT_MISSING")
        report = json.loads(verify_artifact(self.root, run.report).read_bytes())
        verify_artifact(self.root, run.checkpoint)
        if run.artifacts and report.get("artifacts") != {
            name: value.model_dump() for name, value in run.artifacts.items()
        }:
            raise ValueError("RUN_ARTIFACT_BINDING_MISMATCH")

    def detail(self, run_id: str) -> RunState:
        with run_lock(self.root):
            data = self._load()
            self._reconcile(data)
            run = self._get(data, run_id)
            self._save(data)
            self._verify_outputs(run)
            return run

    def cancel_run(self, run_id: str, request: RunMutation) -> RunState:
        return self._mutate(run_id, request, retry=False)

    def retry_run(self, run_id: str, request: RunMutation) -> RunState:
        return self._mutate(run_id, request, retry=True)

    def _mutate(self, run_id: str, request: RunMutation, *, retry: bool) -> RunState:
        fingerprint = digest(["retry" if retry else "cancel", run_id, request.model_dump()])
        with run_lock(self.root):
            data = self._load()
            replay = self._receipt(data, request.request_id, fingerprint)
            if replay:
                return self._get(data, replay)
            self._reconcile(data)
            self._save(data)
            run = self._get(data, run_id)
            if run.attempt != request.expected_attempt:
                raise ValueError("RUN_ATTEMPT_CONFLICT")
            if retry:
                if run.status not in {"failed", "cancelled"}:
                    raise ValueError("RUN_NOT_RETRYABLE")
                if self._alive(run):
                    raise ValueError("RUN_PROCESS_ALIVE")
                if any(item["status"] in ACTIVE for item in data["runs"].values()):
                    raise ValueError("RUN_BUSY")
                self._check_budget(run)
                self.validate(run.request)
                if run.checkpoint:
                    verify_artifact(self.root, run.checkpoint)
                run.attempts.append(
                    {
                        "attempt": run.attempt,
                        "status": run.status,
                        "error": run.error,
                        "pid": run.pid,
                        "process_created": run.process_created,
                        "reserved_steps": run.reserved_steps,
                        "used_seconds": run.used_seconds,
                    }
                )
                run.attempt += 1
                run.fence = data["next_fence"]
                data["next_fence"] += 1
                run.lease = uuid.uuid4().hex
                run.status = "queued"
                run.cancel_requested = False
                run.pid = None
                run.process_created = None
                run.heartbeat_at = None
                run.started_at = None
                run.last_accounted_at = None
                run.attempt_deadline = None
                run.launch_deadline = self.clock() + LAUNCH_SECONDS
                run.error = None
                run.artifacts = {}
                run.report = None
                run.best_epoch = None
                run.diagnostics = []
            elif run.status in ACTIVE:
                run.cancel_requested = True
                if run.status == "queued":
                    run.status = "cancelled"
            self._record(data, request.request_id, fingerprint, run)
            self._save(data, run)
        if retry:
            self._launch(run)
        return self.detail(run.id)

    def _fenced(self, data: dict[str, Any], run_id: str, lease: Token) -> RunState:
        run = self._get(data, run_id)
        if token(run) != lease or run.status not in ACTIVE:
            raise ValueError("RUN_WRITER_FENCED")
        return run

    @staticmethod
    def _check_budget(run: RunState) -> None:
        if (
            run.reserved_steps >= run.request.configuration.max_steps
            or run.used_seconds >= run.request.configuration.max_seconds
        ):
            raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")

    def claim(self, run_id: str, lease: Token) -> RunState:
        with run_lock(self.root):
            data = self._load()
            run = self._fenced(data, run_id, lease)
            if run.status != "queued" or self.clock() >= run.launch_deadline:
                raise ValueError("RUN_CLAIM_REJECTED")
            self.validate(run.request)
            self._check_budget(run)
            run.pid, run.process_created = own_identity()
            now = self.clock()
            run.started_at = run.heartbeat_at = run.last_accounted_at = now
            run.attempt_deadline = now + run.request.configuration.max_seconds - run.used_seconds
            run.status = "running"
            self._save(data, run)
            return run

    def heartbeat(self, run_id: str, lease: Token, *, reserve_step: bool = False) -> RunState:
        with run_lock(self.root):
            data = self._load()
            run = self._fenced(data, run_id, lease)
            if run.status != "running":
                raise ValueError("RUN_NOT_RUNNING")
            self._account(run)
            run.heartbeat_at = self.clock()
            self._save(data, run)
            if reserve_step:
                self._check_budget(run)
                run.reserved_steps += 1
                self._save(data, run)
            elif run.used_seconds >= run.request.configuration.max_seconds:
                raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            return run

    def checkpoint(self, run_id: str, lease: Token, content: bytes, epoch: int) -> None:
        with run_lock(self.root):
            data = self._load()
            run = self._fenced(data, run_id, lease)
            if run.status != "running" or epoch < run.checkpoint_epoch:
                raise ValueError("RUN_CHECKPOINT_EPOCH_INVALID")
            self.validate(run.request)
            self._account(run)
            artifact = publish(self.root, run.id, run.attempt, content, "pt")
            # Validate bytes and binding before replacing the last known-good pointer.
            from game_predictor_worker.training_core.checkpoint import load_checkpoint

            value = load_checkpoint(
                verify_artifact(self.root, artifact),
                artifact.sha256,
                expected_binding=checkpoint_binding(run.request),
            )
            if value["schemaVersion"] != 2 or value["epoch"] != epoch:
                raise ValueError("RUN_CHECKPOINT_EPOCH_INVALID")
            run.checkpoint, run.checkpoint_epoch = artifact, epoch
            run.heartbeat_at = self.clock()
            self._save(data, run)

    def finish(
        self,
        run_id: str,
        lease: Token,
        *,
        status: str,
        error: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> RunState:
        with run_lock(self.root):
            data = self._load()
            run = self._fenced(data, run_id, lease)
            self._account(run)
            if status == "succeeded":
                self.validate(run.request)
                if run.used_seconds >= run.request.configuration.max_seconds:
                    status, error = "cancelled", "RUN_BUDGET_EXHAUSTED"
                elif run.cancel_requested:
                    status, error = "cancelled", "RUN_CANCELLED"
                elif run.checkpoint is None:
                    raise ValueError("RUN_SUCCESS_ARTIFACT_MISSING")
                else:
                    verify_artifact(self.root, run.checkpoint)
                    if run.request.protocol_digest is not None and set(run.artifacts) != {
                        "onnx",
                        "best_weights",
                    }:
                        raise ValueError("RUN_SUCCESS_ARTIFACT_MISSING")
                    for artifact in run.artifacts.values():
                        verify_artifact(self.root, artifact)
                    if run.checkpoint_epoch != run.request.configuration.epochs:
                        raise ValueError("RUN_EPOCHS_INCOMPLETE")
            if status not in {"succeeded", "failed", "cancelled"}:
                raise ValueError("RUN_TERMINAL_STATUS_INVALID")
            run.status = status  # type: ignore[assignment]
            run.error = error
            if status == "succeeded" and run.request.protocol_digest is not None:
                best_epoch = (metrics or {}).get("best_epoch")
                if type(best_epoch) is not int or not 1 <= best_epoch <= run.checkpoint_epoch:
                    raise ValueError("HYBRID_BEST_STATE_MISSING")
                run.best_epoch = best_epoch
            report = {
                "run_id": run.id,
                "attempt": run.attempt,
                "fingerprint": run.fingerprint,
                "status": status,
                "error": error,
                "checkpoint": (run.checkpoint.model_dump() if run.checkpoint else None),
                "completed_epoch": run.checkpoint_epoch,
                "reserved_steps": run.reserved_steps,
                "used_seconds": run.used_seconds,
                "conservative_seconds": run.conservative_seconds,
                "metrics": metrics or {},
                "artifacts": {name: value.model_dump() for name, value in run.artifacts.items()},
                "binding": checkpoint_binding(run.request),
            }
            run.report = publish(self.root, run.id, run.attempt, canonical(report), "json")
            if status == "succeeded":
                self._account(run)
                if run.used_seconds >= run.request.configuration.max_seconds:
                    raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            self._save(data, run)
            return run

    def publish_artifact(self, run_id: str, lease: Token, name: str, content: bytes) -> Artifact:
        extensions = {"onnx": "onnx", "best_weights": "pt"}
        if name not in extensions:
            raise ValueError("RUN_ARTIFACT_NAME_INVALID")
        with run_lock(self.root):
            data = self._load()
            run = self._fenced(data, run_id, lease)
            if run.status != "running":
                raise ValueError("RUN_NOT_RUNNING")
            self.validate(run.request)
            self._account(run)
            if run.used_seconds >= run.request.configuration.max_seconds:
                self._save(data, run)
                raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            artifact = publish(self.root, run.id, run.attempt, content, extensions[name])
            verify_artifact(self.root, artifact)
            self._account(run)
            if run.used_seconds >= run.request.configuration.max_seconds:
                self._save(data, run)
                raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            run.artifacts[name] = artifact
            self._save(data, run)
            return artifact
