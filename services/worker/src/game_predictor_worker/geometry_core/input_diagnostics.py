"""Versioned, inference-free reconstruction of neural-grid input samples."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Annotated, Any, Literal

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from .preprocessing import ByteImage, board_rectifier, crop_board, quad_is_usable, screen_input
from .settings import BoardPreset, Contract, ScreenPreset

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Point = tuple[float, float]
Matrix = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
SUPPORTED_PREPROCESSING_VERSION = "neural-grid-screen768-board320x192-v1"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def array_sha256(value: NDArray[Any]) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


class SourcePin(Contract):
    source_id: str
    source_sha256: Sha256
    normalized_pixel_sha256: Sha256
    rgb_bytes_sha256: Sha256
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    exif_orientation: int | None
    decoder_version: str
    coordinate_space: str


class ModelPin(Contract):
    version_id: str
    bundle_sha256: Sha256
    preset_sha256: Sha256
    preprocessing_version: str


class InputStage(Contract):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_to_input: Matrix
    interpolation: Literal["INTER_AREA", "INTER_LINEAR"]
    padding: Literal[114] = 114
    border: Literal["right_bottom", "BORDER_CONSTANT"]
    rgb_dtype: Literal["uint8"] = "uint8"
    rgb_layout: Literal["HWC"] = "HWC"
    rgb_sha256: Sha256
    tensor_dtype: Literal["float32"] = "float32"
    tensor_byte_order: Literal["little"] = "little"
    tensor_layout: Literal["NCHW", "CHW"]
    tensor_scope: Literal["screen_runner_batch", "single_board_sample_before_stack"]
    tensor_shape: tuple[int, ...]
    tensor_sha256: Sha256
    normalization: Literal["none_values_0_to_255"] = "none_values_0_to_255"


class NodeObservation(Contract):
    nodes: list[Point] | None
    unavailable_reason: str | None

    @model_validator(mode="after")
    def consistent(self) -> NodeObservation:
        if self.nodes is None:
            if not self.unavailable_reason:
                raise ValueError("DIAGNOSTIC_UNAVAILABLE_REASON_REQUIRED")
        elif len(self.nodes) != 24 or self.unavailable_reason is not None:
            raise ValueError("DIAGNOSTIC_EXPECTED_24_NODES")
        return self


class DiagnosticUse(Contract):
    source_id: str
    source_sha256: Sha256
    normalized_pixel_sha256: Sha256
    purpose: Literal["diagnostic_comparison"] = "diagnostic_comparison"
    independent_validation: Literal[False] = False
    future_control_exclusion_required: Literal[True] = True
    ledger_modified: Literal[False] = False


class InputDiagnostic(Contract):
    schema_version: Literal["full-board-input-diagnostic-v1"] = "full-board-input-diagnostic-v1"
    opencv_version: str
    source: SourcePin
    model: ModelPin
    archived_preset: dict[str, Any]
    sequence_number: int = Field(gt=0)
    position_index: int = Field(ge=0, le=8)
    association_basis: Literal["exact_saved_nodes_then_unique_equal_detector_quad"]
    screen_quad: tuple[Point, Point, Point, Point]
    screen_preset: ScreenPreset
    board_preset: BoardPreset
    screen: InputStage
    board: InputStage
    raw_nodes: NodeObservation
    fitted_nodes: NodeObservation
    reason_codes: list[str]
    historical_disposition: str | None
    current_policy: str
    current_policy_blockers: list[str]
    current_policy_verdict: Literal["blocked", "unavailable"]
    # This saved-comparison adapter has no qualified human reference. A future
    # schema must bind real reader evidence before introducing a GT metric.
    human_reference: Literal["unavailable"] = "unavailable"
    human_reference_reason: str = "NO_QUALIFIED_REFERENCE_BOUND_TO_SAVED_COMPARISON"
    fraction_of_gt_outside_input: None = None
    diagnostic_use: DiagnosticUse

    @model_validator(mode="after")
    def same_source(self) -> InputDiagnostic:
        if (
            self.diagnostic_use.source_id != self.source.source_id
            or self.diagnostic_use.source_sha256 != self.source.source_sha256
            or self.diagnostic_use.normalized_pixel_sha256 != self.source.normalized_pixel_sha256
        ):
            raise ValueError("DIAGNOSTIC_USE_SOURCE_MISMATCH")
        return self


def _stage(pixels: ByteImage, matrix: NDArray[np.float64], *, screen: bool) -> InputStage:
    sample = pixels.transpose(2, 0, 1).astype(np.float32)
    tensor = sample[None] if screen else sample
    return InputStage(
        width=pixels.shape[1],
        height=pixels.shape[0],
        source_to_input=matrix.tolist(),
        interpolation="INTER_AREA" if screen else "INTER_LINEAR",
        border="right_bottom" if screen else "BORDER_CONSTANT",
        rgb_sha256=array_sha256(pixels),
        tensor_layout="NCHW" if screen else "CHW",
        tensor_scope="screen_runner_batch" if screen else "single_board_sample_before_stack",
        tensor_shape=tensor.shape,
        tensor_sha256=array_sha256(tensor.astype("<f4")),
    )


def input_stages(
    rgb: ByteImage,
    source: SourcePin,
    quad: tuple[Point, Point, Point, Point],
    screen: ScreenPreset,
    board: BoardPreset,
) -> tuple[InputStage, InputStage, ByteImage, ByteImage]:
    """Use production transforms; never run either network or refit nodes."""
    if (
        rgb.dtype != np.uint8
        or rgb.shape != (source.height, source.width, 3)
        or array_sha256(rgb) != source.rgb_bytes_sha256
    ):
        raise ValueError("DIAGNOSTIC_SOURCE_PIXELS_MISMATCH")
    points = np.asarray(quad, dtype=np.float32)
    if points.shape != (4, 2) or not quad_is_usable(points):
        raise ValueError("DIAGNOSTIC_SCREEN_QUAD_INVALID")
    # Bound diagnostic allocation even when a foreign preset is supplied.
    if any(size < 1 or size > 4096 for size in board.canvas):
        raise ValueError("DIAGNOSTIC_CANVAS_LIMIT")
    canvas, sx, sy = screen_input(rgb, screen)
    matrix = board_rectifier(points, board)
    if not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("DIAGNOSTIC_TRANSFORM_INVALID")
    crop = crop_board(rgb, matrix, board)
    return (
        _stage(canvas, np.diag([sx, sy, 1.0]), screen=True),
        _stage(crop, matrix, screen=False),
        canvas,
        crop,
    )


def reconstruct_input(record: InputDiagnostic, rgb: ByteImage) -> tuple[ByteImage, ByteImage]:
    """Fail on environment, metadata or byte drift instead of silently recropping."""
    if digest(record.archived_preset) != record.model.preset_sha256:
        raise ValueError("DIAGNOSTIC_PRESET_HASH_MISMATCH")
    if (
        record.model.preprocessing_version != SUPPORTED_PREPROCESSING_VERSION
        or record.archived_preset.get("preprocessing_version") != record.model.preprocessing_version
    ):
        raise ValueError("DIAGNOSTIC_PREPROCESSING_VERSION_MISMATCH")
    if (
        ScreenPreset.model_validate(record.archived_preset.get("screen")) != record.screen_preset
        or BoardPreset.model_validate(record.archived_preset.get("board")) != record.board_preset
    ):
        raise ValueError("DIAGNOSTIC_PRESET_CONTRACT_MISMATCH")
    if record.opencv_version != cv2.__version__:
        raise ValueError("DIAGNOSTIC_OPENCV_VERSION_MISMATCH")
    screen, board, canvas, crop = input_stages(
        rgb, record.source, record.screen_quad, record.screen_preset, record.board_preset
    )
    if screen != record.screen or board != record.board:
        raise ValueError("DIAGNOSTIC_INPUT_REPLAY_MISMATCH")
    return canvas, crop


def encode_record(record: InputDiagnostic) -> dict[str, object]:
    payload = record.model_dump(mode="json")
    return {"payload": payload, "sha256": digest(payload)}


def decode_record(document: dict[str, Any]) -> InputDiagnostic:
    if set(document) != {"payload", "sha256"} or digest(document["payload"]) != document["sha256"]:
        raise ValueError("DIAGNOSTIC_RECORD_CHECKSUM_MISMATCH")
    return InputDiagnostic.model_validate(document["payload"])


def diagnostic_uses(records: Iterable[InputDiagnostic]) -> list[dict[str, Any]]:
    """Stable T4 handoff: one source use, with distinct immutable record bindings.

    T4 must union records by recordSha256 and usages by deduplicationKey across
    reports. This is evidence of diagnostic access, not a new role ledger.
    """
    uses: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = record.diagnostic_use.model_dump(mode="json")
        key = digest(
            {
                "schemaVersion": "diagnostic-use-key-v1",
                **{
                    name: identity[name]
                    for name in ("source_id", "source_sha256", "normalized_pixel_sha256", "purpose")
                },
            }
        )
        use = uses.setdefault(key, {**identity, "deduplicationKey": key, "records": {}})
        record_sha = encode_record(record)["sha256"]
        use["records"][record_sha] = {
            "recordSha256": record_sha,
            "sequenceNumber": record.sequence_number,
            "positionIndex": record.position_index,
        }
    return [
        {**uses[key], "records": [value for _, value in sorted(uses[key]["records"].items())]}
        for key in sorted(uses)
    ]
