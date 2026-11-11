"""FP32 evaluation independent of CUDA's process-wide training precision defaults."""

from collections.abc import Iterator
from contextlib import contextmanager

import torch

EVALUATION_PRECISION = "torch-fp32-no-tf32-v1"


@contextmanager
def evaluation_precision() -> Iterator[None]:
    """Disable TF32 and autocast for inference, restoring training settings on failure."""
    cudnn = torch.backends.cudnn.allow_tf32
    matmul = torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        with torch.autocast("cuda", enabled=False), torch.autocast("cpu", enabled=False):
            yield
    finally:
        torch.backends.cudnn.allow_tf32 = cudnn
        torch.backends.cuda.matmul.allow_tf32 = matmul
