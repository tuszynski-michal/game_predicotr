"""PostgreSQL persistence for local worker-lane heartbeats."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.worker_lanes import WorkerLaneName, WorkerLaneRuntime
from game_predictor_api.storage.models import WorkerLaneRuntimeModel


class SqlAlchemyWorkerLaneRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

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
    ) -> None:
        with self._session_factory() as session, session.begin():
            statement = insert(WorkerLaneRuntimeModel).values(
                lane=lane,
                instance_token=instance_token,
                worker_id=worker_id,
                worker_version=worker_version,
                process_id=process_id,
                thread_budget=thread_budget,
                started_at=started_at,
                heartbeat_at=started_at,
                stopped_at=None,
                updated_at=started_at,
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[WorkerLaneRuntimeModel.lane],
                    set_={
                        "instance_token": statement.excluded.instance_token,
                        "worker_id": statement.excluded.worker_id,
                        "worker_version": statement.excluded.worker_version,
                        "process_id": statement.excluded.process_id,
                        "thread_budget": statement.excluded.thread_budget,
                        "started_at": statement.excluded.started_at,
                        "heartbeat_at": statement.excluded.heartbeat_at,
                        "stopped_at": None,
                        "updated_at": statement.excluded.updated_at,
                    },
                )
            )

    def heartbeat(
        self,
        *,
        lane: WorkerLaneName,
        instance_token: UUID,
        heartbeat_at: datetime,
    ) -> bool:
        with self._session_factory() as session, session.begin():
            updated_lane = session.scalar(
                update(WorkerLaneRuntimeModel)
                .where(
                    WorkerLaneRuntimeModel.lane == lane,
                    WorkerLaneRuntimeModel.instance_token == instance_token,
                    WorkerLaneRuntimeModel.stopped_at.is_(None),
                )
                .values(heartbeat_at=heartbeat_at, updated_at=heartbeat_at)
                .returning(WorkerLaneRuntimeModel.lane)
            )
            return updated_lane is not None

    def stop(
        self,
        *,
        lane: WorkerLaneName,
        instance_token: UUID,
        stopped_at: datetime,
    ) -> bool:
        with self._session_factory() as session, session.begin():
            updated_lane = session.scalar(
                update(WorkerLaneRuntimeModel)
                .where(
                    WorkerLaneRuntimeModel.lane == lane,
                    WorkerLaneRuntimeModel.instance_token == instance_token,
                )
                .values(
                    heartbeat_at=stopped_at,
                    stopped_at=stopped_at,
                    updated_at=stopped_at,
                )
                .returning(WorkerLaneRuntimeModel.lane)
            )
            return updated_lane is not None

    def list(self) -> tuple[WorkerLaneRuntime, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(WorkerLaneRuntimeModel).order_by(WorkerLaneRuntimeModel.lane)
            ).all()
            return tuple(_from_record(record) for record in records)


def _from_record(record: WorkerLaneRuntimeModel) -> WorkerLaneRuntime:
    return WorkerLaneRuntime(
        lane=record.lane,
        instance_token=record.instance_token,
        worker_id=record.worker_id,
        worker_version=record.worker_version,
        process_id=record.process_id,
        thread_budget=record.thread_budget,
        started_at=record.started_at,
        heartbeat_at=record.heartbeat_at,
        stopped_at=record.stopped_at,
    )
