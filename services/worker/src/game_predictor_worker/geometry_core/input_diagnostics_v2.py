"""Replay one completed rescue request against its exact canonical raster, no inference."""

from __future__ import annotations

from typing import Any, Literal

import cv2
import numpy as np
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_rescue_policy import require_rescue_pin
from pydantic import StrictInt

from .input_diagnostics import (
    SUPPORTED_PREPROCESSING_VERSION,
    InputDiagnostic,
    InputStage,
    ModelPin,
    SourcePin,
    _stage,
    array_sha256,
    decode_record,
    digest,
)
from .preprocessing import ByteImage, board_rectifier, crop_board, quad_is_usable, screen_input
from .rescue import (
    BoardCropGeometryV1,
    BoardCropGeometryV2,
    GridRescueVariantV1,
    GridRescueVariantV2,
    ScreenInputGeometryV1,
)
from .rescue_serialization import detection_from_document
from .settings import BoardPreset, Contract, ScreenPreset


class RequestInputDiagnostic(Contract):
    schema_version: Literal["full-board-input-diagnostic-v2"] = "full-board-input-diagnostic-v2"
    source: SourcePin
    model: ModelPin
    archived_preset: dict[str, Any]
    execution: dict[str, Any]
    expected_positions: list[StrictInt]
    attempt: str
    stage: InputStage


def _pixels(
    source: SourcePin,
    model: ModelPin,
    preset: dict[str, Any],
    execution: dict[str, Any],
    positions: list[int],
    attempt: str,
    rgb: ByteImage,
) -> tuple[InputStage, ByteImage]:
    if set(execution) != {
        "contractVersion",
        "preprocessingContract",
        "identity",
        "attempts",
        "reasonCodes",
        "sha256",
    } or execution["sha256"] != digest({k: v for k, v in execution.items() if k != "sha256"}):
        raise ValueError("DIAGNOSTIC_EXECUTION_CHECKSUM_MISMATCH")
    identity = execution["identity"]
    if (
        execution["contractVersion"] != "grid-rescue-execution-v1"
        or execution["preprocessingContract"]
        not in ("neural-grid-rescue-preprocessing-v1", "neural-grid-content-preprocessing-v1")
        or identity.get("preprocessingContract") != execution["preprocessingContract"]
        or identity.get("opencvVersion") != cv2.__version__
    ):
        raise ValueError("DIAGNOSTIC_EXECUTION_VERSION_MISMATCH")
    if (
        "GRID_RESCUE_SLOT_BINDING_REQUIRED" in execution["reasonCodes"]
        or not isinstance(identity.get("positions"), list)
        or any(type(p) is not int for p in identity.get("positions", []))
        or identity.get("positions") != positions
        or positions != sorted(set(positions))
        or not positions
        or any(type(p) is not int or not 0 <= p <= 8 for p in positions)
    ):
        raise ValueError("DIAGNOSTIC_FOREIGN_SLOT_SCOPE")
    if (
        identity.get("sourceSha256") != source.source_sha256
        or identity.get("width") != source.width
        or identity.get("height") != source.height
        or rgb.dtype != np.uint8
        or rgb.shape != (source.height, source.width, 3)
        or array_sha256(rgb) != source.rgb_bytes_sha256
    ):
        raise ValueError("DIAGNOSTIC_SOURCE_PIXELS_MISMATCH")
    raster = identity.get("inputRaster")
    if not isinstance(raster, dict) or set(raster) != {
        "pixelSha256",
        "validBox",
        "coordinateSpace",
    }:
        raise ValueError("DIAGNOSTIC_ACTUAL_RASTER_UNAVAILABLE")
    if raster["coordinateSpace"] != "exif-normalized-rgb-pixels-v1" or raster[
        "pixelSha256"
    ] != rgb_pixel_checksum_sha256(rgb):
        raise ValueError("DIAGNOSTIC_ACTUAL_RASTER_MISMATCH")
    box = raster["validBox"]
    if (
        not isinstance(box, list)
        or len(box) != 4
        or not all(isinstance(v, int | float) and np.isfinite(v) for v in box)
        or not 0 <= box[0] < box[2] <= source.width
        or not 0 <= box[1] < box[3] <= source.height
    ):
        raise ValueError("DIAGNOSTIC_ACTUAL_SUPPORT_INVALID")
    if (
        digest(preset) != model.preset_sha256
        or identity.get("baselinePresetSha256") != model.preset_sha256
    ):
        raise ValueError("DIAGNOSTIC_PRESET_HASH_MISMATCH")
    if (
        model.preprocessing_version != SUPPORTED_PREPROCESSING_VERSION
        or preset.get("preprocessing_version") != model.preprocessing_version
    ):
        raise ValueError("DIAGNOSTIC_PREPROCESSING_VERSION_MISMATCH")
    screen = ScreenPreset.model_validate(preset.get("screen"))
    board = BoardPreset.model_validate(preset.get("board"))
    pin = require_rescue_pin(identity.get("pin"), bundle_sha=model.bundle_sha256)
    content_mode = pin["policyVersion"] == "grid-content-rescue-policy-v1"
    variant = (GridRescueVariantV2 if content_mode else GridRescueVariantV1).model_validate(
        pin["variant"]
    )
    if execution["preprocessingContract"] != variant.preprocessingContract:
        raise ValueError("DIAGNOSTIC_REQUEST_GEOMETRY_MISMATCH")
    variant.require_baseline(board.margin)
    matches = [item for item in execution["attempts"] if item.get("attempt") == attempt]
    if len(matches) != 1:
        raise ValueError("DIAGNOSTIC_ATTEMPT_UNAVAILABLE")
    completed = matches[0]
    if (
        completed.get("state") != "completed"
        or not isinstance(completed.get("resultSha256"), str)
        or len(completed["resultSha256"]) != 64
        or any(c not in "0123456789abcdef" for c in completed["resultSha256"])
    ):
        raise ValueError("DIAGNOSTIC_ATTEMPT_NOT_COMPLETED")
    request = completed["request"]
    if completed.get("reservationSha256") != digest({"state": "reserved", "request": request}):
        raise ValueError("DIAGNOSTIC_REQUEST_CHECKSUM_MISMATCH")
    if (
        request.get("opencvVersion") != cv2.__version__
        or request.get("preprocessingContract") != execution["preprocessingContract"]
    ):
        raise ValueError("DIAGNOSTIC_REQUEST_VERSION_MISMATCH")
    if attempt == "redetect":
        if (
            set(request) != {"kind", "geometry", "opencvVersion", "preprocessingContract"}
            or request["kind"] != "screen"
            or pin["selectedPath"] not in ("screen_only", "combined")
            or variant.screen is None
            or request["geometry"] != variant.screen.model_dump(mode="json")
        ):
            raise ValueError("DIAGNOSTIC_REQUEST_GEOMETRY_MISMATCH")
        geometry = ScreenInputGeometryV1.model_validate(request["geometry"])
        pixels, sx, sy = screen_input(rgb, screen, geometry=geometry)
        return _stage(pixels, np.diag([sx, sy, 1.0]), screen=True), pixels
    if not attempt.startswith("crop-") or attempt[5:] not in {str(p) for p in positions}:
        raise ValueError("DIAGNOSTIC_FOREIGN_SLOT_SCOPE")
    if (
        set(request) != {"kind", "geometry", "opencvVersion", "preprocessingContract", "detection"}
        or request["kind"] != "board"
    ):
        raise ValueError("DIAGNOSTIC_REQUEST_GEOMETRY_MISMATCH")
    expected = variant.board if pin["selectedPath"] in ("board_only", "combined") else None
    if request["geometry"] != (expected.model_dump(mode="json") if expected else None):
        raise ValueError("DIAGNOSTIC_REQUEST_GEOMETRY_MISMATCH")
    detection = detection_from_document(request["detection"])
    if not quad_is_usable(detection.screen_quad):
        raise ValueError("DIAGNOSTIC_SCREEN_QUAD_INVALID")
    override = (
        (BoardCropGeometryV2 if content_mode else BoardCropGeometryV1).model_validate(
            request["geometry"]
        )
        if request["geometry"] is not None
        else None
    )
    matrix = board_rectifier(detection.screen_quad, board, geometry=override)
    pixels = crop_board(rgb, matrix, board, geometry=override)
    return _stage(pixels, matrix, screen=False), pixels


