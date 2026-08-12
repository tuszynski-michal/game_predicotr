from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.worker_lanes import WorkerLaneStatusService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.worker_lanes import WorkerLaneName, WorkerLaneRuntime
from game_predictor_api.main import create_app


class MemoryWorkerLaneRepository:
    def __init__(self, records: tuple[WorkerLaneRuntime, ...] = ()) -> None:
        self.records = records

    def list(self) -> tuple[WorkerLaneRuntime, ...]:
        return self.records


def _runtime(
    lane: WorkerLaneName,
    *,
    now: datetime,
    heartbeat_age_seconds: int,
    stopped: bool = False,
) -> WorkerLaneRuntime:
    started_at = now - timedelta(minutes=5)
    heartbeat_at = now - timedelta(seconds=heartbeat_age_seconds)
    return WorkerLaneRuntime(
        lane=lane,
        instance_token=uuid4(),
        worker_id=f"worker-{lane.value}",
        worker_version=f"worker-v10-{lane.value}",
        process_id=123,
        thread_budget=4 if lane is WorkerLaneName.IMAGE_SELECTION else 2,
        started_at=started_at,
        heartbeat_at=heartbeat_at,
        stopped_at=heartbeat_at if stopped else None,
    )


def test_lane_status_distinguishes_running_degraded_and_stopped() -> None:
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    repository = MemoryWorkerLaneRepository(
        (
            _runtime(
                WorkerLaneName.GENERAL,
                now=now,
                heartbeat_age_seconds=5,
            ),
            _runtime(
                WorkerLaneName.IMAGE_SELECTION,
                now=now,
                heartbeat_age_seconds=30,
            ),
        )
    )

    statuses = WorkerLaneStatusService(repository, clock=lambda: now).list_statuses()

    assert [status.state.value for status in statuses] == ["running", "degraded"]
    repository.records = (
        _runtime(
            WorkerLaneName.GENERAL,
            now=now,
            heartbeat_age_seconds=1,
            stopped=True,
        ),
    )
    statuses = WorkerLaneStatusService(repository, clock=lambda: now).list_statuses()
    assert [status.state.value for status in statuses] == ["stopped", "stopped"]


def test_worker_lane_api_returns_both_lanes_without_process_details(tmp_path) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    service = WorkerLaneStatusService(
        MemoryWorkerLaneRepository(
            (
                _runtime(
                    WorkerLaneName.GENERAL,
                    now=now,
                    heartbeat_age_seconds=5,
                ),
            )
        ),
        clock=lambda: now,
    )
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        worker_lane_status_service_dependency=lambda: service,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/worker-lanes")

    assert response.status_code == 200
    assert response.json() == [
        {
            "lane": "general",
            "state": "running",
            "workerVersion": "worker-v10-general",
            "threadBudget": 2,
            "startedAt": "2026-08-05T11:55:00Z",
            "heartbeatAt": "2026-08-05T11:59:55Z",
        },
        {
            "lane": "image_selection",
            "state": "stopped",
            "workerVersion": None,
            "threadBudget": None,
            "startedAt": None,
            "heartbeatAt": None,
        },
    ]
    assert "processId" not in response.text
    assert "workerId" not in response.text
