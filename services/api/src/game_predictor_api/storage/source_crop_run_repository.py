"""Persistence of source crop runs and their worker jobs (TASK-1047, D-562).

``public.source_crop_runs`` and ``public.jobs`` are shared; a run never binds a
game. The API creates a run with its plan job and later its execute job; the
worker reports the plan and the progress through the same repository. Every
worker write is fenced by the job's current lease token, and every job state
change outside the handler (cancel, failure, retry, lease recovery) reaches the
run atomically through ``synchronize_source_crop_job``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.application.source_crop_runs import (
    SourceCropRun,
    SourceCropRunKind,
    SourceCropScope,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobNotFoundError,
    JobStatus,
    JobType,
    create_job,
)
from game_predictor_api.storage.models import JobModel
from game_predictor_api.storage.source_image_crop_models import SourceCropRunModel

MAX_RECORDED_FAILURES = 100
_ACTIVE = ("planning", "previewed", "created", "processing")
_FINISHED = ("completed", "failed", "cancelled")
SOURCE_CROP_JOB_TYPES = frozenset({JobType.SOURCE_CROP, JobType.SOURCE_ORIGINAL_DELETION})


def job_type_for_kind(kind: str) -> JobType:
    return JobType.SOURCE_CROP if kind == "crop" else JobType.SOURCE_ORIGINAL_DELETION


def source_crop_job_payload(
    run_id: UUID, *, kind: str, phase: str, manifest_checksum_sha256: str | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "source_crop_run_id": str(run_id),
        "kind": kind,
        "phase": phase,
    }
    if manifest_checksum_sha256 is not None:
        payload["manifest_checksum_sha256"] = manifest_checksum_sha256
    return payload


def assert_job_lease(session: Session, job_id: UUID, lease_token: UUID) -> None:
    """Fail closed unless ``lease_token`` still holds ``job_id`` (same transaction)."""

    record = session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())
    if (
        record is None
        or record.status != JobStatus.PROCESSING
        or record.lease_token != lease_token
        or record.lease_expires_at is None
        or record.lease_expires_at <= _now()
    ):
        raise JobConflictError(
            "JOB_LEASE_LOST", "The worker lease no longer permits source crop writes."
        )


class SqlAlchemySourceCropRunRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_planning_run(
        self, *, run_id: UUID, kind: SourceCropRunKind, scope: SourceCropScope
    ) -> SourceCropRun:
        from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository

        try:
            with self._session_factory.begin() as session:
                _supersede_unstarted_preview(session)
                job = create_job(
                    job_type_for_kind(kind),
                    game_id=None,
                    input_payload=source_crop_job_payload(run_id, kind=kind, phase="plan"),
                )
                SqlAlchemyJobRepository(session).add_job(job)
                row = SourceCropRunModel(
                    id=run_id,
                    kind=kind,
                    status="planning",
                    scope=scope.to_payload(),
                    plan_job_id=job.id,
                    job_id=None,
                    exclusion_counts={},
                    outcome_counts={},
                    failures=[],
                    created_at=job.created_at,
                    updated_at=job.created_at,
                )
                session.add(row)
                session.flush()
                result = _run(row)
        except IntegrityError as error:
            if "uq_source_crop_runs_active" in str(error.orig):
                raise JobConflictError(
                    "SOURCE_CROP_RUN_ACTIVE",
                    "Another source crop run is being planned or executed.",
                ) from error
            raise
        return result

    def start_run(
        self,
        *,
        run_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_preview_token: str,
    ) -> SourceCropRun:
        from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository

        with self._session_factory.begin() as session:
            row = session.get(SourceCropRunModel, run_id, with_for_update=True)
            if row is None:
                raise JobNotFoundError(
                    "SOURCE_CROP_RUN_NOT_FOUND", "The source crop run does not exist."
                )
            if (
                row.manifest_checksum_sha256 != expected_manifest_checksum_sha256
                or row.preview_token != expected_preview_token
            ):
                raise JobConflictError(
                    "SOURCE_CROP_PREVIEW_STALE",
                    "The source crop preview token or manifest checksum is stale.",
                )
            if row.job_id is not None:
                return _run(row)  # an idempotent retry of the same confirmation
            if row.status != "previewed":
                raise JobConflictError(
                    "SOURCE_CROP_PREVIEW_STALE", "The source crop preview is no longer startable."
                )
            job = create_job(
                job_type_for_kind(row.kind),
                game_id=None,
                input_payload=source_crop_job_payload(
                    row.id,
                    kind=row.kind,
                    phase="execute",
                    manifest_checksum_sha256=row.manifest_checksum_sha256,
                ),
            )
            SqlAlchemyJobRepository(session).add_job(job)
            row.job_id = job.id
            row.status = "created"
            row.updated_at = job.created_at
            session.flush()
            return _run(row)

    def get_run(self, run_id: UUID) -> SourceCropRun:
        with self._session_factory() as session:
            row = session.get(SourceCropRunModel, run_id)
            if row is None:
                raise JobNotFoundError(
                    "SOURCE_CROP_RUN_NOT_FOUND", "The source crop run does not exist."
                )
            return _run(row)

    def list_runs(self, *, limit: int) -> Sequence[SourceCropRun]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SourceCropRunModel)
                .order_by(SourceCropRunModel.created_at.desc(), SourceCropRunModel.id)
                .limit(limit)
            ).all()
            return tuple(_run(row) for row in rows)

    # ----- worker side (every write is fenced by the job lease) ---------------

    def mark_previewed(
        self,
        run_id: UUID,
        *,
        plan_job_id: UUID,
        lease_token: UUID,
        manifest_relative_path: str,
        manifest_checksum_sha256: str,
        preview_token: str,
        eligible_count: int,
        excluded_count: int,
        exclusion_counts: Mapping[str, int],
        candidate_bytes: int,
        estimated_saved_bytes: int,
    ) -> SourceCropRun:
        with self._session_factory.begin() as session:
            assert_job_lease(session, plan_job_id, lease_token)
            row = self._locked(session, run_id)
            if row.plan_job_id != plan_job_id:
                raise JobConflictError(
                    "SOURCE_CROP_RUN_JOB_MISMATCH", "The plan job does not own this run."
                )
            if row.status != "planning":
                raise JobConflictError(
                    "SOURCE_CROP_RUN_STATE_INVALID", "Only a planning run can be previewed."
                )
            row.status = "previewed"
            row.manifest_relative_path = manifest_relative_path
            row.manifest_checksum_sha256 = manifest_checksum_sha256
            row.preview_token = preview_token
            row.eligible_count = eligible_count
            row.excluded_count = excluded_count
            row.exclusion_counts = dict(exclusion_counts)
            row.candidate_bytes = candidate_bytes
            row.estimated_saved_bytes = estimated_saved_bytes
            row.updated_at = _now()
            session.flush()
            return _run(row)

    def manifest_of(self, run_id: UUID, *, job_id: UUID) -> SourceCropRun:
        with self._session_factory() as session:
            row = session.get(SourceCropRunModel, run_id)
            if row is None or row.job_id != job_id:
                raise JobConflictError(
                    "SOURCE_CROP_RUN_JOB_MISMATCH", "The execute job does not own this run."
                )
            return _run(row)

    def mark_processing(self, run_id: UUID, *, job_id: UUID, lease_token: UUID) -> SourceCropRun:
        with self._session_factory.begin() as session:
            assert_job_lease(session, job_id, lease_token)
            row = self._owned(session, run_id, job_id)
            if row.status == "created":
                row.status = "processing"
                row.started_at = row.started_at or _now()
                row.updated_at = _now()
            elif row.status != "processing":
                raise JobConflictError(
                    "SOURCE_CROP_RUN_STATE_INVALID", "Only a confirmed run can be executed."
                )
            session.flush()
            return _run(row)

    def checkpoint(
        self,
        run_id: UUID,
        *,
        job_id: UUID,
        lease_token: UUID,
        checkpoint_index: int,
        outcomes: Mapping[str, int],
        succeeded: int,
        skipped: int,
        failed: int,
        saved_bytes: int,
        failures: Sequence[Mapping[str, object]],
    ) -> None:
        with self._session_factory.begin() as session:
            assert_job_lease(session, job_id, lease_token)
            row = self._owned(session, run_id, job_id)
            if row.status != "processing" or checkpoint_index < row.checkpoint_index:
                raise JobConflictError(
                    "SOURCE_CROP_RUN_STATE_INVALID", "The checkpoint is older than the run."
                )
            row.checkpoint_index = checkpoint_index
            row.outcome_counts = dict(outcomes)
            row.succeeded_count = succeeded
            row.skipped_count = skipped
            row.failed_count = failed
            row.processed_count = succeeded + skipped + failed
            row.saved_bytes = saved_bytes
            row.failures = [dict(item) for item in failures][:MAX_RECORDED_FAILURES]
            row.updated_at = _now()

    def complete(self, run_id: UUID, *, job_id: UUID, lease_token: UUID) -> None:
        with self._session_factory.begin() as session:
            assert_job_lease(session, job_id, lease_token)
            row = self._owned(session, run_id, job_id)
            if row.status != "processing":
                raise JobConflictError(
                    "SOURCE_CROP_RUN_STATE_INVALID", "Only a running run can complete."
                )
            row.status = "completed"
            row.finished_at = _now()
            row.updated_at = row.finished_at

    @staticmethod
    def _locked(session: Session, run_id: UUID) -> SourceCropRunModel:
        row = session.get(SourceCropRunModel, run_id, with_for_update=True)
        if row is None:
            raise JobNotFoundError(
                "SOURCE_CROP_RUN_NOT_FOUND", "The source crop run does not exist."
            )
        return row

    @classmethod
    def _owned(cls, session: Session, run_id: UUID, job_id: UUID) -> SourceCropRunModel:
        row = cls._locked(session, run_id)
        if row.job_id != job_id:
            raise JobConflictError(
                "SOURCE_CROP_RUN_JOB_MISMATCH", "The execute job does not own this run."
            )
        return row


def synchronize_source_crop_job(session: Session, job: Job) -> None:
    """Atomic counterpart of every job state change outside the handler.

    Called next to ``synchronize_grid_job`` by the API job repository and the
    worker job store. A cancelled or failed job ends its run; a retried job
    (``created`` again) reopens its failed or cancelled run with its checkpoint,
    which fails with ``SOURCE_CROP_RUN_ACTIVE`` while another run is active; a
    job that completed without finishing its phase fails the run.
    """

    if job.job_type not in SOURCE_CROP_JOB_TYPES or job.status in (
        JobStatus.PROCESSING,
        JobStatus.WAITING_FOR_REVIEW,
    ):
        return
    row = session.scalar(
        select(SourceCropRunModel)
        .where(or_(SourceCropRunModel.plan_job_id == job.id, SourceCropRunModel.job_id == job.id))
        .with_for_update()
    )
    if row is None:
        return
    is_plan = row.job_id != job.id
    owned_phase = row.status == "planning" if is_plan else row.status in ("created", "processing")
    now = _now()
    if job.status in (JobStatus.CANCELLED, JobStatus.FAILED):
        if not owned_phase:
            return
        cancelled = job.status is JobStatus.CANCELLED
        row.status = "cancelled" if cancelled else "failed"
        row.error_code = (
            job.error_code
            or ("SOURCE_CROP_JOB_CANCELLED" if cancelled else "SOURCE_CROP_JOB_FAILED")
        )[:100]
        row.error_message = (job.error_message or "The run's job ended.")[:2000]
        row.finished_at = now
    elif job.status is JobStatus.CREATED:
        if row.status not in ("failed", "cancelled"):
            return
        if is_plan and row.manifest_checksum_sha256 is None:
            row.status = "planning"
        elif not is_plan:
            row.status = "created"
        else:
            return
        row.error_code = None
        row.error_message = None
        row.finished_at = None
    elif job.status is JobStatus.COMPLETED:
        if not owned_phase:
            return
        row.status = "failed"
        row.error_code = "SOURCE_CROP_JOB_ENDED_EARLY"
        row.error_message = "The run's job completed before its phase finished."
        row.finished_at = now
    row.updated_at = now
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as error:
        if "uq_source_crop_runs_active" in str(error.orig):
            raise JobConflictError(
                "SOURCE_CROP_RUN_ACTIVE",
                "Another source crop run is active; this run cannot be retried now.",
            ) from error
        raise


def _supersede_unstarted_preview(session: Session) -> None:
    """A new preview replaces a reviewed preview that nobody started."""

    row = session.scalar(
        select(SourceCropRunModel)
        .where(SourceCropRunModel.status == "previewed", SourceCropRunModel.job_id.is_(None))
        .with_for_update()
    )
    if row is None:
        return
    row.status = "cancelled"
    row.error_code = "SOURCE_CROP_PREVIEW_SUPERSEDED"
    row.error_message = "A newer preview replaced this unstarted preview."
    row.finished_at = _now()
    row.updated_at = row.finished_at
    session.flush()


def _now() -> datetime:
    return datetime.now(UTC)


def _counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int(count)
        for key, count in value.items()
        if isinstance(count, int) and not isinstance(count, bool)
    }


def _run(row: SourceCropRunModel) -> SourceCropRun:
    return SourceCropRun(
        id=row.id,
        kind=row.kind,
        status=row.status,
        scope=SourceCropScope.from_payload(row.scope),
        plan_job_id=row.plan_job_id,
        job_id=row.job_id,
        manifest_checksum_sha256=row.manifest_checksum_sha256,
        preview_token=row.preview_token,
        eligible_count=row.eligible_count,
        excluded_count=row.excluded_count,
        exclusion_counts=_counts(row.exclusion_counts),
        candidate_bytes=row.candidate_bytes,
        estimated_saved_bytes=row.estimated_saved_bytes,
        processed_count=row.processed_count,
        succeeded_count=row.succeeded_count,
        skipped_count=row.skipped_count,
        failed_count=row.failed_count,
        saved_bytes=row.saved_bytes,
        checkpoint_index=row.checkpoint_index,
        outcome_counts=_counts(row.outcome_counts),
        failures=tuple(row.failures or ()),
        error_code=row.error_code,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


__all__ = [
    "MAX_RECORDED_FAILURES",
    "SOURCE_CROP_JOB_TYPES",
    "SqlAlchemySourceCropRunRepository",
    "assert_job_lease",
    "job_type_for_kind",
    "source_crop_job_payload",
    "synchronize_source_crop_job",
]
