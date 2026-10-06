"""Torch-free equivalent of the frozen RGB96 -> RGB64 lab inference transform."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

LAB_RGB_PREPROCESSING_VERSION = "rgb96-bilinear-antialias64-float32-v1"
LAB_RGB_CROP_SIZE = 96
LAB_RGB_INPUT_SIZE = 64
MAX_LAB_RGB_BATCH = 256


def _weights() -> NDArray[np.float32]:
    scale = np.float32(1.5)
    weights: NDArray[np.float32] = np.zeros(
        (LAB_RGB_INPUT_SIZE, LAB_RGB_CROP_SIZE), dtype=np.float32
    )
    for index in range(LAB_RGB_INPUT_SIZE):
        center = np.float32((index + 0.5) * scale)
        for position in range(LAB_RGB_CROP_SIZE):
            weights[index, position] = np.maximum(
                np.float32(0),
                np.float32(1) - abs((np.float32(position + 0.5) - center) / scale),
            )
        weights[index] /= weights[index].sum(dtype=np.float32)
    return weights


_RESIZE_WEIGHTS = _weights()


def preprocess_lab_rgb96(
    images: Sequence[NDArray[np.uint8]],
) -> NDArray[np.float32]:
    """Retain the float interpolation, antialiasing and normalization used in R2.

    This accepts exact RGB96 render output. It never resizes an already altered
    RGB64 crop or clips a partial source into a different training identity.
    """
    if not 1 <= len(images) <= MAX_LAB_RGB_BATCH or any(
        not isinstance(image, np.ndarray)
        or image.dtype != np.uint8
        or image.shape != (LAB_RGB_CROP_SIZE, LAB_RGB_CROP_SIZE, 3)
        for image in images
    ):
        raise ValueError("LAB_RGB_CROP_CONTRACT_INVALID")
    source = np.stack(images).transpose(0, 3, 1, 2).astype(np.float32)
    horizontal = np.einsum("oi,bchi->bcho", _RESIZE_WEIGHTS, source, optimize=False)
    output: NDArray[np.float32] = np.einsum(
        "oi,bciw->bcow", _RESIZE_WEIGHTS, horizontal, optimize=False
    )
    return (output / np.float32(255) - np.float32(0.5)) / np.float32(0.5)
