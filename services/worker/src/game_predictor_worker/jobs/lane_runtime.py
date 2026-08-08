"""Independent heartbeat for a local worker process, including idle time."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, Thread
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_api.domain.worker_lanes import WorkerLaneName

LOGGER = logging.getLogger(__name__)
DEFAULT_LANE_HEARTBEAT_INTERVAL_SECONDS = 5.0


class WorkerLaneHeartbeatStore(Protocol):
    def register(
        self,
        *,
        lane: WorkerLaneName,
        instance_token: UUID,
        worker_id: str,
        worker_version: str,
        process_id: int,
        thread_budget: int,
        started_at: datetime,
    ) -> None: ...

    def heartbeat(
        self,
        *,
        lane: WorkerLaneName,
        instance_token: UUID,
        heartbeat_at: datetime,
    ) -> bool: ...

    def stop(
        self,
        *,
        lane: WorkerLaneName,
        instance_token: UUID,
        stopped_at: datetime,
    ) -> bool: ...


class WorkerLaneHeartbeat:
    def __init__(
        self,
        store: WorkerLaneHeartbeatStore,
        *,
        lane: WorkerLaneName,
        worker_id: str,
        worker_version: str,
        process_id: int,
        thread_budget: int,
        interval_seconds: float = DEFAULT_LANE_HEARTBEAT_INTERVAL_SECONDS,
        clock: Callable[[], datetime] | None = None,
        instance_token: UUID | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive.")
        if not 1 <= thread_budget <= 64:
            raise ValueError("thread_budget must be between 1 and 64.")
        self._store = store
        self._lane = lane
        self._worker_id = worker_id
        self._worker_version = worker_version
        self._process_id = process_id
        self._thread_budget = thread_budget
        self._interval_seconds = interval_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._instance_token = instance_token or uuid4()
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def instance_token(self) -> UUID:
        return self._instance_token

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Worker lane heartbeat is already started.")
        started_at = self._clock()
        self._store.register(
            lane=self._lane,
            instance_token=self._instance_token,
            worker_id=self._worker_id,
            worker_version=self._worker_version,
            process_id=self._process_id,
            thread_budget=self._thread_budget,
            started_at=started_at,
        )
        self._thread = Thread(
            target=self._run,
            name=f"worker-lane-heartbeat-{self._lane.value}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds + 1.0))
            self._thread = None
        try:
            self._store.stop(
                lane=self._lane,
                instance_token=self._instance_token,
                stopped_at=self._clock(),
            )
        except Exception:
            LOGGER.exception("Failed to persist worker lane shutdown.")

    def __enter__(self) -> WorkerLaneHeartbeat:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                current = self._store.heartbeat(
                    lane=self._lane,
                    instance_token=self._instance_token,
                    heartbeat_at=self._clock(),
                )
                if not current:
                    LOGGER.warning(
                        "Worker lane heartbeat was fenced by a newer process: %s",
                        self._lane.value,
                    )
                    return
            except Exception:
                LOGGER.exception("Failed to persist worker lane heartbeat.")