def capture_request_input(
    *,
    source: SourcePin,
    model: ModelPin,
    archived_preset: dict[str, Any],
    execution: dict[str, Any],
    expected_positions: list[int],
    attempt: str,
    rgb: ByteImage,
) -> RequestInputDiagnostic:
    stage, _ = _pixels(source, model, archived_preset, execution, expected_positions, attempt, rgb)
    return RequestInputDiagnostic(
        source=source,
        model=model,
        archived_preset=archived_preset,
        execution=execution,
        expected_positions=expected_positions,
        attempt=attempt,
        stage=stage,
    )


def replay_request_input(record: RequestInputDiagnostic, rgb: ByteImage) -> ByteImage:
    stage, pixels = _pixels(
        record.source,
        record.model,
        record.archived_preset,
        record.execution,
        record.expected_positions,
        record.attempt,
        rgb,
    )
    if stage != record.stage:
        raise ValueError("DIAGNOSTIC_INPUT_REPLAY_MISMATCH")
    return pixels


def decode_input_record(document: dict[str, Any]) -> InputDiagnostic | RequestInputDiagnostic:
    if document.get("payload", {}).get("schema_version") != "full-board-input-diagnostic-v2":
        return decode_record(document)
    if set(document) != {"payload", "sha256"} or digest(document["payload"]) != document["sha256"]:
        raise ValueError("DIAGNOSTIC_RECORD_CHECKSUM_MISMATCH")
    return RequestInputDiagnostic.model_validate(document["payload"])
