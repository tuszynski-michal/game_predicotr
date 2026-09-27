"""Checksum-first checkpoints. Exact continuation is defined at epoch boundaries."""

import hashlib
import io
import os
import random
import tempfile
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn


def capture_rng(generator: torch.Generator) -> dict[str, Any]:
    numpy_state: Any = np.random.get_state()
    return {
        "python": random.getstate(),
        "numpy": [numpy_state[0], numpy_state[1].tolist(), *numpy_state[2:]],
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
        "loader": generator.get_state(),
    }


def restore_rng(state: dict[str, Any], generator: torch.Generator) -> None:
    random.setstate(state["python"])
    value = state["numpy"]
    np.random.set_state((value[0], np.asarray(value[1], dtype=np.uint32), *value[2:]))
    torch.set_rng_state(state["torch"])
    if state["cuda"]:
        if not torch.cuda.is_available() or len(state["cuda"]) != torch.cuda.device_count():
            raise ValueError("CHECKPOINT_CUDA_RUNTIME_MISMATCH")
        torch.cuda.set_rng_state_all(state["cuda"])
    generator.set_state(state["loader"])


def make_checkpoint(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    generator: torch.Generator,
    *,
    binding: dict[str, Any],
    epoch: int,
    global_step: int,
    history: list[dict[str, Any]],
    best_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "resumeMode": "completed_epoch",
        "cursor": 0,
        "epoch": epoch,
        "globalStep": global_step,
        "binding": binding,
        "modelState": model.state_dict(),
        "optimizerState": optimizer.state_dict(),
        "schedulerState": scheduler.state_dict() if scheduler is not None else None,
        "rng": capture_rng(generator),
        "history": history,
        "bestState": best_state,
    }


def checkpoint_bytes(value: dict[str, Any]) -> bytes:
    stream = io.BytesIO()
    torch.save(value, stream)
    return stream.getvalue()


def write_checkpoint(directory: Path, value: dict[str, Any]) -> tuple[Path, str]:
    """Create immutable bytes; publication of a run pointer is the caller's fenced operation."""
    content = checkpoint_bytes(value)
    checksum = hashlib.sha256(content).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{checksum}.pt"
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".checkpoint-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            if destination.read_bytes() != content:
                raise ValueError("CHECKPOINT_ARTIFACT_CONFLICT")
        else:
            os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, checksum


def load_checkpoint(
    path: Path, expected_sha256: str, *, expected_binding: dict[str, Any] | None = None
) -> dict[str, Any]:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("CHECKPOINT_CHECKSUM_MISMATCH")
    value = torch.load(io.BytesIO(content), map_location="cpu", weights_only=True)
    if not isinstance(value, dict) or not isinstance(value.get("modelState"), dict):
        raise ValueError("CHECKPOINT_INVALID")
    version = value.get("schemaVersion")
    if version == 1:
        warnings.warn(
            "Checkpoint v1 has no complete RNG/config binding; continuation is not exact, "
            "and best model weights may differ from the optimizer epoch.",
            RuntimeWarning,
            stacklevel=2,
        )
        if expected_binding and value.get("inputFingerprint") != expected_binding.get(
            "inputFingerprint"
        ):
            raise ValueError("CHECKPOINT_BINDING_MISMATCH")
        return {**value, "resumeMode": "legacy_approximate"}
    required = {
        "binding",
        "optimizerState",
        "schedulerState",
        "rng",
        "epoch",
        "globalStep",
        "history",
    }
    if (
        version != 2
        or not required <= value.keys()
        or value.get("resumeMode") != "completed_epoch"
        or value.get("cursor") != 0
        or (expected_binding is not None and value["binding"] != expected_binding)
    ):
        raise ValueError("CHECKPOINT_BINDING_MISMATCH")
    if (
        not isinstance(value["binding"], dict)
        or not isinstance(value["optimizerState"], dict)
        or not {"state", "param_groups"} <= value["optimizerState"].keys()
        or not isinstance(value["history"], list)
        or type(value["epoch"]) is not int
        or value["epoch"] < 0
        or type(value["globalStep"]) is not int
        or value["globalStep"] < 0
        or (value["schedulerState"] is not None and not isinstance(value["schedulerState"], dict))
    ):
        raise ValueError("CHECKPOINT_INVALID")
    try:
        rng = value["rng"]
        random.Random().setstate(rng["python"])
        numpy_rng = rng["numpy"]
        np.random.RandomState().set_state(
            (numpy_rng[0], np.asarray(numpy_rng[1], dtype=np.uint32), *numpy_rng[2:])
        )
        torch.Generator().set_state(rng["torch"])
        torch.Generator().set_state(rng["loader"])
        if not isinstance(rng["cuda"], list) or any(
            not isinstance(item, torch.Tensor) or item.dtype != torch.uint8 or item.ndim != 1
            for item in rng["cuda"]
        ):
            raise ValueError("CHECKPOINT_INVALID")
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise ValueError("CHECKPOINT_RNG_INVALID") from error
    return value


def restore_checkpoint(
    value: dict[str, Any],
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    generator: torch.Generator,
) -> None:
    model.load_state_dict(value["modelState"])
    optimizer.load_state_dict(value["optimizerState"])
    if value["schemaVersion"] == 2:
        if (scheduler is None) != (value["schedulerState"] is None):
            raise ValueError("CHECKPOINT_SCHEDULER_MISMATCH")
        if scheduler is not None:
            scheduler.load_state_dict(value["schedulerState"])
        restore_rng(value["rng"], generator)
