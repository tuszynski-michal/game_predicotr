"""Iterative Mumie fine-tune of the run-1 neural_grid model (D-490 amendment, TASK-0825).

``python -m game_predictor_worker.vision_lab.neural_grid_finetune <command>``

iterate   one fine-tune iteration end to end, resumable and idempotent:
          export of the complete Mumie photos -> holdout assignment -> iteration
          snapshot -> fine-tune on the GPU (detached worker, preset D) -> evaluation
          (Mumie holdout, 777 development) -> ONNX export -> new proposals for the
          photos that are still incomplete -> report
status    ledger, budget and per-iteration results

Protocol. The third D-481 training run is ONE ``RunManager`` run with preset D. Every
iteration is one attempt of that run: the first iteration creates the run (admitted by
``admit_run``: at most three training runs, one per preset), every later iteration is a
resume of it. ``used_seconds`` therefore stays durable across iterations and processes, and
the run's ``max_seconds`` (14 400 s) bounds all iterations together: the run contract, the
trainer's planning from the durable ``used_seconds``, ``RunManager`` refusing work past the
limit and the worker watchdog all apply unchanged. A finished iteration ends its attempt as
``cancelled`` with ``NEURAL_GRID_ITERATION_COMPLETE`` and leaves its own checkpoint
(``checkpoint_epoch`` = iteration number, best state = the selected candidate) and its own
attempt report. Smoke iterations use a separate ledger and a smoke run (<= 50 steps) that
does not count towards the budget.

Data. Only complete Mumie photos of the lab annotation store (D-484) enter an iteration.
Each newly complete photo gets a permanent role: photos are numbered after all earlier
assignments in the order of a stable key (SHA-256 of a fixed prefix and the source SHA-256,
not the order of clicks) and every fifth number is ``holdout``. Holdout photos are written
to the iteration snapshot with role ``development`` only, and the worker refuses to train
when any registered holdout photo appears among its training photos. The 777 data are read
from the production snapshot v2 through the role guard (``training`` and ``development``
only; ``gold`` is never read).

The ledger (``<runs root>/finetune-D/ledger.json``) records the holdout registry and the
progress of every iteration; re-running ``iterate`` continues where it stopped and never
trains an iteration twice. Torch is imported only by the functions that need it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np

from game_predictor_worker.training_core.runtime import TrainingInterrupted

from .annotations import exclusive, read_checked, write_atomic
from .neural_grid_protocol import (
    FINETUNE_PRESET,
    SMOKE_EVAL_IMAGES,
    SMOKE_ROUNDS,
    SMOKE_STEPS_PER_ROUND,
    FinetunePreset,
    NeuralGridRunRequest,
    Preset,
    build_request,
    finetune_settings,
    load_preset,
    validate_request,
)
from .neural_grid_runs import (
    DEFAULT_DATA,
    DEFAULT_ROOT,
    DEFAULT_SNAPSHOT,
    build_manager,
    describe,
    runtime_settings,
)
from .run_contracts import RunMutation, RunState
from .runs import ACTIVE, RunManager, Token, checkpoint_binding

ITERATION_COMPLETE: Final = "NEURAL_GRID_ITERATION_COMPLETE"
LEDGER_FORMAT: Final = "neural-grid-finetune-ledger-v1"
PLAN_FORMAT: Final = "neural-grid-finetune-plan-v1"
REPORT_FORMAT: Final = "neural-grid-finetune-report-v1"
REQUEST_IDS: Final = {"train": "ng-finetune-d-train", "smoke": "ng-finetune-d-smoke"}
HOLDOUT_PREFIX: Final = "TASK-0825-mumie-holdout-v1:"
GAME: Final = "mumie"
LAB_SNAPSHOT_ID: Final = "0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2"
DEFAULT_CATALOG: Final = DEFAULT_DATA / "snapshots" / LAB_SNAPSHOT_ID
DEFAULT_ANNOTATIONS: Final = DEFAULT_DATA / "annotations" / LAB_SNAPSHOT_ID
DEFAULT_PROPOSALS: Final = DEFAULT_DATA / "assisted-annotation" / "proposals"
POLL_SECONDS: Final = 15.0
EVALUATION_ESTIMATE: Final = 60.0
CHECKPOINT_ESTIMATE: Final = 30.0
Purpose = Literal["smoke", "train"]


# --- pure rules ---------------------------------------------------------------------------------


def holdout_key(source_sha256: str) -> str:
    """Stable ordering key of a photo: independent of click order and of the source id."""

    return hashlib.sha256((HOLDOUT_PREFIX + source_sha256).encode()).hexdigest()


def assign_holdout(
    registry: Mapping[str, Mapping[str, Any]],
    photos: Mapping[str, str],
    every: int,
    iteration: int,
) -> dict[str, dict[str, Any]]:
    """Permanent roles: new photos (``source_id -> source sha256``) numbered in key order
    after every earlier assignment; each ``every``-th number is holdout. Existing entries
    are never changed, so a photo keeps its role even when it is later reopened."""

    updated = {source_id: dict(entry) for source_id, entry in registry.items()}
    position = max((int(e["position"]) for e in updated.values()), default=0)
    fresh = [(holdout_key(sha), sid) for sid, sha in photos.items() if sid not in updated]
    for key, source_id in sorted(fresh):
        position += 1
        updated[source_id] = {
            "role": "holdout" if position % every == 0 else "train",
            "position": position,
            "key": key,
            "iteration": iteration,
        }
    return updated


def holdout_ids(registry: Mapping[str, Mapping[str, Any]]) -> set[str]:
    return {source_id for source_id, entry in registry.items() if entry["role"] == "holdout"}


def guard_training_photos(train_ids: Sequence[str], registry_holdout: set[str]) -> None:
    """The fine-tune data never contain a Mumie holdout photo (D-490)."""

    leaked = sorted(set(train_ids) & registry_holdout)
    if leaked:
        raise ValueError(f"NEURAL_GRID_HOLDOUT_IN_TRAINING:{','.join(leaked[:5])}")


def planned_train_seconds(settings: FinetunePreset, train_photos: int) -> float:
    """Training time of an iteration: grows with the Mumie training photos, bounded."""

    return float(
        min(
            settings.iteration_train_seconds_max,
            max(
                settings.iteration_train_seconds_min,
                settings.train_seconds_per_mumie_photo * train_photos,
            ),
        )
    )


def affordable_train_seconds(
    preset: Preset, used_seconds: float, planned: float, overhead: float
) -> float:
    """Training seconds that still fit the durable run budget after ``overhead``."""

    remaining = preset.schedule.max_run_seconds - used_seconds
    return float(min(planned, remaining - preset.schedule.final_reserve_seconds - overhead))


def select_candidate(
    candidates: Sequence[Mapping[str, Any]],
    settings: FinetunePreset,
    holdout_photos: int,
    *,
    smoke: bool = False,
) -> tuple[int | None, str]:
    """Candidate state of the iteration (1-based) or ``None`` to keep the previous state.

    Admissible: 777 development complete-and-correct rate not below run 1 by more than
    ``development_max_drop``. Among them the maximum Mumie-holdout rate (tie: lower holdout
    image-macro, then higher development rate, then the earlier candidate). With fewer than
    ``holdout_min_photos`` holdout photos the last admissible state is taken.
    """

    if not candidates:
        return None, "no_candidate"
    if smoke:
        return int(candidates[-1]["candidate"]), "smoke_final_state"
    floor = settings.init.development_photo_complete_correct_rate - settings.development_max_drop
    admissible = [
        c
        for c in candidates
        if c["development"]["photo_complete_correct_rate"] is not None
        and float(c["development"]["photo_complete_correct_rate"]) >= floor - 1e-9
    ]
    if not admissible:
        return None, "previous_state_kept_777_development_drop"
    if holdout_photos < settings.holdout_min_photos:
        return int(admissible[-1]["candidate"]), "last_admissible_state_holdout_too_small"

    def key(c: Mapping[str, Any]) -> tuple[float, float, float, int]:
        holdout: Mapping[str, Any] = c["holdout"] or {}
        macro = holdout.get("image_macro")
        return (
            float(holdout.get("photo_complete_correct_rate") or 0.0),
            -float(1.0 if macro is None else macro),
            float(c["development"]["photo_complete_correct_rate"]),
            -int(c["candidate"]),
        )

    return int(max(admissible, key=key)["candidate"]), "max_mumie_holdout_with_777_guard"


class MixedBatchSampler:
    """Infinite batches of ``primary_per_batch`` Mumie and the rest 777 indices.

    Indices ``[0, primary)`` are Mumie training photos, ``[primary, primary + reference)``
    777 training photos; both are drawn uniformly with replacement.
    """

    def __init__(
        self, primary: int, reference: int, batch: int, primary_per_batch: int, seed: int
    ) -> None:
        if primary < 1 or reference < 1 or not 1 <= primary_per_batch < batch:
            raise ValueError("NEURAL_GRID_FINETUNE_BATCH_INVALID")
        self.primary, self.reference = primary, reference
        self.batch, self.primary_per_batch, self.seed = batch, primary_per_batch, seed

    def __iter__(self) -> Iterator[list[int]]:
        rng = np.random.default_rng(self.seed)
        while True:
            mumie = rng.integers(0, self.primary, self.primary_per_batch)
            reference = self.primary + rng.integers(
                0, self.reference, self.batch - self.primary_per_batch
            )
            yield [int(i) for i in np.concatenate([mumie, reference])]


def _stats(values: Sequence[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "mean": float(np.mean(ordered)),
        "median": float(np.median(ordered)),
        "p95": float(np.percentile(ordered, 95)),
    }


def proposal_accuracy(rows: Sequence[Mapping[str, Any]], previous_ids: set[str]) -> dict[str, Any]:
    """How the operator treated the proposals on the photos completed since the last
    iteration: accepted unchanged, corrected, drawn by hand (from label provenance)."""

    batch = [row for row in rows if row["imageId"] not in previous_ids]
    origins: Counter[str] = Counter()
    by_set: dict[str, Counter[str]] = {}
    shifts: list[float] = []
    for row in batch:
        for board in row["boards"]:
            origin = str(board["origin"])
            origins[origin] += 1
            if origin.startswith("proposal_"):
                key = str(board.get("proposalSetId") or "unknown")
                by_set.setdefault(key, Counter())[origin] += 1
                if origin == "proposal_corrected" and board.get("maxCornerShiftPx") is not None:
                    shifts.append(float(board["maxCornerShiftPx"]))
    boards = sum(origins.values())
    offered = origins["proposal_unchanged"] + origins["proposal_corrected"]
    return {
        "photos": len(batch),
        "boards": boards,
        "origins": dict(sorted(origins.items())),
        "unchanged_share_of_boards": origins["proposal_unchanged"] / boards if boards else None,
        "corrected_share_of_boards": origins["proposal_corrected"] / boards if boards else None,
        "manual_share_of_boards": origins["manual"] / boards if boards else None,
        "unchanged_share_of_used_proposals": (
            origins["proposal_unchanged"] / offered if offered else None
        ),
        "by_proposal_set": {key: dict(value) for key, value in sorted(by_set.items())},
        "corrected_max_corner_shift_px": _stats(shifts),
        "active_seconds_per_photo": _stats([float(row["activeMs"]) / 1000 for row in batch]),
        "photo_ids": sorted(str(row["imageId"]) for row in batch),
    }


def _compact(summary: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    keys = (
        "photos",
        "photo_complete_correct",
        "photo_complete_correct_rate",
        "image_macro",
        "board_recovery_rate",
        "detection_recall",
        "nme_median",
        "nme_p95",
        "false_boards",
        "evaluation_seconds",
    )
    return {key: summary.get(key) for key in keys}


# --- ledger -------------------------------------------------------------------------------------


def ledger_directory(root: Path, purpose: str) -> Path:
    return root / (f"finetune-{FINETUNE_PRESET}" + ("-smoke" if purpose == "smoke" else ""))


def iteration_directory(root: Path, purpose: str, iteration: int) -> Path:
    return ledger_directory(root, purpose) / "iterations" / f"{iteration:02d}"


class Ledger:
    """Durable progress of the fine-tune run: holdout registry and iteration steps."""

    def __init__(self, root: Path, purpose: Purpose, fingerprint: str) -> None:
        self.root = root
        self.purpose = purpose
        self.fingerprint = fingerprint
        self.directory = ledger_directory(root, purpose)
        self.path = self.directory / "ledger.json"

    @contextmanager
    def locked(self) -> Iterator[None]:
        """One ``iterate`` at a time; the worker never writes the ledger."""

        try:
            with exclusive(self.directory):
                yield
        except ValueError as error:
            if str(error) == "ANNOTATION_STORE_BUSY":
                raise SystemExit("NEURAL_GRID_FINETUNE_BUSY: another iterate is running") from error
            raise

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "format": LEDGER_FORMAT,
                "purpose": self.purpose,
                "preset": FINETUNE_PRESET,
                "preset_fingerprint": self.fingerprint,
                "run_id": None,
                "holdout": {},
                "iterations": {},
            }
        data = read_checked(self.path)
        if (
            data.get("format") != LEDGER_FORMAT
            or data.get("purpose") != self.purpose
            or data.get("preset_fingerprint") != self.fingerprint
        ):
            raise ValueError("NEURAL_GRID_FINETUNE_LEDGER_MISMATCH")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path, data)


def read_plan(root: Path, purpose: str, iteration: int) -> dict[str, Any]:
    plan = read_checked(iteration_directory(root, purpose, iteration) / "plan.json")
    if plan.get("format") != PLAN_FORMAT or plan.get("iteration") != iteration:
        raise ValueError("NEURAL_GRID_ITERATION_PLAN_INVALID")
    if plan.get("purpose") != purpose:
        raise ValueError("NEURAL_GRID_ITERATION_PLAN_INVALID")
    return plan


# --- worker side (GPU) ------------------------------------------------------------------------


def initial_weights(
    manager: RunManager, run: RunState, settings: FinetunePreset, iteration: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Start state of an iteration: run-1 best weights (iteration 1, checksum-pinned) or
    the selected state of the previous iteration (its checkpoint's best state)."""

    import torch

    from game_predictor_worker.training_core.checkpoint import load_checkpoint

    from .run_files import verify_artifact

    if iteration == 1:
        init = settings.init
        base = Path((manager.settings or {}).get("init_root") or manager.root)
        directory = base / init.export_directory
        bundle = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
        provenance = bundle.get("provenance", {})
        if (
            bundle.get("weights_sha256") != init.weights_sha256
            or bundle.get("preset_fingerprint") != init.preset_fingerprint
            or provenance.get("run_id") != init.run_id
            or provenance.get("checkpoint_sha256") != init.checkpoint_sha256
            or provenance.get("best_round") != init.best_round
        ):
            raise ValueError("NEURAL_GRID_FINETUNE_INIT_MISMATCH")
        content = (directory / "weights.pt").read_bytes()
        if hashlib.sha256(content).hexdigest() != init.weights_sha256:
            raise ValueError("NEURAL_GRID_FINETUNE_INIT_CHECKSUM_MISMATCH")
        import io

        state = torch.load(io.BytesIO(content), map_location="cpu", weights_only=True)
        return state, [], {"source": "run1_export", "weights_sha256": init.weights_sha256}
    if run.checkpoint is None or run.checkpoint_epoch != iteration - 1:
        raise ValueError("NEURAL_GRID_FINETUNE_PREVIOUS_CHECKPOINT_MISSING")
    value = load_checkpoint(
        verify_artifact(manager.root, run.checkpoint),
        run.checkpoint.sha256,
        expected_binding=checkpoint_binding(run.request),
    )
    best = value.get("bestState") or {}
    if "model" not in best or best.get("round") != iteration - 1:
        raise ValueError("NEURAL_GRID_BEST_STATE_MISSING")
    return (
        best["model"],
        list(value["history"]),
        {"source": "previous_iteration", "checkpoint_sha256": run.checkpoint.sha256},
    )


