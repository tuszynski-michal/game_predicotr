"""Closed model registry and the only laboratory bridge to neutral epoch training."""

from collections.abc import Callable
from typing import Any

from .run_contracts import StartRunRequest
from .runs import RunManager, Token
from .training_manifest import TrainingInputs


class RunControl:
    def __init__(self, manager: RunManager, run_id: str, lease: Token) -> None:
        self.manager, self.run_id, self.lease = manager, run_id, lease

    def before_batch(self) -> None:
        self.manager.heartbeat(self.run_id, self.lease, reserve_step=True)

    def after_batch(self) -> None:
        self.manager.heartbeat(self.run_id, self.lease)

    def checkpoint(self, content: bytes, epoch: int) -> None:
        self.manager.checkpoint(self.run_id, self.lease, content, epoch)

    def cancellation_requested(self) -> bool:
        return self.manager.detail(self.run_id).cancel_requested


Trainer = Callable[[TrainingInputs, StartRunRequest, RunControl], dict[str, Any]]


def _hybrid(
    inputs: TrainingInputs, request: StartRunRequest, control: RunControl
) -> dict[str, Any]:
    from .hybrid_training import train

    return train(inputs, request, control)


# Lazy registry: API/ORT inference must not import torch merely to discover models.
TRAINERS: dict[str, Trainer] = {"hybrid-mobilenet-v1": _hybrid}


def train_from_manifest(
    inputs: TrainingInputs,
    request: StartRunRequest,
    control: RunControl,
) -> dict[str, Any]:
    if request.model_version not in TRAINERS:
        raise ValueError("RUN_MODEL_NOT_AVAILABLE")
    return TRAINERS[request.model_version](inputs, request, control)
