"""Versioned deterministic appearance variation, without new labels or samples."""

import hashlib
import random

import torch
from torchvision.transforms import functional  # type: ignore[import-untyped]

from game_predictor_worker.images.symbol_model_benchmark import augment_training_tensor

VERSION = "symbol-light-payline-v1"


def augment(tensor: torch.Tensor, sample_id: str, *, seed: int, epoch: int) -> torch.Tensor:
    if epoch < 1 or tensor.shape != (3, 64, 64) or not torch.isfinite(tensor).all():
        raise ValueError("SYMBOL_AUGMENTATION_INPUT_INVALID")
    binding = f"{VERSION}:{sample_id}:{seed}:{epoch}".encode()
    rng = random.Random(int.from_bytes(hashlib.sha256(binding).digest(), "big"))
    base = augment_training_tensor(tensor, sample_id, seed=seed, epoch=epoch)
    pixels = base.add(1).div(2).clamp(0, 1)
    pixels = functional.adjust_gamma(pixels, rng.uniform(0.65, 1.6))
    pixels = functional.adjust_brightness(pixels, rng.uniform(0.65, 1.5))
    pixels = functional.adjust_contrast(pixels, rng.uniform(0.7, 1.3))
    pixels = functional.adjust_saturation(pixels, rng.uniform(0.1, 1.5))
    pixels = functional.adjust_hue(pixels, rng.uniform(-0.12, 0.12))
    if rng.randrange(3) == 0:
        # Thin translucent overlays vary in location; never erase a complete glyph.
        yy, xx = torch.meshgrid(
            torch.arange(64, device=pixels.device),
            torch.arange(64, device=pixels.device),
            indexing="ij",
        )
        color = pixels.new_tensor([0.05, 0.95, 0.2]).reshape(3, 1, 1)
        for _ in range(rng.randint(1, 2)):
            centre, slope = rng.uniform(12, 52), rng.uniform(-0.12, 0.12)
            thickness, alpha = rng.randint(1, 3), rng.uniform(0.25, 0.7)
            mask = (yy - centre - slope * (xx - 32)).abs() <= thickness / 2
            pixels = torch.where(mask.unsqueeze(0), (1 - alpha) * pixels + alpha * color, pixels)
    return pixels.clamp(0, 1).mul(2).sub(1)
