"""Real torch/ONNX operators, masked human targets and component exposure on CPU."""

from types import SimpleNamespace

import numpy as np
import pytest
import torch
from game_predictor_worker.geometry_core.preprocessing import grid_from_quad
from game_predictor_worker.geometry_core.rescue import BoardCropGeometryV2
from game_predictor_worker.training_core.grid_rescue_training import ContentTrainingExposure
from game_predictor_worker.training_core.grid_training import (
    content_auxiliary_losses,
    export_graphs,
    raw_parity,
    screen_grid_losses,
)
from game_predictor_worker.training_core.grid_visibility_targets import supervised_board_crop
from game_predictor_worker.training_core.neural_grid_network import BoardNetwork, ScreenNetwork
from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset
from test_grid_content_experiment import closed_plan


def test_real_head_and_shared_features_receive_only_unmasked_gradients():
    torch.set_num_threads(1)
    network = BoardNetwork(width=8, content_head=True).eval()
    crop = torch.rand(2, 3, 192, 320) * 255
    _, _, _, quads, local = network.forward_with_content(crop)
    quads.retain_grad()
    local.retain_grad()
    targets = torch.full((2, 15, 4, 2), float("nan"))
    targets[0, 2] = torch.tensor([[10, 10], [30, 10], [30, 30], [10, 30]])
    mask = torch.zeros(2, 15)
    mask[0, 2] = 1
    batch = {
        "content_quads": targets,
        "content_quad_mask": mask,
        "visibility_targets": torch.where(mask > 0, 1.0, float("nan")),
        "visibility_mask": mask,
    }
    losses = content_auxiliary_losses(quads, local, batch, torch.ones(2), (320, 192), "cpu")
    (losses["content_quads"] + losses["local_visibility"]).backward()
    assert quads.shape == (2, 15, 4, 2) and local.shape == (2, 15)
    assert quads.grad[0, 2].abs().sum() > 0 and torch.count_nonzero(quads.grad[1]) == 0
    assert local.grad[0, 2].abs() > 0 and torch.count_nonzero(local.grad[1]) == 0
    assert network.content_head.weight.grad.abs().sum() > 0
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in network.features.parameters())
    assert BoardNetwork(width=8).state_dict().keys() == {
        k for k in network.state_dict() if not k.startswith("content_head.")
    }


def test_three_invalid_jitters_skip_without_target_fallback(monkeypatch):
    import game_predictor_worker.training_core.grid_visibility_targets as targets

    draws = []
    monkeypatch.setattr(
        targets, "perturb_quad", lambda *args: draws.append(1) or np.zeros((4, 2), np.float32)
    )
    preset = load_preset("A")[0]
    quad = np.array([[10, 10], [80, 10], [80, 80], [10, 80]], np.float32)
    result = supervised_board_crop(
        np.zeros((100, 100, 3), np.uint8),
        grid_from_quad(quad),
        preset.board,
        preset.augmentation,
        np.random.default_rng(1),
        reference=None,
        supervision=SimpleNamespace(qualified=False),
        source_support=np.ones((100, 100), np.float32),
        geometry=BoardCropGeometryV2(canvas=(480, 288), margin=0.30),
        content_auxiliary=True,
        explicit_skip=True,
    )
    assert len(draws) == 3 and result["crop_skipped"] == 1
    assert result["crop"].shape == (288, 480, 3)
    for key in ("node_weights", "visibility_mask", "content_quad_mask"):
        assert result[key].sum() == 0


def test_component_exposure_records_actual_stage_and_shape_and_resume():
    plan = closed_plan()
    exposure = ContentTrainingExposure(plan, "R2")
    member = {
        "gameId": "game",
        "sourceId": "source",
        "sourceSha256": "a" * 64,
        "cohortSha256": "c" * 64,
    }
    exposure.confirm_components(
        1,
        screen_members=[member],
        board_members=[],
        screen_canvas=(768, 576),
        board_canvas=(320, 192),
    )
    assert set(exposure.state()["games"]["game"]) == {"screen:baseline"}
    restored = ContentTrainingExposure(plan, "R2")
    restored.restore(exposure.state(), 1)
    with pytest.raises(ValueError, match="RASTER_INVALID"):
        restored.confirm_components(
            2,
            screen_members=[],
            board_members=[member],
            screen_canvas=None,
            board_canvas=(320, 192),
        )
    restored.confirm_components(
        2, screen_members=[], board_members=[member], screen_canvas=None, board_canvas=(480, 288)
    )
    assert set(restored.state()["games"]["game"]) == {"screen:baseline", "board:variant"}


def test_all_skipped_board_batch_does_not_even_run_board_batchnorm():
    class Screen(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.ones(1))

        def forward(self, image):
            return self.weight.expand(1, 1, 2, 2), self.weight.expand(1, 8, 2, 2)

    class Board(torch.nn.Module):
        def forward(self, crops):
            pytest.fail("A skipped crop must not update R0 BatchNorm statistics")

    network = SimpleNamespace(screen=Screen(), board=Board())
    batch = {
        "image": torch.zeros(1, 3, 8, 8),
        "heat": torch.zeros(1, 1, 2, 2),
        "offsets": torch.zeros(1, 8, 2, 2),
        "offset_weight": torch.ones(1, 1, 2, 2),
        "crops": torch.zeros(1, 1, 3, 192, 320),
        "nodes": torch.zeros(1, 1, 24, 2),
        "weights": torch.ones(1, 1),
        "node_weights": torch.zeros(1, 1, 24),
        "visibility_mask": torch.zeros(1, 1, 15),
        "crop_skipped": torch.ones(1, 1),
    }
    result = screen_grid_losses(network, batch, load_preset("A")[0], "cpu")
    result["total"].backward()
    assert result["skipped_board_crops"] == 1 and network.screen.weight.grad.abs().sum() > 0


def test_real_dynamic_onnx_board_content_and_screen_both_canvases(tmp_path):
    torch.set_num_threads(1)

    class Network(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.screen = ScreenNetwork(width=8)
            self.board = BoardNetwork(width=8, content_head=True)

    network = Network().eval()
    preset = load_preset("A")[0]
    export_graphs(network, preset, tmp_path, dynamic_board=True, content_auxiliary=True)
    rng = np.random.default_rng(73)
    for board, screen in [((320, 192), (768, 576)), ((480, 288), (1280, 960))]:
        crop = rng.uniform(0, 255, (1, 3, board[1], board[0])).astype(np.float32)
        pixels = rng.uniform(0, 255, (1, 3, screen[1], screen[0])).astype(np.float32)
        verdict = raw_parity(network, tmp_path, crop, pixels, content_auxiliary=True)
        assert verdict["passed"], verdict
        assert set(verdict["maxDelta"]) == {
            "board.nodes",
            "board.peak",
            "board.visibility",
            "screen.heat",
            "screen.offsets",
            "content.content_quads",
            "content.local_visibility",
        }
