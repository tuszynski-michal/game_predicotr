"""Checksum-bound ONNX export and CPU inference for geometry keypoints."""

from __future__ import annotations

import hashlib
import importlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

import numpy as np
import onnx
import onnxruntime as ort  # type: ignore[import-untyped]
import torch
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourcePoint,
    SourceQuad,
)
from numpy.typing import NDArray
from onnx import TensorProto
from torch import nn

from ..normalization import CanonicalSourceFrame
from .model import (
    DEFAULT_KEYPOINT_MODEL_CONFIGURATION,
    KEYPOINT_CORNER_COUNT,
    KEYPOINT_GEOMETRY_MODEL_VERSION,
    KEYPOINT_SLOT_COUNT,
    KeypointGeometryModelConfiguration,
    prepare_keypoint_model_input,
)

KEYPOINT_ONNX_ADAPTER_VERSION: Final = "keypoint-geometry-onnx-cpu-v1"
KEYPOINT_ONNX_OPSET_VERSION: Final = 18
KEYPOINT_ONNX_INPUT_NAME: Final = "images"
KEYPOINT_ONNX_HEATMAPS_NAME: Final = "corner_heatmaps"
KEYPOINT_ONNX_PRESENCE_NAME: Final = "slot_presence"
KEYPOINT_ONNX_MAX_PARITY_ERROR: Final = 1e-4


