"""Read model for local worker-lane health."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from game_predictor_api.domain.worker_lanes import (
    WorkerLaneName,
    WorkerLaneRuntime,
    WorkerLaneState,
    WorkerLaneStatus,
)

DEGRADED_AFTER = timedelta(seconds=15)
STOPPED_AFTER = timedelta(seconds=60)


class WorkerLaneStatusRepository(Protocol):
    def list(self) -> Sequence[WorkerLaneRuntime]: ...


class WorkerLaneStatusService:
    def __init__(
        self,
        repository: WorkerLaneStatusRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_statuses(self) -> tuple[WorkerLaneStatus, ...]:
        now = self._clock()
        records = {record.lane: record for record in self._repository.list()}
        return tuple(
            self._status(lane, records.get(lane), now)
            for lane in WorkerLaneName
        )

    @staticmethod
    def _status(
        lane: WorkerLaneName,
        record: WorkerLaneRuntime | None,
        now: datetime,
    ) -> WorkerLaneStatus:
        if record is None or record.stopped_at is not None:
            state = WorkerLaneState.STOPPED
        else:
            age = max(timedelta(0), now - record.heartbeat_at)
            if age <= DEGRADED_AFTER:
                state = WorkerLaneState.RUNNING
            elif age <= STOPPED_AFTER:
                state = WorkerLaneState.DEGRADED
            else:
                state = WorkerLaneState.STOPPED
        return WorkerLaneStatus(
            lane=lane,
            state=state,
            worker_version=None if record is None else record.worker_version,
            thread_budget=None if record is None else record.thread_budget,
            started_at=None if record is None else record.started_at,
            heartbeat_at=None if record is None else record.heartbeat_at,
        )
