"""Epoch orchestration with durable control supplied by the caller."""

from collections.abc import Callable, Iterable
from typing import Protocol


class TrainingInterrupted(RuntimeError):
    """The completed-epoch checkpoint remains authoritative."""


class TrainingControl(Protocol):
    def before_batch(self) -> None: ...
    def after_batch(self) -> None: ...
    def checkpoint(self, content: bytes, epoch: int) -> None: ...
    def cancellation_requested(self) -> bool: ...


def train_epochs(
    *,
    start_epoch: int,
    epochs: int,
    batches: Callable[[int], Iterable[object]],
    train_batch: Callable[[object], None],
    finish_epoch: Callable[[int], None],
    serialize_checkpoint: Callable[[int], bytes],
    control: TrainingControl,
) -> int:
    """No sampler replay claims: interrupted epochs restart from the last completed one."""
    control.checkpoint(serialize_checkpoint(start_epoch), start_epoch)
    if control.cancellation_requested():
        raise TrainingInterrupted("RUN_CANCELLED")
    for epoch in range(start_epoch + 1, epochs + 1):
        for batch in batches(epoch):
            control.before_batch()
            train_batch(batch)
            control.after_batch()
        finish_epoch(epoch)
        control.checkpoint(serialize_checkpoint(epoch), epoch)
        if control.cancellation_requested():
            raise TrainingInterrupted("RUN_CANCELLED")
    return epochs