def finetune_candidates(
    *,
    network: Any,
    preset: Preset,
    device: str,
    mumie_train: Sequence[Any],
    holdout: Sequence[Any],
    reference_train: Sequence[Any],
    reference_development: Sequence[Any],
    train_seconds: float,
    candidates: int,
    seed: int,
    budget: Any,
    steps_per_candidate: int | None = None,
    log_directory: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, int]:
    """Train ``candidates`` equal slices from the loaded start state; after each slice
    evaluate the 777 development photos and the Mumie holdout and keep a CPU copy of the
    weights. Returns the candidates, the holdout result of the start state and the steps.

    ``steps_per_candidate`` (smoke, tests) replaces the time slices with reserved steps.
    ``budget`` is the run heartbeat (``check``, ``beat``, ``reserve_step``,
    ``used_seconds``, ``cancel_requested``); tests pass a stand-in.
    """

    import torch
    from torch.amp.grad_scaler import GradScaler
    from torch.utils.data import DataLoader

    from .neural_grid_data import TrainingDataset
    from .neural_grid_training import compute_losses, evaluate_network, learning_rate

    settings = finetune_settings(preset)
    cuda = device.startswith("cuda")
    holdout_before = (
        evaluate_network(network, preset, list(holdout), device)[0] if holdout else None
    )
    optimizer = torch.optim.AdamW(
        network.parameters(),
        lr=preset.optimization.learning_rate,
        weight_decay=preset.optimization.weight_decay,
    )
    scaler = GradScaler("cuda", enabled=cuda)
    samples = [*mumie_train, *reference_train]
    workers = preset.optimization.data_workers
    loader: DataLoader[Any] = DataLoader(
        TrainingDataset(samples, preset, seed),  # type: ignore[arg-type]
        batch_sampler=MixedBatchSampler(
            len(mumie_train),
            len(reference_train),
            preset.optimization.batch_images,
            settings.mumie_images_per_batch,
            seed,
        ),
        num_workers=workers,
        persistent_workers=workers > 0,
        pin_memory=cuda,
        prefetch_factor=4 if workers > 0 else None,
    )
    stream = iter(loader)
    slice_seconds = train_seconds / candidates
    results: list[dict[str, Any]] = []
    step = 0
    nonfinite = 0
    losses_path = None if log_directory is None else log_directory / "losses.jsonl"
    trained_seconds = 0.0
    for candidate in range(1, candidates + 1):
        network.train()
        slice_started = time.monotonic()
        sums: dict[str, float] = {}
        window: dict[str, float] = {}
        steps = 0
        window_steps, window_started = 0, time.monotonic()
        while True:
            elapsed = time.monotonic() - slice_started
            if steps_per_candidate is not None:
                if steps >= steps_per_candidate:
                    break
                budget.reserve_step()
                progress = ((candidate - 1) + steps / steps_per_candidate) / candidates
            elif elapsed >= slice_seconds:
                break
            else:
                progress = (trained_seconds + elapsed) / max(train_seconds, 1e-9)
            budget.check()
            if budget.cancel_requested:
                raise TrainingInterrupted("RUN_CANCELLED")
            rate = learning_rate(preset, progress)
            for group in optimizer.param_groups:
                group["lr"] = rate
            batch = next(stream)
            losses = compute_losses(network, batch, preset, device)
            optimizer.zero_grad(set_to_none=True)
            if not torch.isfinite(losses["total"]):
                nonfinite += 1
                if nonfinite > 20:
                    raise ValueError("NEURAL_GRID_LOSS_NONFINITE")
                continue
            nonfinite = 0
            scaler.scale(losses["total"]).backward()  # type: ignore[no-untyped-call]
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(network.parameters(), preset.optimization.gradient_clip)
            scaler.step(optimizer)
            scaler.update()
            step += 1
            steps += 1
            window_steps += 1
            for name, tensor in losses.items():
                number = float(tensor.detach())
                sums[name] = sums.get(name, 0.0) + number
                window[name] = window.get(name, 0.0) + number
            if losses_path is not None and (steps_per_candidate is not None or window_steps >= 50):
                now = time.monotonic()
                line = {
                    "step": step,
                    "candidate": candidate,
                    "lr": rate,
                    "progress": progress,
                    "steps_per_second": window_steps / max(now - window_started, 1e-6),
                    **{k: v / window_steps for k, v in window.items()},
                }
                with losses_path.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(line) + "\n")
                window, window_steps, window_started = {}, 0, now
        train_slice = time.monotonic() - slice_started
        trained_seconds += train_slice
        evaluation_started = time.monotonic()
        development, _ = evaluate_network(network, preset, list(reference_development), device)
        holdout_summary = (
            evaluate_network(network, preset, list(holdout), device)[0] if holdout else None
        )
        budget.beat()
        results.append(
            {
                "candidate": candidate,
                "steps": steps,
                "global_step": step,
                "train_seconds": train_slice,
                "evaluation_seconds": time.monotonic() - evaluation_started,
                "used_seconds": budget.used_seconds,
                "train_loss": {k: v / max(steps, 1) for k, v in sums.items()},
                "development": development,
                "holdout": holdout_summary,
                "model": {k: v.detach().cpu().clone() for k, v in network.state_dict().items()},
            }
        )
    del stream, loader
    return results, holdout_before, step