class KeypointOnnxError(ValueError):
    """Stable keypoint export, artifact, contract or inference failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _OnnxProgram(Protocol):
    model_proto: onnx.ModelProto


@dataclass(frozen=True, slots=True)
class KeypointOnnxArtifact:
    content: bytes
    checksum_sha256: str
    model_version: str
    adapter_version: str
    input_size: int
    heatmap_size: int


@dataclass(frozen=True, slots=True)
class KeypointOnnxOutputs:
    corner_heatmap_logits: NDArray[np.float32]
    slot_presence_logits: NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class KeypointSlotPrediction:
    position_index: int
    quad: SourceQuad | None
    presence_confidence: float
    corner_confidences: tuple[float, float, float, float]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KeypointGeometryPrediction:
    slots: tuple[KeypointSlotPrediction, ...]
    active_slot_mask: tuple[bool, ...]
    inactive_false_positive_count: int
    model_checksum_sha256: str

    @property
    def complete(self) -> bool:
        return all(slot.quad is not None and not slot.reason_codes for slot in self.slots)


@dataclass(frozen=True, slots=True)
class KeypointOnnxParityReport:
    maximum_absolute_error: float
    heatmap_argmax_equal: bool
    presence_mask_equal: bool


@dataclass(frozen=True, slots=True)
class KeypointCpuTiming:
    warmup_count: int
    measurement_count: int
    median_milliseconds: float
    p95_milliseconds: float


def export_keypoint_geometry_onnx(
    model: nn.Module,
    *,
    configuration: KeypointGeometryModelConfiguration = (DEFAULT_KEYPOINT_MODEL_CONFIGURATION),
) -> KeypointOnnxArtifact:
    model.eval()
    example = torch.zeros(
        (1, 3, configuration.input_size, configuration.input_size), dtype=torch.float32
    )
    try:
        onnx_export = cast(
            "Callable[..., _OnnxProgram | None]",
            vars(importlib.import_module("torch.onnx"))["export"],
        )
        dimension = cast(
            "Callable[..., object]",
            vars(importlib.import_module("torch.export"))["Dim"],
        )
        program = onnx_export(
            model,
            (example,),
            f=None,
            input_names=[KEYPOINT_ONNX_INPUT_NAME],
            output_names=[KEYPOINT_ONNX_HEATMAPS_NAME, KEYPOINT_ONNX_PRESENCE_NAME],
            dynamic_shapes=({0: dimension("batch", min=1)},),
            dynamo=True,
            opset_version=KEYPOINT_ONNX_OPSET_VERSION,
            optimize=True,
            report=False,
            verify=False,
            verbose=False,
        )
        if program is None:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_EXPORT_FAILED",
                "The PyTorch exporter did not return an ONNX program.",
            )
        exported = program.model_proto
    except (OSError, RuntimeError, ValueError, onnx.OnnxError) as error:
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_EXPORT_FAILED",
            "The keypoint checkpoint could not be exported to ONNX.",
        ) from error
    exported.producer_name = "game-predictor"
    exported.producer_version = KEYPOINT_GEOMETRY_MODEL_VERSION
    exported.domain = "local.game-predictor"
    exported.model_version = 1
    exported.doc_string = ""
    del exported.metadata_props[:]
    validate_keypoint_onnx_contract(exported, configuration=configuration)
    content = cast(bytes, exported.SerializeToString(deterministic=True))
    return KeypointOnnxArtifact(
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        model_version=KEYPOINT_GEOMETRY_MODEL_VERSION,
        adapter_version=KEYPOINT_ONNX_ADAPTER_VERSION,
        input_size=configuration.input_size,
        heatmap_size=configuration.heatmap_size,
    )


def validate_keypoint_onnx_contract(
    model: onnx.ModelProto,
    *,
    configuration: KeypointGeometryModelConfiguration,
) -> None:
    try:
        onnx.checker.check_model(model, full_check=True)
    except onnx.checker.ValidationError as error:
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_MODEL_INVALID",
            "The keypoint ONNX model failed structural validation.",
        ) from error
    if len(model.graph.input) != 1 or len(model.graph.output) != 2:
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_IO_CONTRACT_INVALID",
            "The keypoint model must expose one input and two outputs.",
        )
    model_input = model.graph.input[0]
    outputs = {output.name: output for output in model.graph.output}
    if (
        model_input.name != KEYPOINT_ONNX_INPUT_NAME
        or set(outputs) != {KEYPOINT_ONNX_HEATMAPS_NAME, KEYPOINT_ONNX_PRESENCE_NAME}
        or model_input.type.tensor_type.elem_type != TensorProto.FLOAT
        or any(
            output.type.tensor_type.elem_type != TensorProto.FLOAT for output in outputs.values()
        )
    ):
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_IO_CONTRACT_INVALID",
            "The keypoint ONNX names or data types are invalid.",
        )
    input_dimensions = _dimensions(model_input)
    heatmap_dimensions = _dimensions(outputs[KEYPOINT_ONNX_HEATMAPS_NAME])
    presence_dimensions = _dimensions(outputs[KEYPOINT_ONNX_PRESENCE_NAME])
    if input_dimensions != ("batch", 3, configuration.input_size, configuration.input_size):
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_INPUT_SHAPE_INVALID",
            "Expected dynamic-batch RGB input with a fixed keypoint input size.",
        )
    if heatmap_dimensions != (
        "batch",
        KEYPOINT_SLOT_COUNT,
        KEYPOINT_CORNER_COUNT,
        configuration.heatmap_size,
        configuration.heatmap_size,
    ):
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_HEATMAP_SHAPE_INVALID",
            "Expected 9 x 4 fixed-size corner heatmaps.",
        )
    if presence_dimensions != ("batch", KEYPOINT_SLOT_COUNT):
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_PRESENCE_SHAPE_INVALID",
            "Expected one presence logit for each of nine slots.",
        )
    opsets = {value.domain: int(value.version) for value in model.opset_import}
    if opsets.get("", 0) != KEYPOINT_ONNX_OPSET_VERSION:
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_OPSET_INVALID",
            "The keypoint ONNX model uses an unexpected default opset.",
        )


class LocalKeypointGeometryOnnxAdapter:
    """Narrow ONNX Runtime CPU adapter; it never selects a primary geometry."""

    def __init__(
        self,
        model_path: Path,
        *,
        expected_sha256: str,
        configuration: KeypointGeometryModelConfiguration = (DEFAULT_KEYPOINT_MODEL_CONFIGURATION),
        minimum_presence_confidence: float = 0.5,
        minimum_corner_confidence: float = 0.3,
    ) -> None:
        if not 0 < minimum_presence_confidence < 1 or not 0 < minimum_corner_confidence < 1:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_THRESHOLD_INVALID",
                "Keypoint confidence thresholds must be strictly between zero and one.",
            )
        try:
            content = model_path.read_bytes()
        except OSError as error:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_ARTIFACT_MISSING",
                "The keypoint ONNX artifact cannot be read.",
            ) from error
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_ARTIFACT_DRIFT",
                "The keypoint ONNX artifact differs from its expected checksum.",
            )
        try:
            model = onnx.load_model_from_string(content)
        except onnx.OnnxError as error:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_MODEL_INVALID",
                "The keypoint ONNX artifact cannot be decoded.",
            ) from error
        validate_keypoint_onnx_contract(model, configuration=configuration)
        if "CPUExecutionProvider" not in ort.get_available_providers():
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_CPU_PROVIDER_MISSING",
                "ONNX Runtime CPUExecutionProvider is unavailable.",
            )
        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        try:
            self._session = ort.InferenceSession(
                content,
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except (RuntimeError, ValueError) as error:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_SESSION_FAILED",
                "ONNX Runtime could not create the keypoint CPU session.",
            ) from error
        if self._session.get_providers() != ["CPUExecutionProvider"]:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_PROVIDER_INVALID",
                "Keypoint inference must use only CPUExecutionProvider.",
            )
        self.configuration = configuration
        self.artifact_sha256 = expected_sha256
        self.minimum_presence_confidence = minimum_presence_confidence
        self.minimum_corner_confidence = minimum_corner_confidence

    def infer_tensors(self, images: NDArray[np.float32]) -> KeypointOnnxOutputs:
        expected = (
            images.ndim == 4
            and images.dtype == np.float32
            and images.shape[0] >= 1
            and tuple(images.shape[1:])
            == (3, self.configuration.input_size, self.configuration.input_size)
        )
        if not expected or not np.isfinite(images).all():
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_INPUT_INVALID",
                "Keypoint input must be finite float32 NCHW with the configured size.",
            )
        try:
            raw_heatmaps, raw_presence = self._session.run(
                [KEYPOINT_ONNX_HEATMAPS_NAME, KEYPOINT_ONNX_PRESENCE_NAME],
                {KEYPOINT_ONNX_INPUT_NAME: np.ascontiguousarray(images)},
            )
        except (RuntimeError, ValueError) as error:
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_INFERENCE_FAILED",
                "ONNX Runtime keypoint inference failed.",
            ) from error
        heatmaps = np.asarray(raw_heatmaps, dtype=np.float32)
        presence = np.asarray(raw_presence, dtype=np.float32)
        if heatmaps.shape != (
            images.shape[0],
            KEYPOINT_SLOT_COUNT,
            KEYPOINT_CORNER_COUNT,
            self.configuration.heatmap_size,
            self.configuration.heatmap_size,
        ) or presence.shape != (images.shape[0], KEYPOINT_SLOT_COUNT):
            raise KeypointOnnxError(
                "KEYPOINT_ONNX_OUTPUT_INVALID",
                "ONNX Runtime returned invalid keypoint output shapes.",
            )
        return KeypointOnnxOutputs(
            corner_heatmap_logits=heatmaps,
            slot_presence_logits=presence,
        )

    def predict(
        self,
        source: CanonicalSourceFrame,
        *,
        active_board_slots: tuple[int, ...],
    ) -> KeypointGeometryPrediction:
        images = prepare_keypoint_model_input(
            source.rgb,
            input_size=self.configuration.input_size,
        )
        outputs = self.infer_tensors(images)
        return decode_keypoint_outputs(
            outputs,
            source_width=source.source.width,
            source_height=source.source.height,
            active_board_slots=active_board_slots,
            model_checksum_sha256=self.artifact_sha256,
            minimum_presence_confidence=self.minimum_presence_confidence,
            minimum_corner_confidence=self.minimum_corner_confidence,
        )


def decode_keypoint_outputs(
    outputs: KeypointOnnxOutputs,
    *,
    source_width: int,
    source_height: int,
    active_board_slots: tuple[int, ...],
    model_checksum_sha256: str,
    minimum_presence_confidence: float = 0.5,
    minimum_corner_confidence: float = 0.3,
) -> KeypointGeometryPrediction:
    if active_board_slots != tuple(range(len(active_board_slots))) or not (
        1 <= len(active_board_slots) <= KEYPOINT_SLOT_COUNT
    ):
        raise KeypointOnnxError(
            "KEYPOINT_ACTIVE_SLOT_MASK_INVALID",
            "Keypoint inference requires a non-empty attested active-slot prefix.",
        )
    heatmaps = outputs.corner_heatmap_logits
    presence_logits = outputs.slot_presence_logits
    if heatmaps.shape[0] != 1 or presence_logits.shape != (1, KEYPOINT_SLOT_COUNT):
        raise KeypointOnnxError(
            "KEYPOINT_ONNX_SINGLE_SOURCE_REQUIRED",
            "Geometry decoding accepts exactly one source image.",
        )
    presence = _sigmoid(presence_logits[0])
    active_mask = tuple(index in active_board_slots for index in range(KEYPOINT_SLOT_COUNT))
    false_positives = sum(
        1
        for index, is_active in enumerate(active_mask)
        if not is_active and float(presence[index]) >= minimum_presence_confidence
    )
    slots: list[KeypointSlotPrediction] = []
    heatmap_size = heatmaps.shape[-1]
    for slot in active_board_slots:
        reasons: list[str] = []
        presence_confidence = float(presence[slot])
        corner_confidences: list[float] = []
        corners: list[SourcePoint] = []
        if presence_confidence < minimum_presence_confidence:
            reasons.append("keypoint_active_slot_missing")
        for corner_index in range(KEYPOINT_CORNER_COUNT):
            probabilities = _sigmoid(heatmaps[0, slot, corner_index])
            y, x, confidence = _local_soft_argmax(probabilities)
            corner_confidences.append(confidence)
            if confidence < minimum_corner_confidence:
                reasons.append(f"keypoint_corner_{corner_index}_weak")
            corners.append(
                SourcePoint(
                    x=x / max(1, heatmap_size - 1) * max(1, source_width - 1),
                    y=y / max(1, heatmap_size - 1) * max(1, source_height - 1),
                )
            )
        quad: SourceQuad | None = None
        if not reasons:
            try:
                ordered_corners = cast(
                    tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                    tuple(corners),
                )
                quad = SourceQuad(corners=ordered_corners)
            except ImageGeometryContractError:
                reasons.append("keypoint_quad_invalid")
        slots.append(
            KeypointSlotPrediction(
                position_index=slot,
                quad=quad,
                presence_confidence=presence_confidence,
                corner_confidences=cast(
                    tuple[float, float, float, float], tuple(corner_confidences)
                ),
                reason_codes=tuple(reasons),
            )
        )
    return KeypointGeometryPrediction(
        slots=tuple(slots),
        active_slot_mask=active_mask,
        inactive_false_positive_count=false_positives,
        model_checksum_sha256=model_checksum_sha256,
    )


def validate_keypoint_onnx_parity(
    model: nn.Module,
    adapter: LocalKeypointGeometryOnnxAdapter,
    images: NDArray[np.float32],
) -> KeypointOnnxParityReport:
    model.eval()
    with torch.inference_mode():
        torch_heatmaps, torch_presence = model(torch.from_numpy(images))
    runtime = adapter.infer_tensors(images)
    heatmaps = torch_heatmaps.detach().cpu().numpy()
    presence = torch_presence.detach().cpu().numpy()
    maximum_error = max(
        float(np.max(np.abs(heatmaps - runtime.corner_heatmap_logits))),
        float(np.max(np.abs(presence - runtime.slot_presence_logits))),
    )
    return KeypointOnnxParityReport(
        maximum_absolute_error=maximum_error,
        heatmap_argmax_equal=bool(
            np.array_equal(
                heatmaps.reshape(*heatmaps.shape[:3], -1).argmax(axis=-1),
                runtime.corner_heatmap_logits.reshape(
                    *runtime.corner_heatmap_logits.shape[:3], -1
                ).argmax(axis=-1),
            )
        ),
        presence_mask_equal=bool(np.array_equal(presence >= 0, runtime.slot_presence_logits >= 0)),
    )


def measure_keypoint_onnx_cpu(
    adapter: LocalKeypointGeometryOnnxAdapter,
    images: NDArray[np.float32],
    *,
    warmup_count: int = 2,
    measurement_count: int = 5,
) -> KeypointCpuTiming:
    if warmup_count < 0 or measurement_count < 1 or measurement_count > 100:
        raise ValueError("Keypoint CPU timing counts are invalid.")
    for _ in range(warmup_count):
        adapter.infer_tensors(images)
    durations: list[float] = []
    for _ in range(measurement_count):
        started = time.perf_counter()
        adapter.infer_tensors(images)
        durations.append((time.perf_counter() - started) * 1000.0)
    return KeypointCpuTiming(
        warmup_count=warmup_count,
        measurement_count=measurement_count,
        median_milliseconds=float(np.median(durations)),
        p95_milliseconds=float(np.percentile(durations, 95)),
    )


def _dimensions(value: onnx.ValueInfoProto) -> tuple[int | str | None, ...]:
    result: list[int | str | None] = []
    for dimension in value.type.tensor_type.shape.dim:
        if dimension.HasField("dim_value"):
            result.append(int(dimension.dim_value))
        elif dimension.HasField("dim_param"):
            result.append(str(dimension.dim_param))
        else:
            result.append(None)
    return tuple(result)


def _sigmoid(values: NDArray[np.float32]) -> NDArray[np.float32]:
    clipped = np.clip(values, -30.0, 30.0)
    return np.asarray(1.0 / (1.0 + np.exp(-clipped)), dtype=np.float32)


def _local_soft_argmax(probabilities: NDArray[np.float32]) -> tuple[float, float, float]:
    peak_index = int(np.argmax(probabilities))
    peak_y = peak_index // probabilities.shape[1]
    peak_x = peak_index % probabilities.shape[1]
    y0, y1 = max(0, peak_y - 2), min(probabilities.shape[0], peak_y + 3)
    x0, x1 = max(0, peak_x - 2), min(probabilities.shape[1], peak_x + 3)
    window = probabilities[y0:y1, x0:x1].astype(np.float64)
    total = float(window.sum())
    if not math.isfinite(total) or total <= 0:
        return float(peak_y), float(peak_x), float(probabilities[peak_y, peak_x])
    ys, xs = np.mgrid[y0:y1, x0:x1]
    return (
        float((ys * window).sum() / total),
        float((xs * window).sum() / total),
        float(probabilities[peak_y, peak_x]),
    )


__all__ = [
    "KEYPOINT_ONNX_ADAPTER_VERSION",
    "KEYPOINT_ONNX_MAX_PARITY_ERROR",
    "KeypointCpuTiming",
    "KeypointGeometryPrediction",
    "KeypointOnnxArtifact",
    "KeypointOnnxError",
    "KeypointOnnxOutputs",
    "KeypointOnnxParityReport",
    "KeypointSlotPrediction",
    "LocalKeypointGeometryOnnxAdapter",
    "decode_keypoint_outputs",
    "export_keypoint_geometry_onnx",
    "measure_keypoint_onnx_cpu",
    "validate_keypoint_onnx_contract",
    "validate_keypoint_onnx_parity",
]
