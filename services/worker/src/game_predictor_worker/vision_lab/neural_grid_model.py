"""Two-stage neural_grid network and its losses.

Both stages use torchvision ``mobilenet_v3_large`` features (trained from scratch: no
ImageNet weights are available offline) with a small FPN merged down to stride 4.
Inputs are float RGB in 0..255; ImageNet normalization happens inside the graph so the
ONNX contract is the raw pixel tensor.

* Screen: centre heatmap (1 channel, sigmoid) and corner offsets from the cell centre
  (8 channels, TL TR BR BL, divided by ``offset_scale``).
* Board: 24 node heatmaps decoded by a spatial soft-argmax into crop pixels, the peak
  probability per node and 15 cell-visibility logits.
"""

from __future__ import annotations

import math
from typing import cast

import torch
import torch.nn.functional as F  # noqa: N812
from torch import nn
from torchvision.models import mobilenet_v3_large  # type: ignore[import-untyped]

MEAN = (0.485 * 255, 0.456 * 255, 0.406 * 255)
STD = (0.229 * 255, 0.224 * 255, 0.225 * 255)


def _conv(in_channels: int, out_channels: int, kernel: int = 3) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, kernel, padding=kernel // 2, bias=False),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
    )


class FeaturePyramid(nn.Module):
    """MobileNetV3-Large stages at strides 4/8/16/32 merged top-down to stride 4."""

    mean: torch.Tensor
    std: torch.Tensor

    def __init__(self, width: int = 96) -> None:
        super().__init__()
        features = mobilenet_v3_large(weights=None).features
        self.c2 = features[:4]  # stride 4, 24 channels
        self.c3 = features[4:7]  # stride 8, 40 channels
        self.c4 = features[7:13]  # stride 16, 112 channels
        self.c5 = features[13:]  # stride 32, 960 channels
        self.l2 = nn.Conv2d(24, width, 1)
        self.l3 = nn.Conv2d(40, width, 1)
        self.l4 = nn.Conv2d(112, width, 1)
        self.l5 = nn.Conv2d(960, width, 1)
        self.smooth = _conv(width, width)
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1), persistent=False)
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1), persistent=False)

    def forward(self, pixels: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        x = (pixels - self.mean) / self.std
        c2 = self.c2(x)
        c3 = self.c3(c2)
        c4 = self.c4(c3)
        c5 = self.c5(c4)
        p = self.l5(c5)
        p = self.l4(c4) + F.interpolate(p, scale_factor=2.0, mode="nearest")
        p = self.l3(c3) + F.interpolate(p, scale_factor=2.0, mode="nearest")
        p = self.l2(c2) + F.interpolate(p, scale_factor=2.0, mode="nearest")
        return self.smooth(p), c5


class ScreenNetwork(nn.Module):
    def __init__(self, width: int = 96) -> None:
        super().__init__()
        self.features = FeaturePyramid(width)
        self.heat = nn.Sequential(_conv(width, width), nn.Conv2d(width, 1, 1))
        self.offsets = nn.Sequential(_conv(width, width), nn.Conv2d(width, 8, 1))
        heat_out = cast(nn.Conv2d, self.heat[-1])
        assert heat_out.bias is not None
        nn.init.constant_(heat_out.bias, -math.log((1 - 0.1) / 0.1))

    def forward(self, pixels: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        features, _ = self.features(pixels)
        return self.heat(features), self.offsets(features)


class BoardNetwork(nn.Module):
    def __init__(self, stride: int = 4, width: int = 96) -> None:
        super().__init__()
        self.stride = stride
        self.features = FeaturePyramid(width)
        self.nodes = nn.Sequential(_conv(width, width), nn.Conv2d(width, 24, 1))
        self.visibility = nn.Linear(960, 15)

    def forward(self, crops: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Node logits (N, 24, h, w), nodes in crop pixels (N, 24, 2), visibility logits."""

        features, c5 = self.features(crops)
        logits = self.nodes(features).float()
        nodes = soft_argmax(logits, self.stride)
        visibility = self.visibility(c5.float().mean(dim=(2, 3)))
        return logits, nodes, visibility


def soft_argmax(logits: torch.Tensor, stride: int) -> torch.Tensor:
    batch, channels, height, width = logits.shape
    probability = torch.softmax(logits.reshape(batch, channels, height * width), dim=-1)
    probability = probability.reshape(batch, channels, height, width)
    xs = (torch.arange(width, device=logits.device, dtype=logits.dtype) + 0.5) * stride
    ys = (torch.arange(height, device=logits.device, dtype=logits.dtype) + 0.5) * stride
    x = (probability.sum(dim=2) * xs).sum(dim=-1)
    y = (probability.sum(dim=3) * ys).sum(dim=-1)
    return torch.stack([x, y], dim=-1)


class NeuralGridNetwork(nn.Module):
    def __init__(self, stride: int = 4) -> None:
        super().__init__()
        self.screen = ScreenNetwork()
        self.board = BoardNetwork(stride)


class ScreenExport(nn.Module):
    """ONNX graph of the screen stage: probabilities, not logits."""

    def __init__(self, screen: ScreenNetwork) -> None:
        super().__init__()
        self.screen = screen

    def forward(self, pixels: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        heat, offsets = self.screen(pixels)
        return torch.sigmoid(heat), offsets


class BoardExport(nn.Module):
    def __init__(self, board: BoardNetwork) -> None:
        super().__init__()
        self.board = board

    def forward(self, crops: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        logits, nodes, visibility = self.board(crops)
        batch, channels = logits.shape[:2]
        peak = torch.softmax(logits.reshape(batch, channels, -1), dim=-1).amax(dim=-1)
        return nodes, peak, torch.sigmoid(visibility)


# --- losses ------------------------------------------------------------------------------------


def focal_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """CenterNet penalty-reduced focal loss (alpha 2, beta 4), normalized by positives."""

    logits = logits.float()
    probability = torch.sigmoid(logits).clamp(1e-4, 1 - 1e-4)
    positive = target.ge(0.999).float()
    negative_weight = torch.pow(1 - target, 4)
    positive_loss = torch.log(probability) * torch.pow(1 - probability, 2) * positive
    negative_loss = (
        torch.log(1 - probability) * torch.pow(probability, 2) * negative_weight * (1 - positive)
    )
    count = positive.sum().clamp(min=1.0)
    return -(positive_loss.sum() + negative_loss.sum()) / count


def offset_loss(offsets: torch.Tensor, target: torch.Tensor, weight: torch.Tensor) -> torch.Tensor:
    error = (offsets.float() - target).abs() * weight
    return error.sum() / (weight.sum() * 8).clamp(min=1.0)


def node_heatmap_loss(
    logits: torch.Tensor, nodes: torch.Tensor, stride: int, sigma: float
) -> torch.Tensor:
    """Cross-entropy between the node softmax and a normalized Gaussian at the target."""

    batch, channels, height, width = logits.shape
    xs = torch.arange(width, device=logits.device, dtype=torch.float32) + 0.5
    ys = torch.arange(height, device=logits.device, dtype=torch.float32) + 0.5
    target_x = (nodes[..., 0] / stride)[..., None, None]
    target_y = (nodes[..., 1] / stride)[..., None, None]
    gaussian = torch.exp(
        -((xs.view(1, 1, 1, width) - target_x) ** 2 + (ys.view(1, 1, height, 1) - target_y) ** 2)
        / (2 * sigma**2)
    )
    gaussian = gaussian / gaussian.sum(dim=(2, 3), keepdim=True).clamp(min=1e-6)
    log_probability = torch.log_softmax(logits.float().reshape(batch, channels, -1), dim=-1)
    return -(gaussian.reshape(batch, channels, -1) * log_probability).sum(dim=-1).mean()


def parameter_count(module: nn.Module) -> int:
    return sum(parameter.numel() for parameter in module.parameters())
