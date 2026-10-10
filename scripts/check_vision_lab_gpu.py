"""Fresh-process CUDA verification; no data or model training."""

import importlib.util
import json
import sys

import torch

torchvision = importlib.import_module("torchvision")

if torch.__version__ != "2.12.1+cu130" or torchvision.__version__ != "0.27.1+cu130":
    raise RuntimeError("VISION_LAB_CUDA_VERSION_MISMATCH")
if torch.version.cuda != "13.0" or not torch.cuda.is_available():
    raise RuntimeError("VISION_LAB_GPU_UNAVAILABLE")
values = torch.tensor([2.0, 3.0], device="cuda")
result = float((values * values).sum().item())
torch.cuda.synchronize()
assert result == 13.0
assert all(importlib.util.find_spec(name) is None for name in ("psycopg", "paddle", "sqlalchemy"))
print(
    json.dumps(
        {
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(0),
            "result": result,
            "python": sys.executable,
            "database_packages_present": False,
        }
    )
)
