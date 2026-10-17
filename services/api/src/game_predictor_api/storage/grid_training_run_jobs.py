"""Job storage for grid-training runs with an exact, serialized idempotency key (TASK-0996)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, text

from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import JobModel


class SqlAlchemyGridTrainingRunJobs(SqlAlchemyJobRepository):
    def lock_idempotency(self, key: UUID) -> None:
        """Serialize every create with one key until the request transaction ends."""
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"),
            {"name": f"grid-training-run:{key}"},
        )

    def find_by_idempotency(self, key: UUID) -> Job | None:
        record = self._session.scalar(
            select(JobModel)
            .where(
                JobModel.job_type == JobType.GRID_TRAINING,
                func.jsonb_extract_path_text(JobModel.input_payload, "idempotency_key") == str(key),
            )
            .limit(1)
        )
        return None if record is None else job_from_record(record)
