"""GPU trainer process of one application grid-training run (TASK-0996, D-558).

Started by the ``grid_training`` lane supervisor with the configured CUDA interpreter. It
reads only the pinned run specification and files: the frozen cohort snapshot, the base
version's ``training-base`` and the run directory. It never opens the database. It holds
the application GPU lease (D-557) and stops itself when the supervisor disappears, a
cancel intent appears or its time limit passes. Every outcome ends with ``result.json``.

    python -m game_predictor_worker.images.grid_training_child --probe
    python -m game_predictor_worker.images.grid_training_child --spec <run>/spec.json
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from ..training_core.gpu_lease import GpuLease, GpuLeaseError, lease_path
from ..training_core.grid_training_admission import PRESETS, probe_runtime
from ..training_core.process_identity import process_created
from ..training_core.runtime import TrainingInterrupted

SPEC_FORMAT = "grid-training-spec-v1"
PROGRESS_FORMAT = "grid-training-progress-v1"
RESULT_FORMAT = "grid-training-result-v1"
SUPERVISOR_STALE_SECONDS = 60.0
PROGRESS_SECONDS = 2.0
LEASE_RENEW_SECONDS = 20.0
EXPORT_PREFIX = "export-"
WATCHDOG_POLL_SECONDS = 1.0
# The trainer runs only steps the supervisor has reserved in the job payload.
ALLOWANCE_WAIT_SECONDS = 60.0
ALLOWANCE_POLL_SECONDS = 0.5
WATCHDOG_GRACE_SECONDS = 5.0
# The training loop notices a lost supervisor at the next step and publishes a step
# checkpoint; the watchdog only ends the process if that has not happened in time.
WATCHDOG_LOST_GRACE_SECONDS = 30.0
# Approved recipe (D-558): board/screen/augmentation of the frozen lab preset D.
RECIPE_FILE = Path(__file__).resolve().parents[1] / "vision_lab" / "neural_grid_presets" / "D.json"
RECIPE_FINGERPRINT = "b94a9627df4c2d0886b43776f1a80b406de5d124c36c997ada2b5f93c5d1cbd9"
RECIPE_COMPATIBLE_KEYS = (
    "backbone",
    "board",
    "screen",
    "fit",
    "preprocessing_version",
    "model_version",
)


class ChildError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(dict(value), indent=2, sort_keys=True).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_spec(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    body = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(body, dict) or envelope.get("sha256") != sha256_bytes(canonical(body)):
        raise ChildError("GRID_TRAINING_SPEC_CORRUPT")
    if body.get("format") != SPEC_FORMAT:
        raise ChildError("GRID_TRAINING_SPEC_CORRUPT")
    return body


class ChildControl:
    """Cancel intent, supervisor liveness, the spec time limit and progress reports."""

    def __init__(
        self,
        spec: Mapping[str, Any],
        run_dir: Path,
        lease: GpuLease,
        record: Any,
        counter: dict[str, int] | None = None,
    ) -> None:
        self.counter = counter if counter is not None else {"step": 0}
        self.spec, self.run_dir = spec, run_dir
        self.lease, self.record = lease, record
        self.started = time.monotonic()
        self.limit = float(spec["budget"]["remainingSeconds"])
        self.remaining_steps = int(spec["budget"]["remainingSteps"])
        resume = spec.get("resume")
        self.start_step = int(resume["step"]) if resume else 0
        self.allowance = self.start_step
        self.last_progress = 0.0
        self.last_renew = time.monotonic()
        self.checkpoint: dict[str, Any] | None = None

    def _supervisor_alive(self) -> bool:
        return supervisor_alive(self.spec, self.run_dir)

    def before_step(self, step: int) -> None:
        self.counter["step"] = step  # steps completed before this one
        if (self.run_dir / "cancel.intent").exists():
            raise TrainingInterrupted("RUN_CANCELLED")
        if (
            time.monotonic() - self.started >= self.limit
            or step - self.start_step >= self.remaining_steps
        ):
            raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
        if not self._supervisor_alive():
            raise TrainingInterrupted("RUN_SUPERVISOR_LOST")
        if step >= self.allowance:
            self._wait_for_allowance(step)
        if time.monotonic() - self.last_renew >= LEASE_RENEW_SECONDS:
            try:
                self.record = self.lease.renew(self.record)
            except GpuLeaseError as error:
                raise TrainingInterrupted(error.code) from error
            self.last_renew = time.monotonic()

    def _read_allowance(self) -> int:
        try:
            value = json.loads((self.run_dir / "allowance.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.allowance
        if not isinstance(value, dict) or value.get("attempt") != self.spec["attempt"]:
            return self.allowance
        return max(self.allowance, int(value.get("step", 0)))

    def _wait_for_allowance(self, step: int) -> None:
        deadline = time.monotonic() + ALLOWANCE_WAIT_SECONDS
        while True:
            self.allowance = self._read_allowance()
            if step < self.allowance:
                return
            if (self.run_dir / "cancel.intent").exists():
                raise TrainingInterrupted("RUN_CANCELLED")
            if not self._supervisor_alive():
                raise TrainingInterrupted("RUN_SUPERVISOR_LOST")
            if time.monotonic() >= deadline:
                raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
            time.sleep(ALLOWANCE_POLL_SECONDS)

    def checkpoint_published(self, path: Path, sha256: str, step: int) -> None:
        self.counter["step"] = max(self.counter["step"], step)
        self.checkpoint = {"path": path.name, "sha256": sha256, "step": step}
        self.write_progress(step, None, {}, force=True)

    def progress(self, step: int, total: int, losses: Mapping[str, float]) -> None:
        self.counter["step"] = max(self.counter["step"], step)  # ``step`` steps are completed
        self.write_progress(step, total, losses)

    def write_progress(
        self, step: int, total: int | None, losses: Mapping[str, float], *, force: bool = False
    ) -> None:
        now = time.monotonic()
        if not force and now - self.last_progress < PROGRESS_SECONDS:
            return
        self.last_progress = now
        write_json_atomic(
            self.run_dir / "progress.json",
            {
                "format": PROGRESS_FORMAT,
                "attempt": self.spec["attempt"],
                "step": step,
                "totalSteps": total,
                "losses": dict(losses),
                "checkpoint": self.checkpoint,
                "elapsedSeconds": now - self.started,
            },
        )


def _base(spec: Mapping[str, Any], artifact_root: Path) -> tuple[Path, dict[str, Any], bytes]:
    directory = artifact_root / spec["base"]["managedDirectory"] / "training-base"
    preset_bytes = (directory / "preset.json").read_bytes()
    if sha256_bytes(preset_bytes) != spec["base"]["presetSha256"]:
        raise ChildError("GRID_TRAINING_BASE_DRIFT")
    weights = directory / "weights.pt"
    if sha256_file(weights) != spec["base"]["weightsSha256"]:
        raise ChildError("GRID_TRAINING_BASE_DRIFT")
    return weights, json.loads(preset_bytes), preset_bytes


def supervisor_alive(spec: Mapping[str, Any], run_dir: Path) -> bool:
    supervisor = spec["supervisor"]
    try:
        if process_created(int(supervisor["pid"])) != supervisor["created"]:
            return False
        beat = (run_dir / "supervisor.heartbeat").stat().st_mtime
    except (OSError, ValueError):
        return False
    return time.time() - beat <= SUPERVISOR_STALE_SECONDS


class Watchdog:
    """Ends the whole process (data preparation, a blocked batch, validation or export
    included) once the supervisor is gone or the spec time limit plus a short grace has
    passed, so the supervisor's bounded charge of an unconfirmed interval stays true."""

    def __init__(
        self,
        spec: Mapping[str, Any],
        run_dir: Path,
        result_path: Path,
        *,
        alive: Any = supervisor_alive,
        exit_process: Any = os._exit,
        clock: Any = time.monotonic,
    ) -> None:
        self.spec, self.run_dir, self.result_path = spec, run_dir, result_path
        self.alive, self.exit_process, self.clock = alive, exit_process, clock
        self.started = clock()
        self.limit = float(spec["budget"]["remainingSeconds"]) + WATCHDOG_GRACE_SECONDS
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._lost_since: float | None = None

    def expired(self) -> str | None:
        now = self.clock()
        if now - self.started > self.limit:
            return "RUN_BUDGET_EXHAUSTED"
        if self.alive(self.spec, self.run_dir):
            self._lost_since = None
            return None
        if self._lost_since is None:
            self._lost_since = now
        if now - self._lost_since > WATCHDOG_LOST_GRACE_SECONDS:
            return "RUN_SUPERVISOR_LOST"
        return None

    def check(self) -> bool:
        code = self.expired()
        if code is None:
            return False
        with self._lock:
            if self._stopped.is_set():
                return False
            with contextlib.suppress(Exception):
                write_json_atomic(
                    self.result_path,
                    {
                        "format": RESULT_FORMAT,
                        "attempt": self.spec["attempt"],
                        "status": "interrupted",
                        "code": code,
                        "watchdog": True,
                    },
                )
            self.exit_process(4)
        return True

    def _run(self) -> None:
        while not self._stopped.wait(WATCHDOG_POLL_SECONDS):
            if self.check():
                return

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stopped.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=WATCHDOG_POLL_SECONDS + 5.0)


