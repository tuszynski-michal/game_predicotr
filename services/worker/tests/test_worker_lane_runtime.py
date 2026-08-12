from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID

from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_worker.jobs.lane_runtime import WorkerLaneHeartbeat


class RecordingStore:
    def __init__(self) -> None:
        self.registered = Event()
        self.heartbeat_recorded = Event()
        self.stopped = Event()
        self.token: UUID | None = None

    def register(self, **values: object) -> None:
        self.token = values["instance_token"]  # type: ignore[assignment]
        self.registered.set()

    def heartbeat(self, **values: object) -> bool:
        assert values["instance_token"] == self.token
        self.heartbeat_recorded.set()
        return True

    def stop(self, **values: object) -> bool:
        assert values["instance_token"] == self.token
        self.stopped.set()
        return True


class StepClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 5, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(milliseconds=1)
        return self.value


def test_lane_heartbeat_runs_while_no_job_is_claimed_and_stops_cleanly() -> None:
    store = RecordingStore()
    heartbeat = WorkerLaneHeartbeat(
        store,
        lane=WorkerLaneName.IMAGE_SELECTION,
        worker_id="selection-worker",
        worker_version="worker-v10-image-selection",
        process_id=123,
        thread_budget=4,
        interval_seconds=0.01,
        clock=StepClock(),
    )

    heartbeat.start()
    assert store.registered.wait(timeout=0.2)
    assert store.heartbeat_recorded.wait(timeout=0.2)
    heartbeat.stop()

    assert store.stopped.is_set()
