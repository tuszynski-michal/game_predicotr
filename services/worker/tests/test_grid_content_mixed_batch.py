"""P2-3: ignored crop rows cannot affect real R0 BatchNorm or valid gradients."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch
from game_predictor_worker.images.grid_training_data import ScreenGridBatches
from game_predictor_worker.training_core.grid_training import screen_grid_losses
from game_predictor_worker.training_core.neural_grid_network import BoardNetwork
from game_predictor_worker.vision_lab.neural_grid_protocol import load_preset


class Screen(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1))

    def forward(self, image):
        count = image.shape[0]
        return self.weight.expand(count, 1, 2, 2), self.weight.expand(count, 8, 2, 2)


def batch(crop, *, mixed, two_photos, auxiliary):
    count = 2 if mixed else 1
    photos, boards = (count, 1) if two_photos else (1, count)
    # The valid row is last, so a prefix-only slice would corrupt its targets.
    pixels = torch.cat([torch.full_like(crop, 114), crop], dim=0) if mixed else crop.clone()
    masks = torch.tensor([0.0, 1.0] if mixed else [1.0]).reshape(photos, boards)
    nodes = torch.arange(48, dtype=torch.float32).reshape(1, 24, 2) + 20
    nodes = nodes.expand(count, 24, 2).clone()
    vis = torch.ones(count, 15)
    quads = torch.tensor([[20.0, 20.0], [40.0, 20.0], [40.0, 40.0], [20.0, 40.0]])
    quads = quads.expand(count, 15, 4, 2).clone()
    if mixed:
        nodes[0] = float("nan")
        vis[0] = float("nan")
        quads[0] = float("nan")
    result = {
        "image": torch.zeros(photos, 3, 8, 8),
        "heat": torch.zeros(photos, 1, 2, 2),
        "offsets": torch.zeros(photos, 8, 2, 2),
        "offset_weight": torch.ones(photos, 1, 2, 2),
        "crops": pixels.reshape(photos, boards, 3, 192, 320).detach().requires_grad_(),
        "nodes": nodes.reshape(photos, boards, 24, 2),
        "weights": masks.clone(),
        "node_weights": masks[..., None].expand(photos, boards, 24).clone(),
        "visibility_mask": masks[..., None].expand(photos, boards, 15).clone(),
        "visibility_targets": vis.reshape(photos, boards, 15),
        "crop_skipped": 1 - masks,
    }
    if auxiliary:
        result.update(
            content_quads=quads.reshape(photos, boards, 15, 4, 2),
            content_quad_mask=masks[..., None].expand(photos, boards, 15).clone(),
        )
    return result


def board_loss(values, auxiliary):
    names = ["nodes", "node_heatmap", "visibility"]
    if auxiliary:
        names.extend(["content_quads", "local_visibility"])
    return sum(values[key] for key in names)


@pytest.mark.parametrize("two_photos", [False, True])
@pytest.mark.parametrize("auxiliary", [False, True])
def test_mixed_skip_equals_valid_only_bn_outputs_targets_and_gradients(two_photos, auxiliary):
    torch.set_num_threads(1)
    torch.manual_seed(1167)
    valid_board = BoardNetwork(width=8, content_head=auxiliary).train()
    mixed_board = deepcopy(valid_board)
    crop = torch.rand(1, 3, 192, 320) * 255
    valid = batch(crop, mixed=False, two_photos=two_photos, auxiliary=auxiliary)
    mixed = batch(crop, mixed=True, two_photos=two_photos, auxiliary=auxiliary)
    before = {key: value.detach().clone() for key, value in mixed.items()}
    forwarded, logits = [], []
    handles = [
        mixed_board.features.register_forward_pre_hook(
            lambda _, args: forwarded.append(args[0].detach().clone())
        ),
        valid_board.nodes.register_forward_hook(
            lambda _, args, result: logits.append(result.detach().clone())
        ),
        mixed_board.nodes.register_forward_hook(
            lambda _, args, result: logits.append(result.detach().clone())
        ),
    ]
    recipe = load_preset("A")[0]
    left = screen_grid_losses(
        SimpleNamespace(screen=Screen(), board=valid_board), valid, recipe, "cpu"
    )
    right = screen_grid_losses(
        SimpleNamespace(screen=Screen(), board=mixed_board), mixed, recipe, "cpu"
    )
    board_loss(left, auxiliary).backward()
    board_loss(right, auxiliary).backward()
    for handle in handles:
        handle.remove()
    assert len(forwarded) == 1 and forwarded[0].shape[0] == 1
    torch.testing.assert_close(forwarded[0], crop, rtol=0, atol=0)
    torch.testing.assert_close(logits[0], logits[1], rtol=0, atol=0)
    torch.testing.assert_close(
        board_loss(left, auxiliary), board_loss(right, auxiliary), rtol=0, atol=0
    )
    for key, value in valid_board.named_buffers():
        torch.testing.assert_close(value, dict(mixed_board.named_buffers())[key], rtol=0, atol=0)
    for key, value in valid_board.named_parameters():
        other = dict(mixed_board.named_parameters())[key]
        if value.grad is None:
            assert other.grad is None
        else:
            torch.testing.assert_close(value.grad, other.grad, rtol=0, atol=0)
    mixed_grad = mixed["crops"].grad.flatten(0, 1)
    assert torch.count_nonzero(mixed_grad[0]) == 0
    torch.testing.assert_close(mixed_grad[1:], valid["crops"].grad.flatten(0, 1), rtol=0, atol=0)
    assert right["valid_nodes"] == 24 and right["masked_nodes"] == 24
    assert right["valid_visibility"] == 15 and right["masked_visibility"] == 15
    assert right["skipped_board_crops"] == 1
    if auxiliary:
        assert right["valid_content_quads"] == 15
    # Exposure still observes the unmodified original photo/crop mapping.
    for key, value in before.items():
        torch.testing.assert_close(mixed[key].detach(), value, rtol=0, atol=0, equal_nan=True)
    members = [{"sourceId": f"photo-{i}"} for i in range(mixed["image"].shape[0])]
    source = SimpleNamespace(exposure_members=lambda step: members)
    exposure = ScreenGridBatches.content_exposure_members(source, 0, mixed, right)
    assert exposure["screen"] == members
    assert exposure["board"] == [members[-1]]


def test_legacy_without_explicit_skip_keeps_existing_full_batch_forward():
    torch.set_num_threads(1)
    board = BoardNetwork(width=8).train()
    data = batch(torch.rand(1, 3, 192, 320) * 255, mixed=True, two_photos=False, auxiliary=False)
    del data["crop_skipped"]
    forwarded = []
    handle = board.features.register_forward_pre_hook(
        lambda _, args: forwarded.append(args[0].shape[0])
    )
    result = screen_grid_losses(
        SimpleNamespace(screen=Screen(), board=board), data, load_preset("A")[0], "cpu"
    )
    handle.remove()
    assert forwarded == [2] and "skipped_board_crops" not in result


@pytest.mark.parametrize("failure", ["mask", "weight", "contradictory_skip"])
def test_invalid_skipped_row_does_not_hide_bad_supervision(failure):
    data = batch(torch.zeros(1, 3, 192, 320), mixed=True, two_photos=False, auxiliary=False)
    if failure == "mask":
        data["node_weights"][0, 0, 0] = float("nan")
    elif failure == "weight":
        data["weights"][0, 0] = -1
    else:
        data["crop_skipped"][0, 1] = 1
    with pytest.raises(ValueError, match="CONTENT_.*INVALID"):
        screen_grid_losses(
            SimpleNamespace(screen=Screen(), board=None), data, load_preset("A")[0], "cpu"
        )
