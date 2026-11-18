"""Progress-bounded preparation: no total wall-clock limit for a healthy worker."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import Any

from game_predictor_api.domain.grid_training_cohorts import GridCohortError

from .grid_training_cohort_repository import CohortDeadline

Progress = Callable[[str, int, int | None], None]
PREPARATION_WORKER_CAPABILITY = "grid-preparation-v1"
_active: ContextVar[PreparationDeadline | None] = ContextVar("grid_preparation", default=None)


class PreparationDeadline(CohortDeadline):
    """Each real unit renews the stall budget; heartbeats alone never renew it."""

    def __init__(self, progress: Progress, seconds: float = 300) -> None:
        super().__init__(seconds)
        self.callback = progress
        self.last_unit: tuple[str, int, int | None] | None = None

    def check(self, session: Any = None) -> None:
        if monotonic() >= self.end:
            raise GridCohortError(
                "GRID_PREPARATION_STALLED", "No preparation progress within 300 seconds.", 503
            )
        super().check(session)

    def progress(self, stage: str, current: int, total: int | None) -> None:
        self.check()
        unit = stage, current, total
        if unit != self.last_unit:
            self.last_unit = unit
            self.end = monotonic() + self.seconds
            self.callback(stage, current, total)


@contextmanager
def preparation_progress(progress: Progress) -> Iterator[None]:
    token = _active.set(PreparationDeadline(progress))
    try:
        yield
    finally:
        _active.reset(token)


def preparation_deadline(seconds: float = 300) -> CohortDeadline:
    return _active.get() or CohortDeadline(seconds)


def report_preparation(stage: str, current: int, total: int | None = None) -> None:
    deadline = _active.get()
    if deadline is not None:
        deadline.progress(stage, current, total)
