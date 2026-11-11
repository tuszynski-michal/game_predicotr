"""Actual raster parity for the selected content arm's dynamic CPU graphs."""

from __future__ import annotations

from typing import Any

import numpy as np
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_training_cohorts import digest

from ..geometry_core.preprocessing import board_rectifier, corners, crop_board, screen_input
from ..geometry_core.rescue import GridRescueVariantV2
from ..training_core.grid_training import raw_parity


def content_parity(
    network: Any,
    directory: Any,
    photos: Any,
    recipe: Any,
    arm: str,
    include_legacy_parity: bool = False,
) -> dict[str, Any]:
    from .grid_training_child import sha256_file

    if include_legacy_parity:
        from .grid_training_data import parity_inputs, validation_crops

        crops, _ = validation_crops(photos, recipe)
        board_inputs, screen_inputs = parity_inputs(crops, photos, recipe)
        if not raw_parity(network, directory, board_inputs, screen_inputs)["passed"]:
            raise ValueError("CONTENT_EXPERIMENT_RUNTIME_PARITY_FAILED")
    rgb = photos.rgb(0)
    nodes = photos.targets(0)[0][0]
    variant = GridRescueVariantV2()
    cases = []
    for changed in (False, True) if arm in ("R2", "R3") else (False,):
        geometry = variant.board if changed else None
        matrix = board_rectifier(corners(nodes), recipe.board, geometry=geometry)
        board = crop_board(rgb, matrix, recipe.board, geometry=geometry)
        screen, _, _ = screen_input(
            rgb, recipe.screen, geometry=variant.screen if changed else None
        )
        result = raw_parity(
            network,
            directory,
            board.transpose(2, 0, 1)[None].astype(np.float32),
            screen.transpose(2, 0, 1)[None].astype(np.float32),
            content_auxiliary=arm == "R3",
        )
        if not result["passed"]:
            raise ValueError("CONTENT_EXPERIMENT_RUNTIME_PARITY_FAILED")
        cases.append(
            {
                "screenLongSide": 1280 if changed else 768,
                "boardCanvas": [board.shape[1], board.shape[0]],
                "boardMargin": 0.30 if changed else 0.15,
                "inputSha256s": {
                    "screen": rgb_pixel_checksum_sha256(screen),
                    "board": rgb_pixel_checksum_sha256(board),
                },
                "result": result,
            }
        )
    graphs = {
        name: sha256_file(directory / name)
        for name in ("screen.onnx", "board.onnx", *(("content.onnx",) if arm == "R3" else ()))
    }
    body = {"schemaVersion": "content-runtime-parity-v1", "cases": cases, "graphs": graphs}
    return {**body, "sha256": digest(body)}