def run(spec_path: Path) -> int:
    spec = read_spec(spec_path)
    run_dir = spec_path.parent
    artifact_root = Path(spec["artifactRoot"])
    result_path = run_dir / f"result-{spec['attempt']}.json"
    lease = GpuLease(lease_path(artifact_root))
    record = None
    watchdog = Watchdog(spec, run_dir, result_path)
    watchdog.start()
    resume = spec.get("resume")
    counter = {"step": int(resume["step"]) if resume else 0}  # last step reached, for results
    try:
        record = lease.acquire("train", spec["jobId"])
        outcome = _train(spec, run_dir, artifact_root, lease, record, counter)
    except TrainingInterrupted as interrupted:
        outcome = {"status": "interrupted", "code": str(interrupted)}
    except (ChildError, GpuLeaseError) as error:
        outcome = {"status": "failed", "code": error.code}
    except ValueError as error:
        code = str(error).split(":", 1)[0]
        outcome = {"status": "failed", "code": code if code.isupper() else "GRID_TRAINING_FAILED"}
    finally:
        watchdog.stop()
    # The result is durable before the GPU lease is released: a supervisor that sees the
    # lease free can rely on the result file (a crash in between leaves the lease stale).
    outcome.setdefault("steps", counter["step"])
    write_json_atomic(result_path, {"format": RESULT_FORMAT, "attempt": spec["attempt"], **outcome})
    if record is not None:
        with contextlib.suppress(GpuLeaseError):
            lease.release(record)
    return 0 if outcome["status"] == "exported" else 3


