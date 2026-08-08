"""Domain values for local worker-lane observability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class WorkerLaneName(StrEnum):
    GENERAL = "general"
    IMAGE_SELECTION = "image_selection"


class WorkerLaneState(StrEnum):
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class WorkerLaneRuntime:
    lane: WorkerLaneName
    instance_token: UUID
    worker_id: str
    worker_version: str
    process_id: int
    thread_budget: int
    started_at: datetime
    heartbeat_at: datetime
    stopped_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkerLaneStatus:
    lane: WorkerLaneName
    state: WorkerLaneState
    worker_version: str | None
    thread_budget: int | None
    started_at: datetime | None
    heartbeat_at: datetime | None