def train_iteration(
    manager: RunManager, run_id: str, lease: Token, *, device: str | None = None
) -> dict[str, Any]:
    """The detached worker body of one iteration (one attempt of run D)."""

    import torch
    from torch.amp.grad_scaler import GradScaler

    from game_predictor_worker.training_core.checkpoint import checkpoint_bytes, make_checkpoint

    from .neural_grid_data import load_samples, open_snapshot, verify_images
    from .neural_grid_model import NeuralGridNetwork
    from .neural_grid_training import Heartbeat, _ScalerSlot, seed_everything

    run = manager.detail(run_id)
    request = run.request
    if not isinstance(request, NeuralGridRunRequest) or request.preset != FINETUNE_PRESET:
        raise ValueError("NEURAL_GRID_REQUEST_INVALID")
    preset = validate_request(request)
    settings = finetune_settings(preset)
    if device is None:
        if not torch.cuda.is_available():
            raise ValueError("RUN_GPU_UNAVAILABLE")  # no CPU fallback (TASK-0802)
        device = "cuda"
    iteration = run.checkpoint_epoch + 1
    if iteration > request.configuration.epochs:
        raise ValueError("NEURAL_GRID_FINETUNE_ITERATIONS_EXHAUSTED")
    smoke = request.purpose == "smoke"
    plan = read_plan(manager.root, request.purpose, iteration)
    if plan["preset_fingerprint"] != request.preset_fingerprint:
        raise ValueError("NEURAL_GRID_ITERATION_PLAN_INVALID")
    attempt_dir = manager.root / run_id / f"attempt-{run.attempt}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    reference_root = Path((manager.settings or {})["snapshot"])
    if open_snapshot(reference_root).snapshot_id != request.manifest_id:
        raise ValueError("NEURAL_GRID_SNAPSHOT_MISMATCH")

    with Heartbeat(manager, run_id, lease) as heartbeat:
        started = time.monotonic()
        reference = load_samples(reference_root, ("training", "development"))
        verify_images(reference, open_snapshot(reference_root).files)
        reference_train = [s for s in reference if s.role == "training"]
        reference_development = [s for s in reference if s.role == "development"]
        if smoke:
            reference_development = reference_development[:SMOKE_EVAL_IMAGES]
        mumie_root = Path(plan["snapshot"]["directory"])
        mumie_info = open_snapshot(mumie_root)
        if mumie_info.snapshot_id != plan["snapshot"]["snapshot_id"]:
            raise ValueError("NEURAL_GRID_ITERATION_SNAPSHOT_MISMATCH")
        mumie = load_samples(mumie_root, ("training", "development"))
        verify_images(mumie, mumie_info.files)
        mumie_train = [s for s in mumie if s.role == "training"]
        holdout = [s for s in mumie if s.role == "development"]
        registry_holdout = set(plan["registry_holdout_ids"])
        if (
            sorted(s.image_id for s in mumie_train) != sorted(plan["train_ids"])
            or sorted(s.image_id for s in holdout) != sorted(plan["holdout_ids"])
            or not set(plan["holdout_ids"]) <= registry_holdout
        ):
            raise ValueError("NEURAL_GRID_ITERATION_DATA_MISMATCH")
        guard_training_photos([s.image_id for s in mumie_train], registry_holdout)
        if not mumie_train:
            raise ValueError("NEURAL_GRID_FINETUNE_NO_TRAINING_PHOTOS")
        data_seconds = time.monotonic() - started
        heartbeat.beat()
        heartbeat.check()

        generator = seed_everything(request.seed + iteration)
        network = NeuralGridNetwork(preset.board.stride)
        init_state, history, init_info = initial_weights(manager, run, settings, iteration)
        network.load_state_dict(init_state)
        network.to(device)
        candidates = SMOKE_ROUNDS if smoke else settings.candidates_per_iteration
        train_seconds = float(plan["train_seconds"])
        if not smoke:
            overhead = candidates * EVALUATION_ESTIMATE + CHECKPOINT_ESTIMATE
            train_seconds = affordable_train_seconds(
                preset, heartbeat.used_seconds, train_seconds, overhead
            )
            if train_seconds < preset.schedule.minimum_round_seconds:
                raise TrainingInterrupted("RUN_BUDGET_EXHAUSTED")
        cuda = device.startswith("cuda")
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        results, holdout_before, steps = finetune_candidates(
            network=network,
            preset=preset,
            device=device,
            mumie_train=mumie_train,
            holdout=holdout,
            reference_train=reference_train,
            reference_development=reference_development,
            train_seconds=train_seconds,
            candidates=candidates,
            seed=request.seed + iteration,
            budget=heartbeat,
            steps_per_candidate=SMOKE_STEPS_PER_ROUND if smoke else None,
            log_directory=attempt_dir,
        )
        selected, rule = select_candidate(results, settings, len(holdout), smoke=smoke)
        if selected is None:
            model, summary, holdout_summary = init_state, None, holdout_before
        else:
            chosen = results[selected - 1]
            model, summary, holdout_summary = (
                chosen["model"],
                chosen["development"],
                chosen["holdout"],
            )
        entry = {
            "iteration": iteration,
            "attempt": run.attempt,
            "plan": {
                "train_ids": plan["train_ids"],
                "holdout_ids": plan["holdout_ids"],
                "snapshot_id": plan["snapshot"]["snapshot_id"],
                "export_id": plan["export"]["export_id"],
            },
            "init": init_info,
            "planned_train_seconds": float(plan["train_seconds"]),
            "train_seconds": sum(c["train_seconds"] for c in results),
            "data_seconds": data_seconds,
            "steps": steps,
            "holdout_before": holdout_before,
            "candidates": [{k: v for k, v in c.items() if k != "model"} for c in results],
            "selected_candidate": selected,
            "selection_rule": rule,
            "development_reference": {
                "run_id": settings.init.run_id,
                "photo_complete_correct_rate": (
                    settings.init.development_photo_complete_correct_rate
                ),
                "image_macro": settings.init.development_image_macro,
                "max_drop": settings.development_max_drop,
            },
            "selected_development": summary,
            "selected_holdout": holdout_summary,
            "mumie_train_photos": len(mumie_train),
            "mumie_holdout_photos": len(holdout),
            "reference_train_photos": len(reference_train),
            "reference_development_photos": len(reference_development),
            "max_vram_bytes": torch.cuda.max_memory_allocated() if cuda else None,
        }
        history = [*history, entry]
        best = {
            "round": iteration,
            "candidate": selected,
            "rule": rule,
            "summary": summary,
            "holdout": holdout_summary,
            "model": model,
        }
        optimizer = torch.optim.AdamW(network.parameters())
        heartbeat.check()
        manager.checkpoint(
            run_id,
            lease,
            checkpoint_bytes(
                make_checkpoint(
                    network,
                    optimizer,
                    _ScalerSlot(GradScaler("cuda", enabled=cuda)),
                    generator,
                    binding=checkpoint_binding(request),
                    epoch=iteration,
                    global_step=steps,
                    history=history,
                    best_state=best,
                )
            ),
            iteration,
        )
        write_atomic(
            attempt_dir / "progress.json",
            {
                "run_id": run_id,
                "iteration": iteration,
                "selected_candidate": selected,
                "selection_rule": rule,
                "development": _compact(summary),
                "holdout": _compact(holdout_summary),
                "used_seconds": heartbeat.used_seconds,
                "updated_at": time.time(),
            },
        )
        return {
            "iteration": iteration,
            "preset": request.preset,
            "preset_fingerprint": request.preset_fingerprint,
            "purpose": request.purpose,
            "selected_candidate": selected,
            "selection_rule": rule,
            "selected_development": _compact(summary),
            "selected_holdout": _compact(holdout_summary),
            "holdout_before": _compact(holdout_before),
            "candidates": [
                {
                    "candidate": c["candidate"],
                    "steps": c["steps"],
                    "development": _compact(c["development"]),
                    "holdout": _compact(c["holdout"]),
                }
                for c in results
            ],
            "train_seconds": sum(c["train_seconds"] for c in results),
            "steps": steps,
        }