def _train(
    spec: Mapping[str, Any],
    run_dir: Path,
    artifact_root: Path,
    lease: GpuLease,
    record: Any,
    counter: dict[str, int],
) -> dict[str, Any]:
    import torch

    from ..training_core.grid_training import (
        TrainingPlan,
        best_weights,
        board_only_losses,
        namespace,
        preset_payload_fingerprint,
        screen_grid_losses,
        train,
    )
    from ..training_core.neural_grid_network import NeuralGridNetwork
    from .grid_cohort_dataset import GridCohortSnapshot
    from .grid_training_data import (
        CohortPhotos,
        GridOnlyBatches,
        ScreenGridBatches,
        board_evaluator,
        photo_evaluator,
        validation_crops,
    )

    preset = PRESETS.get(spec["preset"]["id"])
    if preset is None or preset.fingerprint != spec["preset"]["fingerprint"]:
        raise ChildError("GRID_RUN_PRESET_NOT_APPROVED")
    weights_path, base_payload, _ = _base(spec, artifact_root)
    preset_bytes = RECIPE_FILE.read_bytes()
    preset_payload = json.loads(preset_bytes)
    if preset_payload_fingerprint(preset_payload) != RECIPE_FINGERPRINT:
        raise ChildError("GRID_TRAINING_RECIPE_CHANGED")
    if any(base_payload.get(key) != preset_payload.get(key) for key in RECIPE_COMPATIBLE_KEYS):
        raise ChildError("GRID_TRAINING_RECIPE_INCOMPATIBLE")
    recipe = namespace(preset_payload)
    cohort = spec["cohort"]
    snapshot = GridCohortSnapshot(artifact_root, cohort["manifestPath"], cohort["manifestSha256"])
    if snapshot.manifest.get("mode") != preset.mode:
        raise ChildError("GRID_RUN_COHORT_MODE_MISMATCH")
    device = "cuda" if torch.cuda.is_available() else spec.get("device", "cpu")
    if spec.get("requireCuda", True) and device != "cuda":
        raise ChildError("GRID_RUN_GPU_UNAVAILABLE")
    torch.manual_seed(int(spec["seed"]))
    network = NeuralGridNetwork(recipe.board.stride)
    network.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
    workers = int(spec.get("dataWorkers", preset.data_workers))
    screen_mode = preset.mode == "screen+grid"
    train_photos = CohortPhotos(snapshot, "TRAIN", full_only=screen_mode)
    validation = CohortPhotos(snapshot, "VALIDATION", full_only=True)
    crops, labels = validation_crops(validation, recipe)
    if screen_mode:
        batches: Any = ScreenGridBatches(
            train_photos, recipe, preset.batch_items, int(spec["seed"]), workers
        )
        evaluate = photo_evaluator(validation, recipe, device)
        losses = screen_grid_losses
    else:
        batches = GridOnlyBatches(
            train_photos, recipe, preset.batch_items, int(spec["seed"]), workers
        )
        evaluate = board_evaluator(crops, labels, device)
        losses = board_only_losses
    plan = TrainingPlan.of(
        spec["jobId"],
        int(spec["seed"]),
        preset,
        int(spec["plannedSteps"]),
        {
            "cohortManifestSha256": cohort["manifestSha256"],
            "baseWeightsSha256": spec["base"]["weightsSha256"],
            "basePresetSha256": spec["base"]["presetSha256"],
            "mode": preset.mode,
        },
    )
    resume = spec.get("resume")
    control = ChildControl(spec, run_dir, lease, record, counter)
    try:
        result = train(
            network=network,
            preset=preset,
            plan=plan,
            batches=batches,
            losses=lambda net, batch: losses(cast(NeuralGridNetwork, net), batch, recipe, device),
            evaluate=evaluate,
            control=control,
            checkpoint_directory=run_dir / "checkpoints",
            resume=None
            if resume is None
            else (run_dir / "checkpoints" / resume["path"], resume["sha256"]),
            device=device,
        )
    finally:
        batches.close()
    network.load_state_dict(
        best_weights(result.checkpoint_path, result.checkpoint_sha256, plan.binding)
    )
    export = _export(
        spec,
        run_dir,
        network,
        recipe,
        preset_payload,
        preset_bytes,
        result,
        (crops, None if not screen_mode else validation),
    )
    return {
        "status": "exported",
        "stopReason": result.stop_reason,
        "steps": result.steps,
        "bestStep": result.best_step,
        "bestMetric": result.best_metric,
        "metric": preset.early_stopping.metric,
        "checkpoint": {"path": result.checkpoint_path.name, "sha256": result.checkpoint_sha256},
        "history": result.history,
        "export": export,
    }


