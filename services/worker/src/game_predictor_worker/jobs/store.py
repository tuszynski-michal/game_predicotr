"""PostgreSQL-backed fenced lease operations for the local worker."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    acknowledge_job_cancellation,
    checkpoint_job,
    complete_job,
    fail_job,
    recover_expired_job,
    renew_job_lease,
    start_job,
    wait_for_review,
)
from game_predictor_api.storage.job_repository import (
    apply_job_to_record,
    job_from_record,
)
from game_predictor_api.storage.models import JobModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


class SqlAlchemyWorkerJobStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def claim_next(
        self,
        *,
        worker_id: str,
        worker_version: str,
        lease_duration: timedelta,
        claimed_at: datetime,
    ) -> Job | None:
        _validate_lease_duration(lease_duration)
        with self._session_factory() as session:
            try:
                with session.begin():
                    self._recover_one_expired(session, recovered_at=claimed_at)
                    active = session.scalar(
                        select(JobModel.id).where(
                            JobModel.status == JobStatus.PROCESSING
                        )
                    )
                    if active is not None:
                        return None
                    record = session.scalar(
                        select(JobModel)
                        .where(JobModel.status == JobStatus.CREATED)
                        .order_by(JobModel.created_at, JobModel.id)
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    if record is None:
                        return None
                    claimed = start_job(
                        job_from_record(record),
                        worker_version=worker_version,
                        worker_id=worker_id,
                        lease_token=uuid4(),
                        lease_expires_at=claimed_at + lease_duration,
                        started_at=claimed_at,
                    )
                    apply_job_to_record(record, claimed)
                    session.flush()
                    return claimed
            except IntegrityError as error:
                session.rollback()
                if _constraint_name(error) == "uq_jobs_execution_slot":
                    return None
                raise

    def heartbeat(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        lease_duration: timedelta,
        heartbeat_at: datetime,
    ) -> Job:
        _validate_lease_duration(lease_duration)
        with self._session_factory() as session, session.begin():
            record = _locked_job(session, job_id)
            updated = renew_job_lease(
                job_from_record(record),
                lease_token=lease_token,
                lease_expires_at=heartbeat_at + lease_duration,
                heartbeat_at=heartbeat_at,
            )
            apply_job_to_record(record, updated)
            session.flush()
            return updated

    def checkpoint(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        lease_duration: timedelta,
        checkpoint_payload: dict[str, object],
        stage: str,
        current: int,
        total: int | None,
        success_count: int,
        failure_count: int,
        review_count: int,
        checkpointed_at: datetime,
    ) -> Job:
        _validate_lease_duration(lease_duration)
        with self._session_factory() as session, session.begin():
            record = _locked_job(session, job_id)
            renewed = renew_job_lease(
                job_from_record(record),
                lease_token=lease_token,
                lease_expires_at=checkpointed_at + lease_duration,
                heartbeat_at=checkpointed_at,
            )
            updated = checkpoint_job(
                renewed,
                lease_token=lease_token,
                checkpoint_payload=checkpoint_payload,
                stage=stage,
                current=current,
                total=total,
                success_count=success_count,
                failure_count=failure_count,
                review_count=review_count,
                updated_at=checkpointed_at,
            )
            if updated.cancel_requested_at is not None:
                updated = acknowledge_job_cancellation(
                    updated,
                    lease_token=lease_token,
                    finished_at=checkpointed_at,
                )
            apply_job_to_record(record, updated)
            session.flush()
            return updated

    def complete(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        completed_at: datetime,
    ) -> Job:
        with self._session_factory() as session, session.begin():
            record = _locked_job(session, job_id)
            job = job_from_record(record)
            updated = (
                acknowledge_job_cancellation(
                    job,
                    lease_token=lease_token,
                    finished_at=completed_at,
                )
                if job.cancel_requested_at is not None
                else complete_job(
                    job,
                    lease_token=lease_token,
                    finished_at=completed_at,
                )
            )
            apply_job_to_record(record, updated)
            session.flush()
            return updated

    def fail(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        error_code: str,
        error_message: str,
        failed_at: datetime,
    ) -> Job:
        with self._session_factory() as session, session.begin():
            record = _locked_job(session, job_id)
            job = job_from_record(record)
            updated = (
                acknowledge_job_cancellation(
                    job,
                    lease_token=lease_token,
                    finished_at=failed_at,
                )
                if job.cancel_requested_at is not None
                else fail_job(
                    job,
                    lease_token=lease_token,
                    error_code=error_code,
                    error_message=error_message,
                    finished_at=failed_at,
                )
            )
            apply_job_to_record(record, updated)
            session.flush()
            return updated

    def pause_for_review(
        self,
        job_id: UUID,
        *,
        lease_token: UUID,
        paused_at: datetime,
    ) -> Job:
        with self._session_factory() as session, session.begin():
            record = _locked_job(session, job_id)
            job = job_from_record(record)
            updated = (
                acknowledge_job_cancellation(
                    job,
                    lease_token=lease_token,
                    finished_at=paused_at,
                )
                if job.cancel_requested_at is not None
                else wait_for_review(
                    job,
                    lease_token=lease_token,
                    updated_at=paused_at,
                )
            )
            apply_job_to_record(record, updated)
            session.flush()
            return updated

    def recover_expired(self, *, recovered_at: datetime) -> Job | None:
        with self._session_factory() as session, session.begin():
            return self._recover_one_expired(
                session,
                recovered_at=recovered_at,
            )

    @staticmethod
    def _recover_one_expired(
        session: Session,
        *,
        recovered_at: datetime,
    ) -> Job | None:
        record = session.scalar(
            select(JobModel)
            .where(
                JobModel.status == JobStatus.PROCESSING,
                JobModel.lease_expires_at <= recovered_at,
            )
            .order_by(JobModel.lease_expires_at, JobModel.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if record is None:
            return None
        recovered = recover_expired_job(
            job_from_record(record),
            recovered_at=recovered_at,
        )
        apply_job_to_record(record, recovered)
        session.flush()
        return recovered


def _locked_job(session: Session, job_id: UUID) -> JobModel:
    record = session.scalar(
        select(JobModel)
        .where(JobModel.id == job_id)
        .with_for_update()
    )
    if record is None:
        raise JobConflictError(
            "JOB_NOT_FOUND",
            "Job no longer exists.",
            details={"jobId": str(job_id)},
        )
    return record


def _validate_lease_duration(lease_duration: timedelta) -> None:
    if lease_duration <= timedelta(0):
        raise ValueError("lease_duration must be positive.")


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return diagnostic.constraint_name if diagnostic is not None else None
