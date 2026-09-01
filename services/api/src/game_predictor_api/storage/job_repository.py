"""SQLAlchemy repository for durable administrative jobs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.jobs import (
    BoardTopologyJobReference,
    ImageGeometryRolloutJobReference,
    ImageSelectionJobDeletionReference,
    JobRepository,
    LayoutImportRulesReference,
    PayoutDatasetReference,
    PayoutRulesReference,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    JobType,
)
from game_predictor_api.domain.mobile_releases import MobileReleaseStatus
from game_predictor_api.storage.models import (
    BrowserSelectionRetentionModel,
    CuratedImageImportSourceModel,
    DatasetVersionModel,
    GameModel,
    ImageGeometryRolloutStateModel,
    ImageSelectionCandidateModel,
    ImageSelectionGroupModel,
    ImageSelectionManualDecisionModel,
    ImageSelectionRunModel,
    JobModel,
    MobileReleaseModel,
    RulesVersionModel,
)


class SqlAlchemyJobRepository(JobRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def game_exists(self, game_id: UUID) -> bool:
        return self._session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is not None

    def get_or_pin_board_topology(
        self,
        game_id: UUID,
    ) -> BoardTopologyJobReference | None:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            return None
        rules = None
        if game.board_topology_rules_version_id is not None:
            rules = self._session.get(RulesVersionModel, game.board_topology_rules_version_id)
        if rules is None:
            rules = self._session.scalar(
                select(RulesVersionModel)
                .where(RulesVersionModel.game_id == game_id)
                .order_by(RulesVersionModel.version.desc(), RulesVersionModel.id)
                .limit(1)
            )
            if rules is None:
                return None
            game.board_topology_rules_version_id = rules.id
            self._session.flush()
        return BoardTopologyJobReference(
            rules_version_id=rules.id,
            rows=rules.rows,
            columns=rules.columns,
        )

    def get_image_geometry_rollout(
        self,
        game_id: UUID,
    ) -> ImageGeometryRolloutJobReference | None:
        record = self._session.get(ImageGeometryRolloutStateModel, game_id)
        if record is None:
            return None
        return ImageGeometryRolloutJobReference(
            geometry_mode=record.geometry_mode,
            cell_asset_mode=record.cell_asset_mode,
            revision=record.revision,
        )

    def get_layout_import_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> LayoutImportRulesReference | None:
        record = self._session.get(RulesVersionModel, rules_version_id)
        if record is None:
            return None
        return LayoutImportRulesReference(
            game_id=record.game_id,
            status=record.status,
        )

    def get_payout_dataset_reference(
        self,
        dataset_version_id: UUID,
    ) -> PayoutDatasetReference | None:
        record = self._session.get(DatasetVersionModel, dataset_version_id)
        if record is None:
            return None
        return PayoutDatasetReference(
            game_id=record.game_id,
            status=record.status,
            rows=record.rows,
            columns=record.columns,
            expected_layout_count=record.expected_layout_count,
            layout_count=record.layout_count,
        )

    def get_payout_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> PayoutRulesReference | None:
        record = self._session.get(RulesVersionModel, rules_version_id)
        if record is None:
            return None
        return PayoutRulesReference(
            game_id=record.game_id,
            status=record.status,
            rows=record.rows,
            columns=record.columns,
        )

    def add_job(self, job: Job) -> Job:
        record = job_record_from_domain(job)
        self._session.add(record)
        self._flush_or_raise_conflict()
        return job_from_record(record)

    def add_source_bound_job(
        self,
        job: Job,
        *,
        source_selection_id: UUID,
    ) -> Job:
        retention = self._session.scalar(
            select(BrowserSelectionRetentionModel)
            .where(BrowserSelectionRetentionModel.upload_id == source_selection_id)
            .with_for_update()
        )
        if retention is not None and retention.game_id not in {None, job.game_id}:
            raise JobConflictError(
                "IMAGE_FOLDER_SELECTION_GAME_MISMATCH",
                "The staged folder belongs to a different game.",
            )

        record = job_record_from_domain(job)
        self._session.add(record)
        self._flush_or_raise_conflict()
        if retention is not None:
            retention.game_id = job.game_id
            retention.import_job_id = job.id
            retention.state = "in_use"
            retention.last_dependency_at = job.created_at
            retention.eligible_at = None
            retention.blocked_reason = None
            retention.updated_at = job.created_at
            self._flush_or_raise_conflict()
        return job_from_record(record)

    def get_job(self, job_id: UUID) -> Job | None:
        record = self._session.get(JobModel, job_id)
        return None if record is None else job_from_record(record)

    def get_job_for_update(self, job_id: UUID) -> Job | None:
        record = self._session.scalar(
            select(JobModel).where(JobModel.id == job_id).with_for_update()
        )
        return None if record is None else job_from_record(record)

    def get_job_by_input_key(self, input_key: str) -> Job | None:
        record = self._session.scalar(select(JobModel).where(JobModel.input_key == input_key))
        return None if record is None else job_from_record(record)

    def get_image_import_by_source_selection(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
    ) -> Job | None:
        record = self._session.scalar(
            select(JobModel)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMPORT,
                JobModel.input_payload["source_selection_id"].as_string()
                == str(source_selection_id),
            )
            .order_by(JobModel.created_at.desc(), JobModel.id)
        )
        return None if record is None else job_from_record(record)

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> list[Job]:
        statement = select(JobModel)
        if status is not None:
            statement = statement.where(JobModel.status == status)
        if job_type is not None:
            statement = statement.where(JobModel.job_type == job_type)
        if game_id is not None:
            statement = statement.where(JobModel.game_id == game_id)
        records = self._session.scalars(
            statement.order_by(JobModel.created_at.desc(), JobModel.id).limit(limit)
        )
        return [job_from_record(record) for record in records]

    def save_job(self, job: Job) -> Job:
        record = self._session.get(JobModel, job.id)
        if record is None:
            raise JobConflictError(
                "JOB_NOT_FOUND",
                "Job no longer exists.",
                details={"jobId": str(job.id)},
            )
        apply_job_to_record(record, job)
        if job.job_type is JobType.ANDROID_BUILD and job.status is JobStatus.CANCELLED:
            release = self._session.scalar(
                select(MobileReleaseModel).where(MobileReleaseModel.build_job_id == job.id)
            )
            if release is not None and release.status is not MobileReleaseStatus.READY:
                release.status = MobileReleaseStatus.FAILED
                release.ready_at = None
        self._flush_or_raise_conflict()
        return job_from_record(record)

    def get_image_selection_deletion_reference(
        self,
        job_id: UUID,
    ) -> ImageSelectionJobDeletionReference | None:
        run = self._session.scalar(
            select(ImageSelectionRunModel).where(ImageSelectionRunModel.job_id == job_id)
        )
        if run is None:
            return None
        source_reference_count = self._session.scalar(
            select(func.count(ImageSelectionRunModel.id)).where(
                ImageSelectionRunModel.source_selection_id == run.source_selection_id
            )
        )
        curated_source_id = self._session.scalar(
            select(CuratedImageImportSourceModel.id).where(
                CuratedImageImportSourceModel.image_selection_run_id == run.id
            )
        )
        return ImageSelectionJobDeletionReference(
            run_id=run.id,
            source_selection_id=run.source_selection_id,
            source_reference_count=int(source_reference_count or 0),
            has_curated_import_source=curated_source_id is not None,
            has_published_output=(
                run.output_manifest_sha256 is not None
                or run.output_manifest_relative_path is not None
            ),
        )

    def delete_image_selection_run_and_job(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
    ) -> None:
        self._session.execute(
            delete(ImageSelectionManualDecisionModel).where(
                ImageSelectionManualDecisionModel.run_id == run_id
            )
        )
        self._session.execute(
            delete(ImageSelectionCandidateModel).where(
                ImageSelectionCandidateModel.run_id == run_id
            )
        )
        self._session.execute(
            delete(ImageSelectionGroupModel).where(ImageSelectionGroupModel.run_id == run_id)
        )
        deleted_run = self._session.execute(
            delete(ImageSelectionRunModel)
            .where(
                ImageSelectionRunModel.id == run_id,
                ImageSelectionRunModel.job_id == job_id,
            )
            .returning(ImageSelectionRunModel.id)
        ).scalar_one_or_none()
        if deleted_run is None:
            raise JobConflictError(
                "IMAGE_SELECTION_JOB_RUN_CHANGED",
                "The image-selection run changed before deletion.",
            )
        deleted_job = self._session.execute(
            delete(JobModel).where(JobModel.id == job_id).returning(JobModel.id)
        ).scalar_one_or_none()
        if deleted_job is None:
            raise JobConflictError(
                "JOB_NOT_FOUND",
                "Job no longer exists.",
                details={"jobId": str(job_id)},
            )
        self._session.flush()

    def _flush_or_raise_conflict(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint_name = diagnostic.constraint_name if diagnostic is not None else None
            if constraint_name == "uq_jobs_input_key":
                raise JobConflictError(
                    "JOB_INPUT_ALREADY_EXISTS",
                    "A job with the same type and input already exists.",
                ) from error
            raise JobConflictError(
                "JOB_PERSISTENCE_CONFLICT",
                "Job data conflicts with a persisted record.",
            ) from error


def apply_job_to_record(record: JobModel, job: Job) -> None:
    record.status = job.status
    record.stage = job.stage
    record.progress_current = job.progress_current
    record.progress_total = job.progress_total
    record.success_count = job.success_count
    record.failure_count = job.failure_count
    record.review_count = job.review_count
    record.error_code = job.error_code
    record.error_message = job.error_message
    record.worker_version = job.worker_version
    record.checkpoint_payload = job.checkpoint_payload
    record.attempt_count = job.attempt_count
    record.execution_slot = job.execution_slot
    record.lease_owner = job.lease_owner
    record.lease_token = job.lease_token
    record.lease_expires_at = job.lease_expires_at
    record.heartbeat_at = job.heartbeat_at
    record.updated_at = job.updated_at
    record.started_at = job.started_at
    record.finished_at = job.finished_at
    record.cancel_requested_at = job.cancel_requested_at


def job_record_from_domain(job: Job) -> JobModel:
    return JobModel(
        id=job.id,
        job_type=job.job_type,
        game_id=job.game_id,
        status=job.status,
        input_payload=job.input_payload,
        input_key=job.input_key,
        stage=job.stage,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        success_count=job.success_count,
        failure_count=job.failure_count,
        review_count=job.review_count,
        error_code=job.error_code,
        error_message=job.error_message,
        worker_version=job.worker_version,
        checkpoint_payload=job.checkpoint_payload,
        attempt_count=job.attempt_count,
        execution_slot=job.execution_slot,
        lease_owner=job.lease_owner,
        lease_token=job.lease_token,
        lease_expires_at=job.lease_expires_at,
        heartbeat_at=job.heartbeat_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        cancel_requested_at=job.cancel_requested_at,
    )


def job_from_record(record: JobModel) -> Job:
    return Job(
        id=record.id,
        job_type=record.job_type,
        game_id=record.game_id,
        status=record.status,
        input_payload=dict(record.input_payload),
        input_key=record.input_key,
        stage=record.stage,
        progress_current=record.progress_current,
        progress_total=record.progress_total,
        success_count=record.success_count,
        failure_count=record.failure_count,
        review_count=record.review_count,
        error_code=record.error_code,
        error_message=record.error_message,
        worker_version=record.worker_version,
        checkpoint_payload=(
            None if record.checkpoint_payload is None else dict(record.checkpoint_payload)
        ),
        attempt_count=record.attempt_count,
        execution_slot=record.execution_slot,
        lease_owner=record.lease_owner,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
        heartbeat_at=record.heartbeat_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        cancel_requested_at=record.cancel_requested_at,
    )
