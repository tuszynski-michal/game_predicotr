"""Versioned ONNX export and fail-closed local CPU inference for M6 symbols."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import cv2
import numpy as np
import onnx
import onnxruntime as ort  # type: ignore[import-untyped]
import torch
from numpy.typing import NDArray
from onnx import TensorProto
from torch import Tensor, nn

ONNX_MODEL_VERSION = "bootstrap-symbol-cnn-onnx-v1"
ONNX_ADAPTER_VERSION = "local-symbol-onnx-runtime-v1"
ONNX_OPSET_VERSION = 18
ONNX_INPUT_NAME = "images"
ONNX_OUTPUT_NAME = "logits"
MAX_PARITY_ABSOLUTE_ERROR = 1e-5


class SymbolOnnxError(ValueError):
    """Stable ONNX export, contract or inference failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _OnnxProgram(Protocol):
    model_proto: onnx.ModelProto


@dataclass(frozen=True, slots=True)
class OnnxInference:
    logits: NDArray[np.float32]
    probabilities: NDArray[np.float32]
    class_indexes: NDArray[np.int64]


def _dimension_value(dimension: onnx.TensorShapeProto.Dimension) -> int | str | None:
    if dimension.HasField("dim_value"):
        return int(dimension.dim_value)
    if dimension.HasField("dim_param"):
        return str(dimension.dim_param)
    return None


def validate_onnx_contract(
    model: onnx.ModelProto,
    *,
    input_size: int,
    class_count: int,
) -> None:
    """Validate the exact fixed-image/dynamic-batch model boundary."""

    try:
        onnx.checker.check_model(model, full_check=True)
    except onnx.checker.ValidationError as error:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_MODEL_INVALID",
            "The ONNX model failed structural validation.",
        ) from error
    if len(model.graph.input) != 1 or len(model.graph.output) != 1:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_IO_CONTRACT_INVALID",
            "The ONNX model must expose exactly one input and one output.",
        )
    model_input = model.graph.input[0]
    model_output = model.graph.output[0]
    if (
        model_input.name != ONNX_INPUT_NAME
        or model_output.name != ONNX_OUTPUT_NAME
        or model_input.type.tensor_type.elem_type != TensorProto.FLOAT
        or model_output.type.tensor_type.elem_type != TensorProto.FLOAT
    ):
        raise SymbolOnnxError(
            "SYMBOL_ONNX_IO_CONTRACT_INVALID",
            "The ONNX input/output names or data types are invalid.",
        )
    input_dimensions = tuple(
        _dimension_value(value) for value in model_input.type.tensor_type.shape.dim
    )
    output_dimensions = tuple(
        _dimension_value(value) for value in model_output.type.tensor_type.shape.dim
    )
    if input_dimensions != ("batch", 3, input_size, input_size):
        raise SymbolOnnxError(
            "SYMBOL_ONNX_INPUT_SHAPE_INVALID",
            "Expected dynamic batch and fixed N x 3 x input_size x input_size input.",
        )
    if output_dimensions != ("batch", class_count):
        raise SymbolOnnxError(
            "SYMBOL_ONNX_OUTPUT_SHAPE_INVALID",
            "Expected dynamic batch and fixed N x class_count logits output.",
        )
    opsets = {value.domain: int(value.version) for value in model.opset_import}
    if opsets.get("", 0) != ONNX_OPSET_VERSION:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_OPSET_INVALID",
            "The ONNX model uses an unexpected default opset.",
        )


def export_symbol_classifier_onnx(
    model: nn.Module,
    *,
    input_size: int,
    class_count: int,
    model_version: str = ONNX_MODEL_VERSION,
) -> bytes:
    """Export deterministic ONNX bytes without changing the source checkpoint."""

    model.eval()
    example = torch.zeros((1, 3, input_size, input_size), dtype=torch.float32)
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
            input_names=[ONNX_INPUT_NAME],
            output_names=[ONNX_OUTPUT_NAME],
            dynamic_shapes=({0: dimension("batch", min=1)},),
            dynamo=True,
            opset_version=ONNX_OPSET_VERSION,
            optimize=True,
            report=False,
            verify=False,
            verbose=False,
        )
        if program is None:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_EXPORT_FAILED",
                "The current PyTorch exporter did not return an ONNX program.",
            )
        exported = program.model_proto
    except (OSError, RuntimeError, ValueError, onnx.OnnxError) as error:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_EXPORT_FAILED",
            "The PyTorch checkpoint could not be exported to ONNX.",
        ) from error
    exported.producer_name = "game-predictor"
    if not model_version:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_MODEL_VERSION_INVALID",
            "The ONNX model version must be explicit.",
        )
    exported.producer_version = model_version
    exported.domain = "local.game-predictor"
    exported.model_version = 1
    exported.doc_string = ""
    del exported.metadata_props[:]
    validate_onnx_contract(
        exported,
        input_size=input_size,
        class_count=class_count,
    )
    return cast(bytes, exported.SerializeToString(deterministic=True))


