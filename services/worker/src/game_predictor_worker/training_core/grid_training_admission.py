"""Versioned grid-training presets, cohort cost, runtime facts and run admission (TASK-1005).

Neutral core: no application, database or laboratory imports. ``torch`` is imported lazily
by :func:`probe_runtime` only, so the API can read presets and estimate cost without it.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

PRESET_POLICY = "grid-training-preset-v1"
ADMISSION_POLICY = "grid-training-admission-v1"
BUDGET_FORMAT = "grid-training-budget-v1"

Mode = Literal["grid-only", "screen+grid"]
Purpose = Literal["train", "smoke"]
LeaseState = Literal["free", "held", "stale", "unknown"]

# A smoke run ends after 50 steps or 120 seconds of training counted from the first step,
# whichever comes first. Start-up (data checks, loader workers) has its own 300 s limit and
# the whole charged run at most 600 s (operator decision 2026-10-16 after the first smoke).
SMOKE_MAX_STEPS = 50
SMOKE_TRAIN_SECONDS = 120.0
SMOKE_STARTUP_SECONDS = 300.0
SMOKE_MAX_SECONDS = 600.0

# Fixed order of every blocking reason; a decision lists all that apply.
REASONS = (
    "GRID_RUN_PRESET_NOT_APPROVED",
    "GRID_RUN_COHORT_MODE_MISMATCH",
    "GRID_RUN_COHORT_EMPTY",
    "GRID_RUN_COHORT_COST_EXCEEDS_BUDGET",
    "GRID_RUN_GPU_UNAVAILABLE",
    "GRID_RUN_RUNTIME_INCOMPATIBLE",
    "GRID_RUN_VRAM_INSUFFICIENT",
    "GRID_RUN_LEASE_BUSY",
    "GRID_RUN_LEASE_UNKNOWN",
    "GRID_RUN_BUDGET_PRESET_MISMATCH",
    "GRID_RUN_BUDGET_EXHAUSTED",
)
WORKER_CHECKS = (
    "GPU_AVAILABLE",
    "RUNTIME_COMPATIBLE",
    "VRAM_SUFFICIENT",
    "GPU_LEASE_FREE",
    "BUDGET_AVAILABLE",
)


class GridRunBudgetError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RuntimeRequirement:
    torch: str
    torchvision: str
    cuda: str


REQUIRED_RUNTIME = RuntimeRequirement(torch="2.12.1+cu130", torchvision="0.27.1+cu130", cuda="13.0")


@dataclass(frozen=True)
class EarlyStopping:
    """Stop after ``patience`` consecutive VALIDATION evaluations without an improvement
    larger than ``min_delta``, never before ``min_evaluations``. REGRESSION is never read."""

    metric: str
    direction: Literal["maximize", "minimize"]
    evaluation_interval_seconds: float
    patience: int
    min_delta: float
    min_evaluations: int


@dataclass(frozen=True)
class GridTrainingPreset:
    preset_id: str
    version: int
    mode: Mode
    batch_items: int
    boards_per_item: int
    data_workers: int
    learning_rate: float
    warmup_fraction: float
    final_learning_rate_fraction: float
    weight_decay: float
    gradient_clip: float
    frozen_modules: tuple[str, ...]
    train_seconds_per_train_photo: float
    min_train_seconds: float
    max_train_seconds: float
    max_steps: int
    max_run_seconds: float
    startup_estimate_seconds: float
    evaluation_estimate_seconds: float
    checkpoint_estimate_seconds: float
    final_reserve_seconds: float
    steps_per_second_estimate: float
    min_total_vram_bytes: int
    min_free_vram_bytes: int
    early_stopping: EarlyStopping
    runtime: RuntimeRequirement = REQUIRED_RUNTIME
    approved: bool = False
    approval_basis: str = ""
    policy: str = field(default=PRESET_POLICY)

    def parameters(self) -> dict[str, Any]:
        """Everything the fingerprint covers: training parameters, not the approval record."""
        value = asdict(self)
        value.pop("approved")
        value.pop("approval_basis")
        value["frozen_modules"] = list(self.frozen_modules)
        return value

    @property
    def fingerprint(self) -> str:
        return digest(self.parameters())


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


# Throughput and memory of the full preset-D step on the RTX 4050 Laptop GPU (6 GB): reports
# GRID_V3_NEURAL_GRID_RUNS_20261002 (2.1-2.46 steps/s, 5.08-5.85 GB) and the Mumie iterations
# 4-5 (2.13 and 2.03 steps/s). The TASK-1005 smoke result is recorded in its Outcome.
_STEPS_PER_SECOND = 2.0
_MAX_STEPS = 4000  # 1800 s x 2.0 steps/s plus margin; the time limit normally ends first
_MIN_TOTAL_VRAM = 6_000_000_000
_MIN_FREE_VRAM = 5_000_000_000
_BASIS = (
    "TASK-1005: preset-D throughput/VRAM from GRID_V3_NEURAL_GRID_RUNS_20261002 and "
    "MUMIE_CURRENT_APPROVALS_20261005, bounded smoke in the TASK-1005 Outcome"
)
_VALIDATION = {
    "grid-only": "validation.board_correct_rate",
    "screen+grid": "validation.photo_complete_correct_rate",
}


def _preset(
    preset_id: str, mode: Mode, batch_items: int, boards: int, frozen: tuple[str, ...]
) -> GridTrainingPreset:
    return GridTrainingPreset(
        preset_id=preset_id,
        version=1,
        mode=mode,
        batch_items=batch_items,
        boards_per_item=boards,
        data_workers=6,
        frozen_modules=frozen,
        max_steps=_MAX_STEPS,
        steps_per_second_estimate=_STEPS_PER_SECOND,
        min_total_vram_bytes=_MIN_TOTAL_VRAM,
        min_free_vram_bytes=_MIN_FREE_VRAM,
        early_stopping=EarlyStopping(
            metric=_VALIDATION[mode],
            direction="maximize",
            evaluation_interval_seconds=300.0,
            patience=2,
            min_delta=0.0,
            min_evaluations=2,
        ),
        approved=True,
        approval_basis=_BASIS,
        # Optimisation of preset D (lab fine-tune of the run-1 state).
        learning_rate=1e-4,
        warmup_fraction=0.05,
        final_learning_rate_fraction=0.1,
        weight_decay=1e-4,
        gradient_clip=5.0,
        # 60 s per TRAIN photo as in preset D, clamped to 300-1800 s of training; the run
        # limit adds start-up, evaluations with checkpoints and the final reserve.
        train_seconds_per_train_photo=60.0,
        min_train_seconds=300.0,
        max_train_seconds=1800.0,
        max_run_seconds=3600.0,
        startup_estimate_seconds=180.0,
        evaluation_estimate_seconds=60.0,
        checkpoint_estimate_seconds=30.0,
        final_reserve_seconds=60.0,
    )


GRID_ONLY_V1 = _preset("grid-only-v1", "grid-only", 48, 1, ("detector", "batchnorm"))
SCREEN_GRID_V1 = _preset("screen-grid-v1", "screen+grid", 12, 4, ())
PRESETS: Mapping[str, GridTrainingPreset] = {
    GRID_ONLY_V1.preset_id: GRID_ONLY_V1,
    SCREEN_GRID_V1.preset_id: SCREEN_GRID_V1,
}


def preset_for_mode(
    mode: str, presets: Mapping[str, GridTrainingPreset] = PRESETS
) -> GridTrainingPreset | None:
    """The approved preset of a cohort mode, or None."""
    matching = [p for p in presets.values() if p.mode == mode and p.approved]
    return max(matching, key=lambda p: p.version) if matching else None


@dataclass(frozen=True)
class CohortCounts:
    """Frozen-cohort counts per role (DB summary or manifest ``counts``)."""

    mode: str
    train_boards: int
    train_photos: int
    train_full_photos: int
    validation_boards: int = 0
    validation_photos: int = 0
    regression_boards: int = 0
    regression_photos: int = 0


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


def summed_counts(headers: Sequence[Mapping[str, Any]]) -> CohortCounts:
    """Shared runs are admitted and costed on the counts of all their cohorts."""
    parts = [counts_from_header(header) for header in headers]
    return CohortCounts(
        mode=parts[0].mode,
        **{
            name: sum(getattr(part, name) for part in parts)
            for name in (
                "train_boards",
                "train_photos",
                "train_full_photos",
                "validation_boards",
                "validation_photos",
                "regression_boards",
                "regression_photos",
            )
        },
    )


@dataclass(frozen=True)
class CohortCost:
    train_items: int
    steps_per_epoch: int
    planned_train_seconds: float
    planned_steps: int
    epochs_planned: float
    evaluations_planned: int
    estimated_run_seconds: float
    within_budget: bool


def estimate_cohort_cost(preset: GridTrainingPreset, counts: CohortCounts) -> CohortCost:
    """Deterministic cost of one run: grid-only trains boards, screen+grid trains full photos."""
    items = counts.train_boards if preset.mode == "grid-only" else counts.train_full_photos
    steps_per_epoch = math.ceil(items / preset.batch_items) if items > 0 else 0
    planned = min(
        preset.max_train_seconds,
        max(preset.min_train_seconds, preset.train_seconds_per_train_photo * counts.train_photos),
    )
    steps = min(preset.max_steps, math.floor(planned * preset.steps_per_second_estimate))
    evaluations = math.ceil(planned / preset.early_stopping.evaluation_interval_seconds)
    total = (
        preset.startup_estimate_seconds
        + planned
        + evaluations * (preset.evaluation_estimate_seconds + preset.checkpoint_estimate_seconds)
        + preset.final_reserve_seconds
    )
    return CohortCost(
        train_items=items,
        steps_per_epoch=steps_per_epoch,
        planned_train_seconds=planned,
        planned_steps=steps if items > 0 else 0,
        epochs_planned=round(steps / steps_per_epoch, 3) if steps_per_epoch else 0.0,
        evaluations_planned=evaluations,
        estimated_run_seconds=total,
        within_budget=total <= preset.max_run_seconds,
    )


@dataclass(frozen=True)
class RuntimeFacts:
    cuda_available: bool
    torch_version: str | None = None
    torchvision_version: str | None = None
    cuda_version: str | None = None
    device_name: str | None = None
    total_vram_bytes: int | None = None
    free_vram_bytes: int | None = None
    probe_error: str | None = None


def probe_runtime(device_index: int = 0) -> RuntimeFacts:
    """Read the local torch/CUDA facts; a failed probe is reported, never treated as a GPU."""
    try:
        import torch
    except Exception as error:  # noqa: BLE001 - an unusable runtime is a fact, not a crash
        return RuntimeFacts(cuda_available=False, probe_error=f"torch: {type(error).__name__}")
    torchvision_version: str | None
    try:
        import torchvision  # type: ignore[import-untyped]

        torchvision_version = str(torchvision.__version__)
    except Exception:  # noqa: BLE001
        torchvision_version = None
    facts = RuntimeFacts(
        cuda_available=False,
        torch_version=str(torch.__version__),
        torchvision_version=torchvision_version,
        cuda_version=torch.version.cuda,
    )
    try:
        if not torch.cuda.is_available():
            return facts
        free, total = torch.cuda.mem_get_info(device_index)
        return replace(
            facts,
            cuda_available=True,
            device_name=str(torch.cuda.get_device_name(device_index)),
            total_vram_bytes=int(total),
            free_vram_bytes=int(free),
        )
    except Exception as error:  # noqa: BLE001
        return replace(facts, cuda_available=False, probe_error=f"cuda: {type(error).__name__}")


@dataclass(frozen=True)
class RunBudget:
    """Durable run budget; resuming never renews steps or seconds."""

    preset_id: str
    preset_fingerprint: str
    purpose: Purpose
    max_steps: int
    max_seconds: float
    reserved_steps: int = 0
    used_seconds: float = 0.0
    attempts: int = 0

    @classmethod
    def for_preset(cls, preset: GridTrainingPreset, purpose: Purpose) -> RunBudget:
        if purpose == "smoke":
            steps, seconds = SMOKE_MAX_STEPS, SMOKE_MAX_SECONDS
        else:
            steps, seconds = preset.max_steps, preset.max_run_seconds
        return cls(preset.preset_id, preset.fingerprint, purpose, steps, seconds)

    @property
    def remaining_steps(self) -> int:
        return max(0, self.max_steps - self.reserved_steps)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - self.used_seconds)

    @property
    def exhausted(self) -> bool:
        return self.remaining_steps == 0 or self.remaining_seconds <= 0.0

    def start_attempt(self) -> RunBudget:
        if self.exhausted:
            raise GridRunBudgetError("GRID_RUN_BUDGET_EXHAUSTED")
        return replace(self, attempts=self.attempts + 1)

    def reserve_step(self) -> RunBudget:
        if self.exhausted:
            raise GridRunBudgetError("GRID_RUN_BUDGET_EXHAUSTED")
        return replace(self, reserved_steps=self.reserved_steps + 1)

    def charge(self, seconds: float) -> RunBudget:
        """Add elapsed seconds; a negative or non-finite value (clock moved back) exhausts."""
        if not math.isfinite(seconds) or seconds < 0:
            return replace(self, used_seconds=self.max_seconds)
        return replace(self, used_seconds=min(self.max_seconds, self.used_seconds + seconds))

    def to_payload(self) -> dict[str, Any]:
        body = {"format": BUDGET_FORMAT, **asdict(self)}
        return {"payload": body, "sha256": digest(body)}

    @classmethod
    def from_payload(cls, envelope: Mapping[str, Any]) -> RunBudget:
        body = envelope.get("payload")
        if not isinstance(body, dict) or envelope.get("sha256") != digest(body):
            raise GridRunBudgetError("GRID_RUN_BUDGET_CORRUPT")
        if body.get("format") != BUDGET_FORMAT:
            raise GridRunBudgetError("GRID_RUN_BUDGET_CORRUPT")
        values = {k: v for k, v in body.items() if k != "format"}
        try:
            budget = cls(**values)
        except TypeError as error:
            raise GridRunBudgetError("GRID_RUN_BUDGET_CORRUPT") from error
        if (
            budget.purpose not in ("train", "smoke")
            or budget.reserved_steps < 0
            or budget.used_seconds < 0
        ):
            raise GridRunBudgetError("GRID_RUN_BUDGET_CORRUPT")
        return budget


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reasons: tuple[str, ...]
    purpose: Purpose
    preset_id: str
    preset_fingerprint: str
    budget: RunBudget | None
    cost: CohortCost | None
    policy: str = ADMISSION_POLICY


def evaluate_admission(
    *,
    preset_id: str,
    preset_fingerprint: str,
    purpose: Purpose,
    runtime: RuntimeFacts | None,
    lease_state: LeaseState,
    counts: CohortCounts | None = None,
    stored_budget: RunBudget | None = None,
    presets: Mapping[str, GridTrainingPreset] = PRESETS,
) -> AdmissionDecision:
    """Pure admission of one new or resumed run. Missing facts block; nothing is assumed."""
    found: set[str] = set()
    preset = presets.get(preset_id)
    unknown = preset is None or preset.fingerprint != preset_fingerprint
    if unknown or (purpose == "train" and preset is not None and not preset.approved):
        found.add("GRID_RUN_PRESET_NOT_APPROVED")
    cost = None
    if purpose == "train":
        if counts is None:
            found.add("GRID_RUN_COHORT_EMPTY")
        elif preset is not None:
            if counts.mode != preset.mode:
                found.add("GRID_RUN_COHORT_MODE_MISMATCH")
            cost = estimate_cohort_cost(preset, counts)
            if cost.train_items == 0:
                found.add("GRID_RUN_COHORT_EMPTY")
            if not cost.within_budget:
                found.add("GRID_RUN_COHORT_COST_EXCEEDS_BUDGET")
    if runtime is None or not runtime.cuda_available:
        found.add("GRID_RUN_GPU_UNAVAILABLE")
    else:
        required = preset.runtime if preset is not None else REQUIRED_RUNTIME
        if (runtime.torch_version, runtime.torchvision_version, runtime.cuda_version) != (
            required.torch,
            required.torchvision,
            required.cuda,
        ):
            found.add("GRID_RUN_RUNTIME_INCOMPATIBLE")
        if preset is not None and (
            runtime.total_vram_bytes is None
            or runtime.free_vram_bytes is None
            or runtime.total_vram_bytes < preset.min_total_vram_bytes
            or runtime.free_vram_bytes < preset.min_free_vram_bytes
        ):
            found.add("GRID_RUN_VRAM_INSUFFICIENT")
    if lease_state == "held":
        found.add("GRID_RUN_LEASE_BUSY")
    elif lease_state not in ("free", "stale"):
        found.add("GRID_RUN_LEASE_UNKNOWN")
    budget = None
    if preset is not None:
        if stored_budget is None:
            budget = RunBudget.for_preset(preset, purpose)
        elif (
            stored_budget.preset_id != preset.preset_id
            or stored_budget.preset_fingerprint != preset.fingerprint
            or stored_budget.purpose != purpose
        ):
            found.add("GRID_RUN_BUDGET_PRESET_MISMATCH")
        else:
            budget = stored_budget
        if budget is not None and budget.exhausted:
            found.add("GRID_RUN_BUDGET_EXHAUSTED")
    reasons = tuple(code for code in REASONS if code in found)
    admitted = not reasons
    return AdmissionDecision(
        admitted=admitted,
        reasons=reasons,
        purpose=purpose,
        preset_id=preset_id,
        preset_fingerprint=preset_fingerprint,
        budget=budget.start_attempt() if admitted and budget is not None else budget,
        cost=cost,
    )


def preset_view(preset: GridTrainingPreset) -> dict[str, Any]:
    """JSON view for previews; field names follow the API casing."""
    stopping = preset.early_stopping
    return {
        "presetId": preset.preset_id,
        "version": preset.version,
        "policy": preset.policy,
        "fingerprint": preset.fingerprint,
        "mode": preset.mode,
        "approved": preset.approved,
        "approvalBasis": preset.approval_basis,
        "batchItems": preset.batch_items,
        "boardsPerItem": preset.boards_per_item,
        "frozenModules": list(preset.frozen_modules),
        "learningRate": preset.learning_rate,
        "trainSecondsPerTrainPhoto": preset.train_seconds_per_train_photo,
        "minTrainSeconds": preset.min_train_seconds,
        "maxTrainSeconds": preset.max_train_seconds,
        "maxSteps": preset.max_steps,
        "maxRunSeconds": preset.max_run_seconds,
        "stepsPerSecondEstimate": preset.steps_per_second_estimate,
        "minTotalVramBytes": preset.min_total_vram_bytes,
        "minFreeVramBytes": preset.min_free_vram_bytes,
        "earlyStopping": {
            "metric": stopping.metric,
            "direction": stopping.direction,
            "evaluationIntervalSeconds": stopping.evaluation_interval_seconds,
            "patience": stopping.patience,
            "minDelta": stopping.min_delta,
            "minEvaluations": stopping.min_evaluations,
        },
        "runtime": {
            "torch": preset.runtime.torch,
            "torchvision": preset.runtime.torchvision,
            "cuda": preset.runtime.cuda,
        },
    }


def cost_view(cost: CohortCost) -> dict[str, Any]:
    return {
        "trainItems": cost.train_items,
        "stepsPerEpoch": cost.steps_per_epoch,
        "plannedTrainSeconds": cost.planned_train_seconds,
        "plannedSteps": cost.planned_steps,
        "epochsPlanned": cost.epochs_planned,
        "evaluationsPlanned": cost.evaluations_planned,
        "estimatedRunSeconds": cost.estimated_run_seconds,
        "withinBudget": cost.within_budget,
    }
