"""Tiny CPU graph fixture exercises the real exporter and recorded-input parity."""

import json

import numpy as np
import pytest
import torch
from game_predictor_worker.geometry_core.preprocessing import board_rectifier, screen_input
from game_predictor_worker.geometry_core.rescue import BoardCropGeometryV1, ScreenInputGeometryV1
from game_predictor_worker.geometry_core.settings import BoardPreset, ScreenPreset
from game_predictor_worker.images.grid_rescue_export import RescueParity
from game_predictor_worker.images.grid_training_child import RECIPE_FILE
from game_predictor_worker.training_core.grid_training import export_graphs, namespace


class TinyScreen(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.head = torch.nn.Conv2d(3, 9, 1)

    def forward(self, pixels):
        value = self.head(torch.nn.functional.avg_pool2d(pixels, 4))
        return value[:, :1], value[:, 1:]


class TinyBoard(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.head = torch.nn.Linear(3, 72)

    def forward(self, crops):
        value = self.head(crops.mean(dim=(2, 3)))
        nodes = value[:, :48].reshape(-1, 24, 2)
        return nodes.reshape(-1, 24, 1, 2), nodes, value[:, 48:]


class TinyExport(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.screen = TinyScreen()
        self.board = TinyBoard()


def test_typed_overrides_leave_historical_preset_closed():
    preset = json.loads(RECIPE_FILE.read_bytes())
    with pytest.raises(ValueError):
        ScreenPreset.model_validate({**preset["screen"], "long_side": 1024})
    base = ScreenPreset.model_validate(preset["screen"])
    rgb = np.zeros((180, 240, 3), np.uint8)
    ordinary = screen_input(rgb, base)
    changed = screen_input(
        rgb, base, geometry=ScreenInputGeometryV1(longSide=1024, trainCanvas=(1024, 768))
    )
    assert ordinary[0].shape != changed[0].shape
    assert max(changed[0].shape[:2]) == 1024
    assert base.long_side == 768
    quad = np.array([[20, 20], [200, 20], [200, 150], [20, 150]], dtype=np.float32)
    board = BoardPreset.model_validate(preset["board"])
    crop = board_rectifier(quad, board)
    expanded = board_rectifier(quad, board, geometry=BoardCropGeometryV1(margin=0.2))
    assert crop.shape == expanded.shape
    assert not np.array_equal(crop, expanded)


def test_real_dynamic_graphs_support_both_orientations_and_fixed_board(tmp_path):
    torch.manual_seed(7)
    network = TinyExport().eval()
    recipe = namespace(json.loads(RECIPE_FILE.read_bytes()))
    export_graphs(network, recipe, tmp_path)
    parity = RescueParity(network, recipe, tmp_path)
    with torch.no_grad():
        for name, height, width in (
            ("baseline", 576, 768),
            ("screen_only", 768, 1024),
            ("combined", 1024, 768),
        ):
            parity.path = name
            parity.engine.screen_runner(np.full((1, 3, height, width), 0.125, np.float32))
        for name in ("baseline", "screen_only", "board_only", "combined"):
            parity.path = name
            parity.engine.board_runner(np.full((1, 3, 192, 320), 0.25, np.float32))
        with pytest.raises(ValueError, match="SHAPE_UNPROVEN"):
            parity.engine.screen_runner(np.zeros((1, 3, 63, 1024), np.float32))
    proof = parity.document()
    assert all(record["verdict"]["passed"] for record in proof["inputs"])
    assert all(not isinstance(size, int) for size in proof["graphs"]["screen"]["shape"][2:])
    assert proof["graphs"]["board"]["shape"][2:] == [192, 320]