class LocalSymbolOnnxAdapter:
    """Checksum-bound ONNX Runtime CPU adapter with a narrow tensor contract."""

    def __init__(
        self,
        model_path: Path,
        *,
        expected_sha256: str,
        class_codes: tuple[str, ...],
        input_size: int,
    ) -> None:
        try:
            content = model_path.read_bytes()
        except OSError as error:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_ARTIFACT_MISSING",
                "The local ONNX artifact cannot be read.",
            ) from error
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_ARTIFACT_DRIFT",
                "The local ONNX artifact checksum differs from the report.",
            )
        if not class_codes or input_size < 16:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_CLASS_CONTRACT_INVALID",
                "Class order and input size must be explicitly configured.",
            )
        try:
            model = onnx.load_model_from_string(content)
        except onnx.OnnxError as error:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_MODEL_INVALID",
                "The local ONNX artifact cannot be decoded.",
            ) from error
        validate_onnx_contract(
            model,
            input_size=input_size,
            class_count=len(class_codes),
        )
        if "CPUExecutionProvider" not in ort.get_available_providers():
            raise SymbolOnnxError(
                "SYMBOL_ONNX_CPU_PROVIDER_MISSING",
                "ONNX Runtime CPUExecutionProvider is unavailable.",
            )
        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        try:
            session = ort.InferenceSession(
                content,
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except (RuntimeError, ValueError) as error:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_SESSION_FAILED",
                "ONNX Runtime could not create the local CPU session.",
            ) from error
        if session.get_providers() != ["CPUExecutionProvider"]:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_PROVIDER_INVALID",
                "The inference session must use only CPUExecutionProvider.",
            )
        self._session = session
        self.class_codes = class_codes
        self.input_size = input_size
        self.artifact_sha256 = expected_sha256

    def infer(self, images: NDArray[np.float32]) -> OnnxInference:
        if (
            not isinstance(images, np.ndarray)
            or images.dtype != np.float32
            or images.ndim != 4
            or images.shape[0] < 1
            or tuple(images.shape[1:]) != (3, self.input_size, self.input_size)
        ):
            raise SymbolOnnxError(
                "SYMBOL_ONNX_INPUT_INVALID",
                "Input must be non-empty float32 N x 3 x input_size x input_size.",
            )
        if not np.isfinite(images).all():
            raise SymbolOnnxError(
                "SYMBOL_ONNX_INPUT_NON_FINITE",
                "Input contains a non-finite value.",
            )
        try:
            raw_outputs = self._session.run(
                [ONNX_OUTPUT_NAME],
                {ONNX_INPUT_NAME: np.ascontiguousarray(images)},
            )
        except (RuntimeError, ValueError) as error:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_INFERENCE_FAILED",
                "ONNX Runtime inference failed.",
            ) from error
        if len(raw_outputs) != 1:
            raise SymbolOnnxError(
                "SYMBOL_ONNX_OUTPUT_INVALID",
                "ONNX Runtime returned an unexpected output count.",
            )
        logits = np.asarray(raw_outputs[0], dtype=np.float32)
        expected_shape = (images.shape[0], len(self.class_codes))
        if logits.shape != expected_shape or not np.isfinite(logits).all():
            raise SymbolOnnxError(
                "SYMBOL_ONNX_OUTPUT_INVALID",
                "ONNX Runtime returned invalid logits.",
            )
        shifted = logits - logits.max(axis=1, keepdims=True)
        exponentials = np.exp(shifted).astype(np.float32, copy=False)
        probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
        if not np.isfinite(probabilities).all():
            raise SymbolOnnxError(
                "SYMBOL_ONNX_OUTPUT_NON_FINITE",
                "ONNX probabilities contain a non-finite value.",
            )
        return OnnxInference(
            logits=logits,
            probabilities=probabilities.astype(np.float32, copy=False),
            class_indexes=np.argmax(logits, axis=1).astype(np.int64, copy=False),
        )


def preprocess_rgb_batch(
    images: Sequence[NDArray[np.uint8]],
    *,
    input_size: int,
) -> NDArray[np.float32]:
    """Build one bounded NCHW batch without persistent intermediate crops."""

    if not images or input_size < 1:
        raise SymbolOnnxError(
            "SYMBOL_ONNX_INPUT_INVALID",
            "Symbol preprocessing requires at least one RGB image and a positive input size.",
        )
    batch = np.empty((len(images), 3, input_size, input_size), dtype=np.float32)
    for index, rgb in enumerate(images):
        if (
            not isinstance(rgb, np.ndarray)
            or rgb.dtype != np.uint8
            or rgb.ndim != 3
            or rgb.shape[2] != 3
        ):
            raise SymbolOnnxError(
                "SYMBOL_ONNX_INPUT_INVALID",
                "Symbol preprocessing requires RGB uint8 images.",
            )
        model_rgb = (
            rgb
            if rgb.shape[:2] == (input_size, input_size)
            else cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_AREA)
        )
        chw = model_rgb.transpose(2, 0, 1).astype(np.float32, copy=False)
        np.multiply(chw, 1.0 / 127.5, out=batch[index])
        batch[index] -= 1.0
    return batch


def tensor_batch_to_numpy(value: Tensor) -> NDArray[np.float32]:
    return value.detach().cpu().numpy().astype(np.float32, copy=False)
