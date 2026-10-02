"""TASK-0802 neural_grid protocol: frozen presets, role guard, run contract, D-481 budget.

Torch-free on purpose: the CLI, the run manager and the ONNX engine import this module
without importing training code. Everything a run is allowed to vary lives in one of the
three preset files in ``neural_grid_presets/``; their SHA-256 fingerprints are frozen
below, so editing a preset after the fact makes every run request with it invalid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Literal, Self

from pydantic import Field, model_validator

from .annotations import digest
from .contracts import Contract
from .run_contracts import RunState, StartRunRequest, TrainingConfiguration

MODEL_VERSION: Final = "neural-grid-v1"
PREPROCESSING_VERSION: Final = "neural-grid-screen768-board320x192-v1"
SNAPSHOT_POLICY: Final = "production-geometry-split-v2"
SNAPSHOT_FORMAT: Final = "production-geometry-snapshot-v1"
COORDINATE_SPACE: Final = "exif-normalized-rgb-pixels-v1"

# D-481: at most three training runs of at most four GPU hours each; smoke <= 50 steps.
MAX_TRAIN_RUNS: Final = 3
MAX_RUN_SECONDS: Final = 4 * 3600
SMOKE_MAX_STEPS: Final = 50
SMOKE_MAX_SECONDS: Final = 1800
SMOKE_ROUNDS: Final = 2
SMOKE_STEPS_PER_ROUND: Final = 20
SMOKE_EVAL_IMAGES: Final = 24

# Role guard: this task may read the training and development roles only.
ALLOWED_ROLES: Final = frozenset({"training", "development"})
FORBIDDEN_ROLES: Final = frozenset({"gold", "final_test", "unseen_game", "validation"})

PRESET_NAMES: Final = ("A", "B", "C")
# D-490 (TASK-0825): the third budget run is the iterative Mumie fine-tune of run 1.
FINETUNE_PRESET: Final = "D"
PRESET_DIRECTORY: Final = Path(__file__).with_name("neural_grid_presets")
# Frozen before run 1 (TASK-0802). A changed preset file no longer matches its entry.
# D was frozen before the first fine-tune iteration (TASK-0825).
FROZEN_PRESET_FINGERPRINTS: Final = {
    "A": "027b5db151b7094e06e69f6910d705a944312afe4341d37ebbc72c1782f0701d",
    "B": "658b3b529cb332016a15d953d7d2387d6adf35eeb9d5ad2b3660f341928b7da7",
    "C": "d54490696c341a18f7c0cf1c4ce0d2773ba935089de60de93ec46b4dd402b1e3",
    "D": "b94a9627df4c2d0886b43776f1a80b406de5d124c36c997ada2b5f93c5d1cbd9",
}

# Frozen metric definition (D-483), shared by evaluator, presets and the report.
METRIC_DEFINITION: Final[dict[str, Any]] = {
    "version": "neural-grid-metrics-v1",
    "matching": "hungarian-max-quad-iou; pairs below min IoU are not matched",
    "match_min_iou": 0.5,
    "quad": "corner nodes 0, 5, 23, 18 (TL, TR, BR, BL)",
    "normalization": "euclidean distance of label nodes 0 and 23 (TL-BR diagonal, as T05)",
    "board_correct_max_nme": 0.02,
    "board_correct_max_node_error": 0.05,
    "false_board": "prediction whose quad IoU with every label is below 0.5",
    "photo_complete_correct": "every label board matched and correct and no false board",
    "image_macro": "T05: per label min(1, NME), missing or invalid = 1, mean per photo, "
    "mean over photos",
    "selection": "max photo_complete_correct_rate on development; tie -> lower image_macro; "
    "tie -> earlier round",
}


class RoleForbiddenError(ValueError):
    """Raised before any sample of a forbidden role is decoded."""


def require_roles(roles: tuple[str, ...] | frozenset[str] | list[str]) -> frozenset[str]:
    requested = frozenset(roles)
    if not requested:
        raise RoleForbiddenError("NEURAL_GRID_ROLE_EMPTY")
    forbidden = sorted(requested - ALLOWED_ROLES)
    if forbidden:
        raise RoleForbiddenError(f"NEURAL_GRID_ROLE_FORBIDDEN:{','.join(forbidden)}")
    return requested


class AugmentationPreset(Contract):
    scale_range: tuple[float, float]
    rotation_degrees: float = Field(ge=0, le=30)
    perspective: float = Field(ge=0, le=0.2)
    translate: float = Field(ge=0, le=0.3)
    blur_probability: float = Field(ge=0, le=1)
    blur_max_sigma: float = Field(ge=0, le=5)
    noise_probability: float = Field(ge=0, le=1)
    noise_max_std: float = Field(ge=0, le=40)
    jpeg_probability: float = Field(ge=0, le=1)
    jpeg_quality_range: tuple[int, int]
    glare_probability: float = Field(ge=0, le=1)
    glare_max_count: int = Field(ge=0, le=6)
    glare_radius_range: tuple[float, float]
    glare_strength_range: tuple[float, float]
    occlusion_probability: float = Field(ge=0, le=1)
    occlusion_max_count: int = Field(ge=0, le=6)
    occlusion_size_range: tuple[float, float]
    hand_probability: float = Field(ge=0, le=1)
    hand_size_range: tuple[float, float]
    color_probability: float = Field(ge=0, le=1)
    brightness: float = Field(ge=0, le=0.6)
    contrast: float = Field(ge=0, le=0.6)
    saturation: float = Field(ge=0, le=0.8)
    hue_degrees: float = Field(ge=0, le=30)


class ScreenPreset(Contract):
    long_side: Literal[768] = 768
    train_canvas: tuple[int, int] = (768, 576)
    stride: Literal[4] = 4
    pad_multiple: Literal[32] = 32
    heat_sigma_fraction: float = Field(gt=0, le=0.5)
    min_heat_sigma: float = Field(gt=0, le=4)
    offset_scale: float = Field(gt=0)
    positive_radius: float = Field(gt=0, le=1)
    offset_loss_weight: float = Field(gt=0)
    decode_threshold: float = Field(gt=0, lt=1)
    nms_iou: float = Field(gt=0, lt=1)
    top_k: int = Field(ge=1, le=256)


class BoardPreset(Contract):
    canvas: tuple[int, int] = (320, 192)
    margin: float = Field(ge=0, le=0.5)
    stride: Literal[4] = 4
    corner_jitter: float = Field(ge=0, le=0.2)
    shift_jitter: float = Field(ge=0, le=0.2)
    scale_jitter: float = Field(ge=0, le=0.3)
    rotation_jitter_degrees: float = Field(ge=0, le=10)
    boards_per_image: int = Field(ge=1, le=16)
    coordinate_loss_weight: float = Field(gt=0)
    heatmap_loss_weight: float = Field(ge=0)
    heatmap_sigma: float = Field(gt=0)
    visibility_loss_weight: float = Field(ge=0)


class FitPreset(Contract):
    method: Literal["opencv-ransac-homography-then-least-squares-on-inliers"] = (
        "opencv-ransac-homography-then-least-squares-on-inliers"
    )
    inlier_threshold: float = Field(gt=0, le=0.2)
    min_inliers: int = Field(ge=4, le=24)


class OptimizationPreset(Contract):
    optimizer: Literal["AdamW"] = "AdamW"
    learning_rate: float = Field(gt=0, le=0.1)
    weight_decay: float = Field(ge=0, le=0.1)
    warmup_fraction: float = Field(ge=0, le=0.5)
    final_learning_rate_fraction: float = Field(gt=0, le=1)
    gradient_clip: float = Field(gt=0)
    batch_images: int = Field(ge=1, le=64)
    mixed_precision: Literal["float16-autocast-gradscaler"] = "float16-autocast-gradscaler"
    data_workers: int = Field(ge=0, le=12)


class SchedulePreset(Contract):
    rounds: int = Field(ge=1, le=64)
    round_seconds: float = Field(gt=0)
    minimum_round_seconds: float = Field(gt=0)
    final_reserve_seconds: float = Field(gt=0)
    max_run_seconds: Literal[14400] = 14400


PRETRAINED_NONE: Final = "none-imagenet-weights-not-available-offline"
PRETRAINED_RUN1: Final = "run1-43933ac8-best-round3-weights"


class FinetuneInit(Contract):
    """Pinned start weights of the fine-tune: the exported best state of run 1."""

    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    preset: Literal["A", "B", "C"]
    preset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    best_round: int = Field(ge=1)
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    export_directory: str
    weights_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    development_evaluation: str
    development_photos: int = Field(ge=1)
    development_photo_complete_correct_rate: float = Field(ge=0, le=1)
    development_image_macro: float = Field(ge=0, le=1)


class FinetunePreset(Contract):
    """Iteration settings of preset D (D-490 amendment of 2026-10-02, TASK-0825)."""

    version: Literal["neural-grid-finetune-v1"] = "neural-grid-finetune-v1"
    decision_reference: Literal["D-490"] = "D-490"
    game: Literal["mumie"] = "mumie"
    init: FinetuneInit
    mumie_images_per_batch: int = Field(ge=1, le=63)
    reference_sample: str
    holdout_every: int = Field(ge=2, le=20)
    holdout_key: str
    train_seconds_per_mumie_photo: float = Field(gt=0)
    iteration_train_seconds_min: float = Field(gt=0)
    iteration_train_seconds_max: float = Field(gt=0, le=3600)
    candidates_per_iteration: int = Field(ge=1, le=8)
    development_max_drop: float = Field(ge=0, le=0.05)
    holdout_min_photos: int = Field(ge=1)
    iteration_overhead_seconds: float = Field(gt=0)
    parity_images: int = Field(ge=1, le=64)
    proposal_threads: int = Field(ge=1, le=4)

    @model_validator(mode="after")
    def ordered_bounds(self) -> Self:
        if self.iteration_train_seconds_min > self.iteration_train_seconds_max:
            raise ValueError("NEURAL_GRID_FINETUNE_BOUNDS_INVALID")
        return self


class Preset(Contract):
    version: Literal["neural-grid-preset-v1"] = "neural-grid-preset-v1"
    name: Literal["A", "B", "C", "D"]
    hypothesis: str
    model_version: Literal["neural-grid-v1"] = "neural-grid-v1"
    preprocessing_version: Literal["neural-grid-screen768-board320x192-v1"] = (
        "neural-grid-screen768-board320x192-v1"
    )
    seed: int = Field(ge=0, le=2147483647)
    backbone: Literal["torchvision-mobilenet_v3_large-features-fpn-stride4"] = (
        "torchvision-mobilenet_v3_large-features-fpn-stride4"
    )
    pretrained: Literal[
        "none-imagenet-weights-not-available-offline", "run1-43933ac8-best-round3-weights"
    ] = "none-imagenet-weights-not-available-offline"
    snapshot_policy: Literal["production-geometry-split-v2"] = "production-geometry-split-v2"
    screen: ScreenPreset
    board: BoardPreset
    fit: FitPreset
    augmentation: AugmentationPreset
    optimization: OptimizationPreset
    schedule: SchedulePreset
    metrics: dict[str, Any]
    # Only the fine-tune preset D has this section; A/B/C files do not carry it.
    finetune: FinetunePreset | None = None

    @model_validator(mode="after")
    def frozen_metrics(self) -> Self:
        if self.metrics != METRIC_DEFINITION:
            raise ValueError("NEURAL_GRID_METRIC_DEFINITION_MISMATCH")
        finetune = self.name == FINETUNE_PRESET
        if finetune != (self.finetune is not None) or finetune != (
            self.pretrained == PRETRAINED_RUN1
        ):
            raise ValueError("NEURAL_GRID_FINETUNE_PRESET_INVALID")
        return self


def preset_path(name: str) -> Path:
    if name not in PRESET_NAMES and name != FINETUNE_PRESET:
        raise ValueError("NEURAL_GRID_PRESET_UNKNOWN")
    return PRESET_DIRECTORY / f"{name}.json"


def preset_fingerprint(payload: dict[str, Any]) -> str:
    return digest(payload)


def load_preset(name: str, *, frozen: dict[str, str] | None = None) -> tuple[Preset, str]:
    """Return the validated preset and its fingerprint; refuse any drift from the freeze."""

    payload = json.loads(preset_path(name).read_text(encoding="utf-8"))
    preset = Preset.model_validate(payload)
    if preset.name != name:
        raise ValueError("NEURAL_GRID_PRESET_NAME_MISMATCH")
    fingerprint = preset_fingerprint(payload)
    expected = (FROZEN_PRESET_FINGERPRINTS if frozen is None else frozen).get(name)
    if fingerprint != expected:
        raise ValueError("NEURAL_GRID_PRESET_FINGERPRINT_MISMATCH")
    return preset, fingerprint


class NeuralGridConfiguration(TrainingConfiguration):
    """Rounds instead of epochs: a round is a fixed slice of training time plus evaluation."""

    epochs: int = Field(ge=1, le=64)
    batch_size: int = Field(ge=1, le=64)
    learning_rate: float = Field(gt=0, le=0.1)
    max_steps: int = Field(ge=1, le=10_000_000)
    max_seconds: float = Field(ge=1, le=MAX_RUN_SECONDS)


def finetune_settings(preset: Preset) -> FinetunePreset:
    if preset.name != FINETUNE_PRESET or preset.finetune is None:
        raise ValueError("NEURAL_GRID_FINETUNE_PRESET_REQUIRED")
    return preset.finetune


class NeuralGridRunRequest(StartRunRequest):
    configuration: NeuralGridConfiguration
    preset: Literal["A", "B", "C", "D"]
    preset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def neural_grid_limits(self) -> Self:
        if self.model_version != MODEL_VERSION:
            raise ValueError("RUN_MODEL_NOT_AVAILABLE")
        if self.preprocessing_version != PREPROCESSING_VERSION:
            raise ValueError("NEURAL_GRID_PREPROCESSING_MISMATCH")
        if self.protocol_digest is not None:
            raise ValueError("NEURAL_GRID_PROTOCOL_DIGEST_UNUSED")
        if self.topology.columns != 5:
            raise ValueError("NEURAL_GRID_TOPOLOGY_UNSUPPORTED")
        if self.purpose == "smoke" and (
            self.configuration.max_steps > SMOKE_MAX_STEPS
            or self.configuration.max_seconds > SMOKE_MAX_SECONDS
            or self.configuration.epochs != SMOKE_ROUNDS
        ):
            raise ValueError("SMOKE_STEP_LIMIT")
        return self


class NeuralGridRunState(RunState):
    request: NeuralGridRunRequest


def build_request(
    *, request_id: str, preset_name: str, purpose: Literal["smoke", "train"], snapshot_id: str
) -> NeuralGridRunRequest:
    preset, fingerprint = load_preset(preset_name)
    if purpose == "smoke":
        configuration = NeuralGridConfiguration(
            epochs=SMOKE_ROUNDS,
            batch_size=preset.optimization.batch_images,
            learning_rate=preset.optimization.learning_rate,
            max_steps=SMOKE_MAX_STEPS,
            max_seconds=SMOKE_MAX_SECONDS,
        )
    else:
        configuration = NeuralGridConfiguration(
            epochs=preset.schedule.rounds,
            batch_size=preset.optimization.batch_images,
            learning_rate=preset.optimization.learning_rate,
            max_steps=10_000_000,
            max_seconds=preset.schedule.max_run_seconds,
        )
    return NeuralGridRunRequest(
        request_id=request_id,
        manifest_id=snapshot_id,
        model_version=MODEL_VERSION,
        preprocessing_version=PREPROCESSING_VERSION,
        seed=preset.seed,
        purpose=purpose,
        configuration=configuration,
        preset=preset.name,
        preset_fingerprint=fingerprint,
    )


def validate_request(request: StartRunRequest) -> Preset:
    """Re-validated at create, claim, every checkpoint and finish (RunManager.validate)."""

    if not isinstance(request, NeuralGridRunRequest):
        request = NeuralGridRunRequest.model_validate(request.model_dump())
    preset, fingerprint = load_preset(request.preset)
    configuration = request.configuration
    if (
        request.preset_fingerprint != fingerprint
        or request.seed != preset.seed
        or configuration.batch_size != preset.optimization.batch_images
        or configuration.learning_rate != preset.optimization.learning_rate
        or (request.purpose == "train" and configuration.epochs != preset.schedule.rounds)
        or (request.purpose == "train" and configuration.max_seconds != MAX_RUN_SECONDS)
    ):
        raise ValueError("NEURAL_GRID_PRESET_REQUEST_MISMATCH")
    return preset


def admit_run(data: dict[str, Any], request: StartRunRequest) -> None:
    """D-481 durable budget, evaluated under the run lock against every recorded run.

    Every started training run counts, whatever its final status (interrupted, failed or
    cancelled runs do not return budget); resuming a run is a new attempt of the same run
    and is not admitted here. Smoke runs do not count. One training run per preset. The
    iterative fine-tune (preset D) is one run: each iteration is a new attempt of it, so
    its iterations share the run's durable ``used_seconds`` and 4-hour limit.
    """

    if request.purpose != "train":
        return
    trained = [
        value["request"]
        for value in data["runs"].values()
        if value["request"].get("purpose") == "train"
        and value["request"].get("model_version") == MODEL_VERSION
    ]
    if len(trained) >= MAX_TRAIN_RUNS:
        raise ValueError("NEURAL_GRID_RUN_BUDGET_EXHAUSTED")
    preset = getattr(request, "preset", None)
    if any(item.get("preset") == preset for item in trained):
        raise ValueError("NEURAL_GRID_PRESET_ALREADY_RUN")
