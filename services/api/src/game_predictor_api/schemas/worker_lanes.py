"""OpenAPI schemas for worker-lane health."""

from datetime import datetime

from game_predictor_api.domain.worker_lanes import WorkerLaneName, WorkerLaneState, WorkerLaneStatus
from game_predictor_api.schemas.catalog import ApiModel


class WorkerLaneStatusResponse(ApiModel):
    lane: WorkerLaneName
    state: WorkerLaneState
    worker_version: str | None
    thread_budget: int | None
    started_at: datetime | None
    heartbeat_at: datetime | None

    @classmethod
    def from_domain(cls, status: WorkerLaneStatus) -> "WorkerLaneStatusResponse":
        return cls(
            lane=status.lane,
            state=status.state,
            worker_version=status.worker_version,
            thread_budget=status.thread_budget,
            started_at=status.started_at,
            heartbeat_at=status.heartbeat_at,
        )