def _export(
    spec: Mapping[str, Any],
    run_dir: Path,
    network: Any,
    recipe: Any,
    preset_payload: Mapping[str, Any],
    preset_bytes: bytes,
    result: Any,
    parity_source: tuple[Any, Any],
) -> dict[str, Any]:
    """Immutable export directory named by the final checkpoint; re-use an identical one."""
    from ..training_core.grid_training import (
        bundle_document,
        export_graphs,
        preset_payload_fingerprint,
        raw_parity,
        weights_bytes,
    )
    from .grid_training_data import parity_inputs

    destination = run_dir / f"{EXPORT_PREFIX}{result.checkpoint_sha256[:16]}"
    if (destination / "bundle.json").exists():
        existing = json.loads((destination / "bundle.json").read_text(encoding="utf-8"))
        if existing["provenance"]["checkpointSha256"] != result.checkpoint_sha256:
            raise ChildError("GRID_TRAINING_EXPORT_CONFLICT")
        _verify_recovered(destination, existing, preset_bytes, result.checkpoint_path)
        return _export_view(destination, existing)
    staging = Path(tempfile.mkdtemp(prefix=".export-", dir=run_dir))
    try:
        network = network.cpu().eval()
        weights = weights_bytes(network.state_dict())
        (staging / "weights.pt").write_bytes(weights)
        export_graphs(network, recipe, staging)
        shutil.copyfile(result.checkpoint_path, staging / "checkpoint.pt")
        (staging / "preset.json").write_bytes(preset_bytes)
        crops, photos = parity_source
        board, pixels = parity_inputs(crops, photos, recipe)
        parity = raw_parity(network, staging, board, pixels)
        if not parity["passed"]:
            raise ChildError("GRID_TRAINING_ONNX_PARITY_FAILED")
        files = {
            name: sha256_file(staging / name)
            for name in ("screen.onnx", "board.onnx", "weights.pt")
        }
        provenance = {
            "runId": spec["jobId"],
            "exportId": str(uuid.uuid5(uuid.UUID(spec["jobId"]), result.checkpoint_sha256)),
            "presetFingerprint": preset_payload_fingerprint(preset_payload),
            "trainingPresetId": spec["preset"]["id"],
            "trainingPresetFingerprint": spec["preset"]["fingerprint"],
            "weightsSha256": sha256_bytes(weights),
            "checkpointSha256": result.checkpoint_sha256,
            "snapshotId": spec["cohort"]["manifestSha256"],
            "baseVersionId": spec["base"]["versionId"],
            "bestStep": result.best_step,
        }
        bundle = bundle_document(
            preset_payload=preset_payload,
            preset_fingerprint=provenance["presetFingerprint"],
            weights_sha256=provenance["weightsSha256"],
            files=files,
            provenance=provenance,
            parity=parity,
        )
        write_json_atomic(staging / "bundle.json", bundle)
        for path in staging.iterdir():
            with path.open("r+b") as stream:  # Windows fsync needs a writable handle
                os.fsync(stream.fileno())
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return _export_view(destination, bundle)