def run_iteration_attempt(
    manager: RunManager, run_id: str, lease: Token, *, device: str | None = None
) -> RunState:
    """Train one iteration and end the attempt: ``cancelled`` with
    ``NEURAL_GRID_ITERATION_COMPLETE`` (more iterations allowed) or ``succeeded`` after the
    last allowed iteration. Errors and interruptions are finished by the caller."""

    metrics = train_iteration(manager, run_id, lease, device=device)
    run = manager.detail(run_id)
    final = metrics["iteration"] >= run.request.configuration.epochs
    return manager.finish(
        run_id,
        lease,
        status="succeeded" if final else "cancelled",
        error=None if final else ITERATION_COMPLETE,
        metrics=metrics,
    )


# --- command side -------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str), flush=True)


def _rows_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    from .snapshot import canonical

    return hashlib.sha256(b"".join(canonical(dict(row)) for row in rows)).hexdigest()


def plan_iteration(
    *,
    root: Path,
    purpose: Purpose,
    iteration: int,
    ledger: dict[str, Any],
    catalog: Any,
    annotations: Path,
    proposals_root: Path,
    preset: Preset,
    fingerprint: str,
    reference_snapshot_id: str,
    allow_same_data: bool = False,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Export -> permanent holdout roles -> iteration snapshot -> ``plan.json``."""

    from .assisted_annotation import (
        open_proposals,
        read_export,
        read_store_state,
        write_export,
        write_reader_snapshot,
    )

    settings = finetune_settings(preset)
    directory = iteration_directory(root, purpose, iteration)
    directory.mkdir(parents=True, exist_ok=True)
    state = read_store_state(annotations, catalog)
    proposals = open_proposals(proposals_root, catalog, (GAME,))
    export = write_export(catalog, state, proposals, directory / "export", (GAME,))
    rows = [row for row in read_export(export) if row["gameKey"] == GAME]
    if not rows:
        raise SystemExit("NEURAL_GRID_FINETUNE_NO_COMPLETE_PHOTOS: no complete Mumie photo")
    previous = ledger["iterations"].get(str(iteration - 1))
    previous_ids: set[str] = set()
    if previous is not None:
        previous_plan = read_plan(root, purpose, iteration - 1)
        previous_ids = set(previous_plan["photo_ids"])
        if previous_plan["rows_sha256"] == _rows_digest(rows) and not allow_same_data:
            raise SystemExit(
                "NEURAL_GRID_FINETUNE_NO_NEW_PHOTOS: the complete Mumie photos and their "
                "grids are unchanged since the previous iteration"
            )
    registry = assign_holdout(
        ledger["holdout"],
        {str(row["imageId"]): str(row["sourceChecksumSha256"]) for row in rows},
        settings.holdout_every,
        iteration,
    )
    registry_holdout = holdout_ids(registry)
    roles = {
        str(row["imageId"]): "development"
        if str(row["imageId"]) in registry_holdout
        else "training"
        for row in rows
    }
    train_ids = sorted(i for i, role in roles.items() if role == "training")
    holdout = sorted(i for i, role in roles.items() if role == "development")
    guard_training_photos(train_ids, registry_holdout)
    if not train_ids:
        raise SystemExit("NEURAL_GRID_FINETUNE_NO_TRAINING_PHOTOS")
    # Short parent path: image paths inside a snapshot are long (Windows MAX_PATH 260).
    snapshot = write_reader_snapshot(rows, catalog, ledger_directory(root, purpose) / "s", roles)
    plan = {
        "format": PLAN_FORMAT,
        "iteration": iteration,
        "purpose": purpose,
        "preset": FINETUNE_PRESET,
        "preset_fingerprint": fingerprint,
        "created_at": _now(),
        "store_revision": state.revision,
        "proposal_set_id": proposals.set_id,
        "export": {"directory": str(export), "export_id": export.name},
        "snapshot": {"directory": str(snapshot), "snapshot_id": snapshot.name},
        "reference_snapshot_id": reference_snapshot_id,
        "photo_ids": sorted(roles),
        "rows_sha256": _rows_digest(rows),
        "new_photo_ids": sorted(set(roles) - previous_ids),
        "train_ids": train_ids,
        "holdout_ids": holdout,
        "registry_holdout_ids": sorted(registry_holdout),
        "train_seconds": planned_train_seconds(settings, len(train_ids)),
    }
    path = directory / "plan.json"
    if path.exists():
        raise ValueError("NEURAL_GRID_ITERATION_PLAN_EXISTS")
    write_atomic(path, plan)
    return plan, registry


def _active_other(manager: RunManager, run_id: str | None) -> RunState | None:
    for run in manager.list(0, 100).runs:
        if run.status in ACTIVE and run.id != run_id:
            return run
    return None


def ensure_training(
    manager: RunManager,
    ledger: dict[str, Any],
    purpose: Purpose,
    iteration: int,
) -> RunState:
    """Create the run (first iteration) or resume it as a new attempt (later ones)."""

    run_id = ledger["run_id"]
    if run_id is None:
        from .neural_grid_data import open_snapshot

        settings = manager.settings or {}
        request = build_request(
            request_id=REQUEST_IDS[purpose],
            preset_name=FINETUNE_PRESET,
            purpose=purpose,
            snapshot_id=open_snapshot(Path(settings["snapshot"])).snapshot_id,
        )
        return manager.create_or_get_run(request)
    run = manager.detail(run_id)
    if run.checkpoint_epoch >= iteration or run.status in ACTIVE:
        return run
    if run.status == "succeeded":
        raise SystemExit("NEURAL_GRID_FINETUNE_ITERATIONS_EXHAUSTED: run D is finished")
    return manager.retry_run(
        run.id,
        RunMutation(
            request_id=f"ng-finetune-d-{purpose}-i{iteration}-a{run.attempt}",
            expected_attempt=run.attempt,
        ),
    )


def wait_for(manager: RunManager, run_id: str, log: Callable[[str], None]) -> RunState:
    last = 0.0
    while True:
        run = manager.detail(run_id)
        if run.status not in ACTIVE:
            return run
        if time.monotonic() - last >= 60:
            last = time.monotonic()
            log(
                f"{datetime.now():%H:%M:%S} run {run.id[:8]} attempt {run.attempt} "
                f"{run.status}, used {run.used_seconds:.0f} s"
            )
        time.sleep(POLL_SECONDS)


def load_iteration_state(
    manager: RunManager, run_id: str, iteration: int
) -> tuple[Any, dict[str, Any], dict[str, Any], str]:
    """Selected weights, best-state record and history entry of a trained iteration."""

    from game_predictor_worker.training_core.checkpoint import load_checkpoint

    from .neural_grid_model import NeuralGridNetwork
    from .run_files import verify_artifact

    run = manager.detail(run_id)
    if run.checkpoint is None or run.checkpoint_epoch != iteration:
        raise ValueError("NEURAL_GRID_ITERATION_CHECKPOINT_MISSING")
    value = load_checkpoint(
        verify_artifact(manager.root, run.checkpoint),
        run.checkpoint.sha256,
        expected_binding=checkpoint_binding(run.request),
    )
    best = value.get("bestState") or {}
    if best.get("round") != iteration or "model" not in best:
        raise ValueError("NEURAL_GRID_BEST_STATE_MISSING")
    entry = next((h for h in value["history"] if h.get("iteration") == iteration), None)
    if entry is None:
        raise ValueError("NEURAL_GRID_ITERATION_HISTORY_MISSING")
    preset = validate_request(run.request)
    network = NeuralGridNetwork(preset.board.stride)
    network.load_state_dict(best["model"])
    return network, {k: v for k, v in best.items() if k != "model"}, entry, run.checkpoint.sha256


def export_iteration(
    manager: RunManager, run_id: str, iteration: int, reference_snapshot: Path
) -> Path:
    """ONNX bundle of the selected state with PyTorch-ONNX parity (CPU)."""

    from .neural_grid_data import load_samples
    from .neural_grid_onnx import export_bundle

    run = manager.detail(run_id)
    assert isinstance(run.request, NeuralGridRunRequest)
    preset = validate_request(run.request)
    settings = finetune_settings(preset)
    network, best, _, checkpoint = load_iteration_state(manager, run_id, iteration)
    destination = manager.root / run_id / "exports" / f"iteration{iteration:02d}-{checkpoint[:16]}"
    if (destination / "bundle.json").exists():
        bundle = json.loads((destination / "bundle.json").read_text(encoding="utf-8"))
        if bundle.get("provenance", {}).get("checkpoint_sha256") != checkpoint:
            raise ValueError("NEURAL_GRID_EXPORT_CONFLICT")
        return destination
    development = load_samples(reference_snapshot, ("development",))[: settings.parity_images]
    export_bundle(
        network,
        preset,
        run.request.preset_fingerprint,
        {
            "run_id": run_id,
            "checkpoint_sha256": checkpoint,
            "best_round": iteration,
            "iteration": iteration,
            "selected_candidate": best.get("candidate"),
            "snapshot_id": run.request.manifest_id,
        },
        destination,
        development,
    )
    return destination


def publish_proposals(
    *,
    catalog: Any,
    annotations: Path,
    proposals_root: Path,
    bundle: Path,
    iteration: int,
    run_id: str,
    threads: int,
    log: Callable[[str], None],
) -> Path | None:
    """New create-only proposal set (generation = iteration) for incomplete Mumie photos;
    ``None`` when every Mumie photo is already complete."""

    from .assisted_annotation import (
        generate_proposals,
        open_proposals,
        photo_complete,
        read_store_state,
    )

    info = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    model = {
        "run_id": run_id,
        "iteration": iteration,
        "checkpoint_sha256": info["provenance"]["checkpoint_sha256"],
        "weights_sha256": info["weights_sha256"],
        "preset_fingerprint": info["preset_fingerprint"],
        "bundle": str(bundle),
    }
    for path in sorted(p for p in proposals_root.iterdir() if p.is_dir()):
        with suppress(OSError, ValueError, KeyError):
            payload = read_checked(path / "proposals.json")
            if payload.get("generation") == iteration and payload.get("model") == model:
                return path  # published before an interruption
    state = read_store_state(annotations, catalog)
    book = open_proposals(proposals_root, catalog, (GAME,))
    items = [
        item for item in book.items if not photo_complete(state, catalog.sources[item["source_id"]])
    ]
    if not items:
        log("every Mumie photo is complete: no new proposal set")
        return None
    return generate_proposals(
        catalog,
        state,
        None,
        bundle,
        proposals_root,
        threads=threads,
        log=log,
        items=items,
        generation=iteration,
        supersedes=book.set_id,
        model=model,
    )


def build_report(
    *,
    purpose: Purpose,
    iteration: int,
    plan: Mapping[str, Any],
    previous_plan: Mapping[str, Any] | None,
    entry: Mapping[str, Any],
    run: RunState,
    bundle: Path | None,
    proposals: Path | None,
    preset: Preset,
) -> dict[str, Any]:
    from .assisted_annotation import read_export

    settings = finetune_settings(preset)
    rows = read_export(Path(plan["export"]["directory"]))
    accuracy = proposal_accuracy(
        [row for row in rows if row["gameKey"] == GAME],
        set(previous_plan["photo_ids"]) if previous_plan else set(),
    )
    reference = settings.init.development_photo_complete_correct_rate
    development = entry["selected_development"]
    rate = None if development is None else development["photo_complete_correct_rate"]
    return {
        "format": REPORT_FORMAT,
        "decision_reference": "D-490",
        "task": "TASK-0825",
        "purpose": purpose,
        "iteration": iteration,
        "created_at": _now(),
        "run": {
            "id": run.id,
            "attempt": entry["attempt"],
            "used_seconds": run.used_seconds,
            "max_seconds": run.request.configuration.max_seconds,
            "remaining_seconds": run.request.configuration.max_seconds - run.used_seconds,
            "budget_counted": purpose == "train",
        },
        "data": {
            "export_id": plan["export"]["export_id"],
            "snapshot_id": plan["snapshot"]["snapshot_id"],
            "store_revision": plan["store_revision"],
            "complete_mumie_photos": len(plan["photo_ids"]),
            "new_photos_since_previous_iteration": len(plan["new_photo_ids"]),
            "mumie_train_photos": len(plan["train_ids"]),
            "mumie_holdout_photos": len(plan["holdout_ids"]),
            "reference_train_photos": entry["reference_train_photos"],
            "reference_development_photos": entry["reference_development_photos"],
        },
        "training": {
            "init": entry["init"],
            "planned_train_seconds": entry["planned_train_seconds"],
            "train_seconds": entry["train_seconds"],
            "steps": entry["steps"],
            "selected_candidate": entry["selected_candidate"],
            "selection_rule": entry["selection_rule"],
            "candidates": [
                {
                    "candidate": c["candidate"],
                    "steps": c["steps"],
                    "development": _compact(c["development"]),
                    "holdout": _compact(c["holdout"]),
                }
                for c in entry["candidates"]
            ],
            "max_vram_bytes": entry.get("max_vram_bytes"),
        },
        "measurements": {
            "mumie_holdout": {
                "photos": len(plan["holdout_ids"]),
                "before_iteration": _compact(entry["holdout_before"]),
                "selected_state": _compact(entry["selected_holdout"]),
                "small_sample": len(plan["holdout_ids"]) < settings.holdout_min_photos,
            },
            "development_777": {
                "selected_state": _compact(development),
                "run1_photo_complete_correct_rate": reference,
                "run1_image_macro": settings.init.development_image_macro,
                "delta_percentage_points": None if rate is None else 100 * (rate - reference),
                "max_drop_percentage_points": 100 * settings.development_max_drop,
                "photos_evaluated": entry["reference_development_photos"],
            },
            "proposal_accuracy_last_batch": accuracy,
        },
        "outputs": {
            "onnx_bundle": None if bundle is None else str(bundle),
            "proposal_set": None if proposals is None else str(proposals),
            "model_unchanged": entry["selected_candidate"] is None,
        },
    }


def _pct(value: Any) -> str:
    return "–" if value is None else f"{100 * float(value):.2f}%"


def report_markdown(report: Mapping[str, Any]) -> str:
    """Polish operator summary of one iteration."""

    m = report["measurements"]
    holdout = m["mumie_holdout"]
    development = m["development_777"]
    accuracy = m["proposal_accuracy_last_batch"]
    training = report["training"]
    data = report["data"]
    run = report["run"]

    def rate(summary: Mapping[str, Any] | None) -> str:
        if not summary:
            return "–"
        macro = summary.get("image_macro")
        return (
            f"{summary['photo_complete_correct']}/{summary['photos']} "
            f"({_pct(summary['photo_complete_correct_rate'])}), image-macro "
            + ("–" if macro is None else f"{macro:.5f}")
        )

    delta = development["delta_percentage_points"]
    lines = [
        f"# Iteracja {report['iteration']} doszkalania neural_grid na Mumiach "
        f"({report['purpose']})",
        "",
        f"- Run `{run['id']}`, próba {run['attempt']}; zużyty czas runu "
        f"{run['used_seconds']:.0f} s z {run['max_seconds']:.0f} s, pozostało "
        f"{run['remaining_seconds']:.0f} s"
        + ("" if run["budget_counted"] else " (smoke — poza budżetem)"),
        f"- Dane: {data['complete_mumie_photos']} kompletnych zdjęć Mumii "
        f"({data['new_photos_since_previous_iteration']} nowych), trening "
        f"{data['mumie_train_photos']}, odłożone {data['mumie_holdout_photos']}; 777: "
        f"{data['reference_train_photos']} zdjęć treningowych, ocena na "
        f"{data['reference_development_photos']} zdjęciach development.",
        f"- Trening: {training['train_seconds']:.0f} s, {training['steps']} kroków; wybrany stan: "
        + (
            f"kandydat {training['selected_candidate']}"
            if training["selected_candidate"] is not None
            else "bez zmiany (żaden kandydat nie spełnił warunku 777)"
        )
        + f" (`{training['selection_rule']}`).",
        "",
        "## Odłożone zdjęcia Mumii (D-483, względem siatek operatora)",
        "",
        f"- Przed iteracją: {rate(holdout['before_iteration'])}",
        f"- Po iteracji: {rate(holdout['selected_state'])}",
    ]
    if holdout["small_sample"]:
        lines.append("- Uwaga: mniej niż 3 odłożone zdjęcia — wynik ma bardzo szeroki margines.")
    lines += [
        "",
        "## Development 777",
        "",
        f"- Run 1: {_pct(development['run1_photo_complete_correct_rate'])}; po iteracji: "
        f"{rate(development['selected_state'])}; różnica "
        + ("–" if delta is None else f"{delta:+.2f} pkt proc.")
        + f" (dopuszczalny spadek {development['max_drop_percentage_points']:.1f} pkt proc.).",
        "",
        "## Trafność propozycji w ostatniej porcji",
        "",
        f"- Zdjęcia: {accuracy['photos']}, plansze: {accuracy['boards']}; przyjęte bez zmian "
        f"{_pct(accuracy['unchanged_share_of_boards'])}, poprawione "
        f"{_pct(accuracy['corrected_share_of_boards'])}, narysowane ręcznie "
        f"{_pct(accuracy['manual_share_of_boards'])}.",
    ]
    active = accuracy["active_seconds_per_photo"]
    if active:
        lines.append(
            f"- Czas aktywny na zdjęcie: średnio {active['mean']:.0f} s, mediana "
            f"{active['median']:.0f} s."
        )
    outputs = report["outputs"]
    lines += [
        "",
        "## Wyniki",
        "",
        f"- Eksport ONNX: `{outputs['onnx_bundle']}`",
        f"- Nowe propozycje: `{outputs['proposal_set']}`",
    ]
    return "\n".join(lines) + "\n"


def _manager_for(args: argparse.Namespace) -> RunManager:
    settings = runtime_settings(args)
    init_root = Path(args.init_root).resolve()
    if init_root != Path(args.root).resolve():
        settings["init_root"] = str(init_root)
    return build_manager(args.root, settings)


def command_iterate(args: argparse.Namespace) -> None:
    from .catalog import Catalog

    purpose: Purpose = "smoke" if args.smoke else "train"
    preset, fingerprint = load_preset(FINETUNE_PRESET)
    settings = finetune_settings(preset)
    manager = _manager_for(args)
    ledger = Ledger(args.root, purpose, fingerprint)
    catalog = Catalog(args.catalog)

    def log(message: str) -> None:
        print(message, flush=True)

    with ledger.locked():
        data = ledger.load()
        open_iterations = [int(k) for k, v in data["iterations"].items() if v["status"] != "done"]
        run = manager.detail(data["run_id"]) if data["run_id"] else None
        if open_iterations:
            iteration = min(open_iterations)
        else:
            iteration = len(data["iterations"]) + 1
            other = _active_other(manager, data["run_id"])
            if other is not None:
                raise SystemExit(f"RUN_BUSY: run {other.id} ({other.status}) uses the GPU")
            limit = SMOKE_ROUNDS if purpose == "smoke" else preset.schedule.rounds
            if iteration > limit or (run is not None and run.status == "succeeded"):
                raise SystemExit("NEURAL_GRID_FINETUNE_ITERATIONS_EXHAUSTED")
            if purpose == "train":
                used = run.used_seconds if run is not None else 0.0
                affordable = affordable_train_seconds(
                    preset,
                    used,
                    settings.iteration_train_seconds_max,
                    settings.iteration_overhead_seconds,
                )
                if affordable < preset.schedule.minimum_round_seconds:
                    raise SystemExit(
                        f"NEURAL_GRID_FINETUNE_BUDGET_EXHAUSTED: used {used:.0f} s of "
                        f"{preset.schedule.max_run_seconds} s"
                    )
            plan, registry = plan_iteration(
                root=args.root,
                purpose=purpose,
                iteration=iteration,
                ledger=data,
                catalog=catalog,
                annotations=args.annotations,
                proposals_root=args.proposals,
                preset=preset,
                fingerprint=fingerprint,
                reference_snapshot_id=Path(args.snapshot).name,
                allow_same_data=args.allow_same_data,
            )
            data["holdout"] = registry
            data["iterations"][str(iteration)] = {
                "status": "planned",
                "planned_at": _now(),
                "train_photos": len(plan["train_ids"]),
                "holdout_photos": len(plan["holdout_ids"]),
                "train_seconds": plan["train_seconds"],
            }
            ledger.save(data)
            log(
                f"iteration {iteration}: {len(plan['train_ids'])} Mumie training photos, "
                f"{len(plan['holdout_ids'])} holdout, planned {plan['train_seconds']:.0f} s"
            )
        entry = data["iterations"][str(iteration)]
        plan = read_plan(args.root, purpose, iteration)

        if entry["status"] == "planned":
            run = ensure_training(manager, data, purpose, iteration)
            if data["run_id"] is None:
                data["run_id"] = run.id
                ledger.save(data)
            if run.checkpoint_epoch < iteration:
                if args.no_wait:
                    _print({"iteration": iteration, "run": describe(args.root, run)})
                    return
                log(f"training iteration {iteration} in run {run.id} (attempt {run.attempt})")
                run = wait_for(manager, run.id, log)
            if run.checkpoint_epoch < iteration:
                raise SystemExit(
                    f"NEURAL_GRID_ITERATION_NOT_TRAINED: run {run.id} {run.status} "
                    f"{run.error}; run iterate again to resume the iteration"
                )
            entry.update(status="trained", trained_at=_now(), attempt=run.attempt)
            ledger.save(data)

        run_id = str(data["run_id"])
        _, best, history_entry, checkpoint = load_iteration_state(manager, run_id, iteration)
        if entry["status"] == "trained":
            if best.get("candidate") is None:
                entry.update(status="proposed", bundle=None, proposals=None, model_unchanged=True)
            else:
                bundle = export_iteration(manager, run_id, iteration, Path(args.snapshot))
                entry.update(status="exported", bundle=str(bundle), checkpoint=checkpoint)
            ledger.save(data)
        if entry["status"] == "exported":
            proposals = publish_proposals(
                catalog=catalog,
                annotations=args.annotations,
                proposals_root=args.proposals,
                bundle=Path(entry["bundle"]),
                iteration=iteration,
                run_id=run_id,
                threads=settings.proposal_threads,
                log=log,
            )
            entry.update(status="proposed", proposals=None if proposals is None else str(proposals))
            ledger.save(data)
        if entry["status"] == "proposed":
            previous_plan = read_plan(args.root, purpose, iteration - 1) if iteration > 1 else None
            report = build_report(
                purpose=purpose,
                iteration=iteration,
                plan=plan,
                previous_plan=previous_plan,
                entry=history_entry,
                run=manager.detail(run_id),
                bundle=None if entry.get("bundle") is None else Path(entry["bundle"]),
                proposals=None if entry.get("proposals") is None else Path(entry["proposals"]),
                preset=preset,
            )
            directory = iteration_directory(args.root, purpose, iteration)
            (directory / "report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True, default=str), "utf-8"
            )
            (directory / "report.md").write_text(report_markdown(report), "utf-8")
            entry.update(
                status="done",
                done_at=_now(),
                report=str(directory / "report.json"),
                selection_rule=history_entry["selection_rule"],
                holdout=_compact(history_entry["selected_holdout"]),
                development=_compact(history_entry["selected_development"]),
            )
            ledger.save(data)
            print(report_markdown(report), flush=True)


def command_status(args: argparse.Namespace) -> None:
    purpose: Purpose = "smoke" if args.smoke else "train"
    preset, fingerprint = load_preset(FINETUNE_PRESET)
    ledger = Ledger(args.root, purpose, fingerprint)
    data = ledger.load()
    manager = _manager_for(args)
    run = manager.detail(data["run_id"]) if data["run_id"] else None
    registry = data["holdout"]
    _print(
        {
            "purpose": purpose,
            "preset": FINETUNE_PRESET,
            "preset_fingerprint": fingerprint,
            "run": None if run is None else describe(args.root, run),
            "budget": {
                "max_seconds": preset.schedule.max_run_seconds,
                "used_seconds": None if run is None else round(run.used_seconds, 1),
                "remaining_seconds": None
                if run is None
                else round(preset.schedule.max_run_seconds - run.used_seconds, 1),
                "counted": purpose == "train",
            },
            "holdout": {
                "assigned": len(registry),
                "holdout": len(holdout_ids(registry)),
                "train": len(registry) - len(holdout_ids(registry)),
            },
            "iterations": data["iterations"],
        }
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="neural_grid_finetune")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("iterate", "status"):
        item = commands.add_parser(name)
        item.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="neural-grid-runs")
        item.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="777 v2")
        item.add_argument(
            "--init-root", type=Path, default=DEFAULT_ROOT, help="runs root holding run 1"
        )
        item.add_argument("--python", help="GPU interpreter for the worker")
        item.add_argument("--smoke", action="store_true", help="<= 50 steps, outside budget")
        if name == "iterate":
            item.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
            item.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
            item.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
            item.add_argument("--no-wait", action="store_true")
            item.add_argument("--allow-same-data", action="store_true")
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    {"iterate": command_iterate, "status": command_status}[args.command](args)


if __name__ == "__main__":
    main(sys.argv[1:])


__all__ = [
    "ITERATION_COMPLETE",
    "Ledger",
    "MixedBatchSampler",
    "assign_holdout",
    "guard_training_photos",
    "planned_train_seconds",
    "proposal_accuracy",
    "select_candidate",
    "train_iteration",
]
