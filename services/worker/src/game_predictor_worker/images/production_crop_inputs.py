"""Witness actual runner tensors, then verify production-transform replays without GT."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_training_cohorts import digest
from PIL import Image

from ..geometry_core.input_diagnostics import _stage, array_sha256
from ..geometry_core.preprocessing import board_rectifier, crop_board, screen_input
from .grid_rescue_strategy import slots
from .production_crop_artifacts import sealed, write_bytes


def analyse_with_inputs(
    engine: Any, frame: Any, photo: dict[str, Any], grid: dict[str, Any] | None, root: Path
) -> tuple[list[Any], dict[str, Any]]:
    """Wrap only this command's owned engine; never modify production defaults."""
    core = getattr(engine, "engine", engine)
    if grid is None or not all(
        hasattr(core, name) for name in ("screen_runner", "board_runner", "settings")
    ):
        return engine.analyse(frame.rgb), {
            "state": "unavailable",
            "reason": "CROP_INPUT_RUNNER_WITNESS_UNAVAILABLE",
        }
    originals = {name: getattr(core, name + "_runner") for name in ("screen", "board")}
    seen: dict[str, set[str]] = {name: set() for name in originals}

    def witness(name: str) -> Any:
        def invoke(batch: Any) -> Any:
            # Network input bytes are observed before the real CPU runner executes.
            if len(seen[name]) + len(batch) > 4096:
                raise ValueError("CROP_INPUT_WITNESS_LIMIT")
            hashes = [array_sha256(sample.astype("<f4")) for sample in batch]
            result = originals[name](batch)
            seen[name].update(hashes)
            return result

        return invoke

    try:
        for name in originals:
            setattr(core, name + "_runner", witness(name))
        found = engine.analyse(frame.rgb)
    finally:
        for name, runner in originals.items():
            setattr(core, name + "_runner", runner)

    entries: list[dict[str, Any]] = []
    path = getattr(engine, "path", None)
    variant = getattr(engine, "variant", None)
    context = {
        "screenPreset": core.settings.screen.model_dump(mode="json"),
        "boardPreset": core.settings.board.model_dump(mode="json"),
        "routing": getattr(engine, "routing", None),
        "path": path,
        "variant": None if variant is None else variant.model_dump(mode="json"),
    }

    def record(
        stage_name: str, index: int, pixels: Any, matrix: Any, geometry: Any, quad: Any = None
    ) -> bool:
        tensor_sha = array_sha256(pixels.transpose(2, 0, 1).astype("<f4"))
        if tensor_sha not in seen[stage_name]:
            return False
        stage = _stage(pixels, matrix, screen=stage_name == "screen").model_dump(mode="json")
        value = {
            "stage": stage_name,
            "predictionIndex": index,
            "geometry": None if geometry is None else geometry.model_dump(mode="json"),
            "screenQuad": None if quad is None else np.asarray(quad).tolist(),
            "input": stage,
            "observedSampleTensorSha256": tensor_sha,
            "pixelSha256": rgb_pixel_checksum_sha256(pixels),
        }
        if photo["role"] == "TRAIN":
            output = BytesIO()
            Image.fromarray(pixels).save(output, format="PNG")
            relative = f"neural-inputs/{photo['sourceId']}/{stage_name}-{index}.png"
            value.update(write_bytes(root, relative, output.getvalue()))
        entries.append(value)
        return True

    screen_geometries = [None]
    completed = getattr(engine, "last_result", None)
    # Rescue screen is required only when the runtime actually requested it.
    if (
        variant is not None
        and path in ("screen_only", "combined")
        and (len(seen["screen"]) > 1 or getattr(completed, "redetect_calls", False))
    ):
        screen_geometries.append(variant.screen)
    missing_screen = []
    for index, geometry in enumerate(screen_geometries):
        pixels, sx, sy = screen_input(frame.rgb, core.settings.screen, geometry=geometry)
        if not record("screen", index, pixels, np.diag([sx, sy, 1.0]), geometry):
            missing_screen.append("base" if index == 0 else "rescue")
    bound_screen = {
        entry["observedSampleTensorSha256"] for entry in entries if entry["stage"] == "screen"
    }
    if seen["screen"] - bound_screen:
        missing_screen.append("unbound-observed-screen")
    missing = []
    binding = slots(found)
    positions = {} if binding is None else {v: k for k, v in binding.items()}
    baseline = getattr(engine, "last_baseline", None)
    for index, detection in enumerate(found):
        if getattr(detection, "raw_nodes", None) is None:
            missing.append(index)
            continue
        geometry = None
        if baseline is not None and not any(detection is d for d in baseline):
            if completed is None or positions.get(index) not in completed.crop_calls:
                missing.append(index)
                continue
            if variant is not None and path in ("board_only", "combined"):
                geometry = variant.board
        # Reconstruct the path actually selected by the runtime, then require
        # equality with a completed runner sample. Never try an invented retry.
        matrix = board_rectifier(detection.screen_quad, core.settings.board, geometry=geometry)
        pixels = crop_board(frame.rgb, matrix, core.settings.board, geometry=geometry)
        if not record("board", index, pixels, matrix, geometry, detection.screen_quad):
            missing.append(index)
    return found, sealed(
        {
            "schemaVersion": "production-crop-input-witness-v1",
            "state": "available" if not missing and not missing_screen else "partial",
            "sourceId": photo["sourceId"],
            "sourcePixelSha256": frame.pixel_checksum_sha256,
            "gridModel": grid,
            "context": context,
            "contextSha256": digest(context),
            "entries": entries,
            "unavailablePredictionIndices": missing,
            "unavailableScreenStages": missing_screen,
            "reason": "CROP_ACTUAL_SCREEN_INPUT_NOT_BOUND"
            if missing_screen
            else "CROP_ACTUAL_INPUT_NOT_BOUND"
            if missing
            else None,
            "contentReferenceRequired": False,
        }
    )
