"""Frozen ImageNet MobileNet features and a trainable geometric residual head."""

from pathlib import Path
from typing import cast

import torch
from torch import nn
from torchvision.models import mobilenet_v3_small  # type: ignore[import-untyped]


class HybridNetwork(nn.Module):
    def __init__(self, weights: Path | None) -> None:
        super().__init__()
        backbone = mobilenet_v3_small(weights=None)
        if weights is not None:
            backbone.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        self.features = backbone.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        output = nn.Linear(128, 8)
        self.head = nn.Sequential(nn.Linear(576, 128), nn.Hardswish(), output)
        nn.init.zeros_(output.weight)
        nn.init.zeros_(output.bias)
        self.features.requires_grad_(False)
        self.features.eval()

    def train(self, mode: bool = True) -> "HybridNetwork":
        super().train(mode)
        self.features.eval()
        return self

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self.head(self.pool(self.features(pixels)).flatten(1)))