def _verify_recovered(
    destination: Path, bundle: Mapping[str, Any], preset_bytes: bytes, checkpoint: Path
) -> None:
    """A re-used export must still match its recorded hashes, never be re-hashed into truth."""
    provenance = bundle["provenance"]
    expected = {**dict(bundle["files"]), "checkpoint.pt": provenance["checkpointSha256"]}
    if (
        expected.get("weights.pt") != provenance["weightsSha256"]
        or (destination / "preset.json").read_bytes() != preset_bytes
        or sha256_file(checkpoint) != provenance["checkpointSha256"]
        or not bundle.get("parity", {}).get("passed")
        or any(sha256_file(destination / name) != sha for name, sha in expected.items())
    ):
        raise ChildError("GRID_TRAINING_EXPORT_CORRUPT")


def _export_view(destination: Path, bundle: Mapping[str, Any]) -> dict[str, Any]:
    names = (
        "screen.onnx",
        "board.onnx",
        "weights.pt",
        "checkpoint.pt",
        "preset.json",
        "bundle.json",
    )
    return {
        "directory": destination.name,
        "provenance": dict(bundle["provenance"]),
        "files": {
            name: {
                "sha256": sha256_file(destination / name),
                "sizeBytes": (destination / name).stat().st_size,
            }
            for name in names
        },
    }


def probe() -> int:
    print(json.dumps(asdict(probe_runtime()), sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--probe", action="store_true")
    group.add_argument("--spec", type=Path)
    args = parser.parse_args(argv)
    if args.probe:
        return probe()
    return run(args.spec.resolve())


if __name__ == "__main__":
    sys.exit(main())
