"""SQLAlchemy persistence for global semi-automatic image-selection runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import case, delete, func, literal, select, union_all
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticSelectionRepository,
)
from game_predictor_api.domain.jobs import JobStatus, requeue_job
from game_predictor_api.domain.semi_automatic_image_selections import (
    V7_SELECTION_CONFIGURATION_VERSION,
    FilenameRangeVerificationReview,
    FilenameRangeVerificationReviewDecision,
    FilenameVerificationHistoryDeletion,
    SemiAutomaticSelectionConflictError,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRangeStatus,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionSourceManifest,
    SemiAutomaticSelectionWorkflowMode,
    SemiAutomaticV7BorderStyle,
    SemiAutomaticV7SelectionConfiguration,
    SemiAutomaticV7SelectionMode,
    begin_filename_verification_cleanup,
)
from game_predictor_api.domain.v7_pilot_acceptance import receipt_matches_gate
from game_predictor_api.domain.v7_selection_delivery import (
    V7_PENDING_STATES,
    V7DeliveryConflict,
    V7OutputOperation,
    V7PilotGate,
    V7PilotSnapshot,
    V7SourcePolicy,
)
from game_predictor_api.storage.job_repository import (
    apply_job_to_record,
    job_from_record,
    job_record_from_domain,
)
from game_predictor_api.storage.models import (
    BrowserSelectionRetentionModel,
    FilenameRangeVerificationReviewModel,
    JobModel,
    SemiAutomaticImageSelectionRangeModel,
    SemiAutomaticImageSelectionRunModel,
    SemiAutomaticV7ActivationGateModel,
    V7OutputOperationModel,
    V7PilotAcceptanceModel,
    V7SourceObservationModel,
)


class SqlAlchemySemiAutomaticSelectionRepository(SemiAutomaticSelectionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_identity(self, identity_key: str) -> SemiAutomaticSelectionRun | None:
        row = self._session.execute(
            select(SemiAutomaticImageSelectionRunModel, JobModel)
            .join(JobModel, JobModel.id == SemiAutomaticImageSelectionRunModel.job_id)
            .where(SemiAutomaticImageSelectionRunModel.identity_key == identity_key)
        ).one_or_none()
        return None if row is None else _run_from_records(*row)

    def add(
        self,
        run: SemiAutomaticSelectionRun,
        ranges: Sequence[SemiAutomaticSelectionRange],
        *,
        identity_key: str,
    ) -> SemiAutomaticSelectionRun:
        try:
            with self._session.begin_nested():
                self._session.add(job_record_from_domain(run.job))
                self._session.add(_run_record(run, identity_key=identity_key))
                # Ranges refer to the durable run through a database foreign
                # key, but the models deliberately have no ORM relationship.
                # Persist the parent before staging its children so SQLAlchemy
                # cannot flush the ranges first.
                self._session.flush()
                self._session.add_all(_range_record(item) for item in ranges)
                self._pin_global_staging(run)
                self._session.flush()
        except IntegrityError as error:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_ALREADY_EXISTS",
                "A semi-automatic selection run with the same input already exists.",
            ) from error
        stored = self.get(run.id)
        if stored is None:
            raise RuntimeError("The persisted semi-automatic selection run cannot be read.")
        return stored

    def _pin_global_staging(self, run: SemiAutomaticSelectionRun) -> None:
        if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
            # V7 admission pins only direct local manifests, never browser staging.
            return
        retention = self._session.get(
            BrowserSelectionRetentionModel,
            run.source.upload_id,
            with_for_update=True,
        )
        if retention is None:
            return
        if retention.game_id is not None:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_SCOPE_INVALID",
                "The global staging is already scoped to a game.",
            )
        if retention.state == "blocked":
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CLEANUP_ACTIVE",
                "The global staging is being removed by a completed verification run.",
            )
        if retention.import_job_id not in {None, run.job.id}:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_IN_USE",
                "The global staging already belongs to another active selection run.",
            )
        retention.import_job_id = run.job.id
        retention.state = "in_use"
        retention.last_dependency_at = run.created_at
        retention.eligible_at = None
        retention.blocked_reason = None
        retention.updated_at = run.created_at

    def get(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> SemiAutomaticSelectionRun | None:
        statement = (
            select(SemiAutomaticImageSelectionRunModel, JobModel)
            .join(JobModel, JobModel.id == SemiAutomaticImageSelectionRunModel.job_id)
            .where(SemiAutomaticImageSelectionRunModel.id == run_id)
        )
        if for_update:
            identity = self._session.get(SemiAutomaticImageSelectionRunModel, run_id)
            if identity is not None and identity.workflow_mode == "v7_selection":
                self.get_v7_pilot_gate(for_update=True)
                self._session.scalar(
                    select(JobModel)
                    .where(JobModel.id == identity.job_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                self._session.scalar(
                    select(SemiAutomaticImageSelectionRunModel)
                    .where(SemiAutomaticImageSelectionRunModel.id == run_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                statement = statement.execution_options(populate_existing=True)
            else:
                statement = statement.with_for_update()
        row = self._session.execute(statement).one_or_none()
        return None if row is None else _run_from_records(*row)

    def get_for_display(
        self, run_id: UUID, *, include_checkpoint: bool = False
    ) -> SemiAutomaticSelectionRun | None:
        """Project only display fields without loading or replacing recovery data."""
        model = SemiAutomaticImageSelectionRunModel
        checkpoint = model.checkpoint
        summary = func.jsonb_build_object(
            "schemaVersion",
            checkpoint["schemaVersion"],
            "runtimeVersion",
            checkpoint["runtimeVersion"],
            "localizerFingerprint",
            checkpoint["localizerFingerprint"],
            "calibrationFingerprint",
            checkpoint["calibrationFingerprint"],
            "v7ProjectionFingerprint",
            checkpoint["v7ProjectionFingerprint"],
            "scanState",
            func.jsonb_build_object(
                "schemaVersion",
                checkpoint["scanState"]["schemaVersion"],
                "phase",
                checkpoint["scanState"]["phase"],
            ),
        )
        display_checkpoint = (
            case((model.workflow_mode == "v7_selection", summary), else_=checkpoint)
            if include_checkpoint
            else literal({}, type_=JSONB)
        )
        row = self._session.execute(
            select(model, JobModel, display_checkpoint)
            .options(defer(model.checkpoint, raiseload=True))
            .join(JobModel, JobModel.id == model.job_id)
            .where(model.id == run_id)
        ).one_or_none()
        return (
            None
            if row is None
            else _run_from_records(
                row[0], row[1], checkpoint_override=cast(dict[str, object], row[2])
            )
        )

    def get_for_v7_review(
        self, run_id: UUID, *, for_update: bool = False
    ) -> SemiAutomaticSelectionRun | None:
        """Read review guards, never transfer the scan history or source inventory."""
        model = SemiAutomaticImageSelectionRunModel
        if for_update:
            identity = self._session.execute(
                select(model.job_id, model.workflow_mode).where(model.id == run_id)
            ).one_or_none()
            if identity is None:
                return None
            if identity[1] != "v7_selection":
                return self.get(run_id, for_update=True)
            self.get_v7_pilot_gate(for_update=True)
            self._session.scalar(
                select(JobModel)
                .where(JobModel.id == identity[0])
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            self._session.scalar(
                select(model)
                .options(defer(model.checkpoint, raiseload=True))
                .where(model.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        checkpoint = model.checkpoint
        control = func.jsonb_build_object(
            "blockedReason",
            checkpoint["blockedReason"],
            "v7ProjectionFingerprint",
            checkpoint["v7ProjectionFingerprint"],
            "scanState",
            func.jsonb_build_object("phase", checkpoint["scanState"]["phase"]),
        )
        row = self._session.execute(
            select(
                model,
                JobModel,
                case((model.workflow_mode == "v7_selection", control), else_=checkpoint),
            )
            .options(defer(model.checkpoint, raiseload=True))
            .join(JobModel, JobModel.id == model.job_id)
            .where(model.id == run_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
        return (
            None
            if row is None
            else _run_from_records(
                row[0], row[1], checkpoint_override=cast(dict[str, object], row[2])
            )
        )

    def save_v7_review_state(self, run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRun:
        """Persist a reservation/requeue without replacing immutable scan recovery."""
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
            raise V7DeliveryConflict("V7_WORKFLOW_REQUIRED", "Review state requires a V7 run.")
        record = self._session.get(
            SemiAutomaticImageSelectionRunModel,
            run.id,
            options=(defer(SemiAutomaticImageSelectionRunModel.checkpoint, raiseload=True),),
        )
        job_record = self._session.get(JobModel, run.job.id)
        if record is None or job_record is None:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND", "The selection run no longer exists."
            )
        apply_job_to_record(job_record, run.job)
        record.status = run.status.value
        record.counters = dict(run.counters)
        record.revision = run.revision
        record.updated_at = run.updated_at
        self._session.flush()
        return run

    def save(self, run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRun:
        record = self._session.get(SemiAutomaticImageSelectionRunModel, run.id)
        job_record = self._session.get(JobModel, run.job.id)
        if record is None or job_record is None:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The semi-automatic selection run no longer exists.",
            )
        apply_job_to_record(job_record, run.job)
        record.status = run.status.value
        record.checkpoint = dict(run.checkpoint)
        record.counters = dict(run.counters)
        record.diagnostics_relative_path = run.diagnostics_relative_path
        record.diagnostics_checksum_sha256 = run.diagnostics_checksum_sha256
        record.revision = run.revision
        record.updated_at = run.updated_at
        self._session.flush()
        stored = self.get(run.id)
        if stored is None:
            raise RuntimeError("The updated semi-automatic selection run cannot be read.")
        return stored

    def list_runs(
        self,
        *,
        workflow_mode: SemiAutomaticSelectionWorkflowMode,
        offset: int,
        limit: int,
    ) -> tuple[tuple[SemiAutomaticSelectionRun, ...], int | None]:
        statement = (
            select(SemiAutomaticImageSelectionRunModel, JobModel)
            .join(JobModel, JobModel.id == SemiAutomaticImageSelectionRunModel.job_id)
            .where(SemiAutomaticImageSelectionRunModel.workflow_mode == workflow_mode.value)
            .order_by(
                SemiAutomaticImageSelectionRunModel.created_at.desc(),
                SemiAutomaticImageSelectionRunModel.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
        v7 = workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION
        if v7:
            statement = statement.options(
                defer(SemiAutomaticImageSelectionRunModel.checkpoint, raiseload=True)
            )
        rows = self._session.execute(statement).all()
        visible = rows[:limit]
        return (
            tuple(
                _run_from_records(*row, checkpoint_override={} if v7 else None) for row in visible
            ),
            offset + limit if len(rows) > limit else None,
        )

    def find_v7_runs_by_source_name(self, name: str) -> tuple[SemiAutomaticSelectionRun, ...]:
        model = SemiAutomaticImageSelectionRunModel
        ids = tuple(
            self._session.scalars(
                select(model.id)
                .where(
                    model.workflow_mode == "v7_selection",
                    model.source_display_name == name,
                )
                .order_by(model.created_at.desc(), model.id.desc())
                .limit(21)
            )
        )
        if len(ids) > 20:
            raise SemiAutomaticSelectionConflictError(
                "V7_REVIEW_FOLDER_AMBIGUOUS", "Too many saved runs match this folder name."
            )
        return tuple(run for run_id in ids if (run := self.get_for_display(run_id)) is not None)

    def get_filename_verification_reviews(
        self,
        run_id: UUID,
        source_indexes: Sequence[int],
    ) -> dict[int, FilenameRangeVerificationReview]:
        if not source_indexes:
            return {}
        rows = self._session.scalars(
            select(FilenameRangeVerificationReviewModel).where(
                FilenameRangeVerificationReviewModel.run_id == run_id,
                FilenameRangeVerificationReviewModel.source_index.in_(source_indexes),
            )
        )
        return {row.source_index: _review_from_record(row) for row in rows}

    def save_filename_verification_review(
        self,
        review: FilenameRangeVerificationReview,
        *,
        expected_revision: int,
    ) -> FilenameRangeVerificationReview:
        run = self._session.scalar(
            select(SemiAutomaticImageSelectionRunModel)
            .where(SemiAutomaticImageSelectionRunModel.id == review.run_id)
            .with_for_update()
        )
        if (
            run is None
            or run.workflow_mode != SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION.value
        ):
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The filename verification run no longer exists.",
            )
        if run.status not in {
            SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE.value,
            SemiAutomaticSelectionRunStatus.REVIEW_MODE.value,
        }:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_REVIEWABLE",
                "Filename verification decisions are no longer accepted for this run.",
            )
        record = self._session.get(
            FilenameRangeVerificationReviewModel,
            {"run_id": review.run_id, "source_index": review.source_index},
            with_for_update=True,
        )
        if record is None:
            if expected_revision != 0:
                raise SemiAutomaticSelectionConflictError(
                    "SEMI_AUTOMATIC_SELECTION_REVIEW_STALE",
                    "The filename verification decision changed in another session.",
                )
            record = FilenameRangeVerificationReviewModel(
                run_id=review.run_id,
                source_index=review.source_index,
                source_checksum_sha256=review.source_checksum_sha256,
                decision=review.decision.value,
                revision=review.revision,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            self._session.add(record)
        else:
            if record.revision != expected_revision:
                raise SemiAutomaticSelectionConflictError(
                    "SEMI_AUTOMATIC_SELECTION_REVIEW_STALE",
                    "The filename verification decision changed in another session.",
                )
            record.source_checksum_sha256 = review.source_checksum_sha256
            record.decision = review.decision.value
            record.revision = review.revision
            record.updated_at = review.updated_at
        self._session.flush()
        required = int(run.counters.get("filenameReviewRequired", 0))
        completed = int(
            self._session.scalar(
                select(func.count())
                .select_from(FilenameRangeVerificationReviewModel)
                .where(FilenameRangeVerificationReviewModel.run_id == review.run_id)
            )
            or 0
        )
        if required > 0 and completed >= required:
            job_record = self._session.scalar(
                select(JobModel).where(JobModel.id == run.job_id).with_for_update()
            )
            if job_record is None:
                raise SemiAutomaticSelectionConflictError(
                    "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                    "The filename verification job no longer exists.",
                )
            domain_run = _run_from_records(run, job_record)
            cleanup_run = begin_filename_verification_cleanup(
                domain_run,
                changed_at=review.updated_at,
            )
            cleanup_job = requeue_job(cleanup_run.job, updated_at=review.updated_at)
            apply_job_to_record(job_record, cleanup_job)
            run.status = cleanup_run.status.value
            run.checkpoint = {
                **dict(run.checkpoint),
                "cleanup": "pending",
                "phase": "cleanup_pending",
            }
            run.revision = cleanup_run.revision
            run.updated_at = cleanup_run.updated_at
            self._session.flush()
        return _review_from_record(record)

    def delete_completed_filename_verification_history(
        self,
        *,
        run_id: UUID,
        job_id: UUID,
    ) -> FilenameVerificationHistoryDeletion:
        """Delete compact history only after the worker removed all run data."""

        run = self._session.scalar(
            select(SemiAutomaticImageSelectionRunModel)
            .where(
                SemiAutomaticImageSelectionRunModel.id == run_id,
                SemiAutomaticImageSelectionRunModel.job_id == job_id,
            )
            .with_for_update()
        )
        job = self._session.scalar(select(JobModel).where(JobModel.id == job_id).with_for_update())
        if run is None or job is None:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The filename verification history changed before deletion.",
            )
        if (
            run.workflow_mode != SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION.value
            or run.status != SemiAutomaticSelectionRunStatus.COMPLETED.value
            or job.status is not JobStatus.COMPLETED
            or run.checkpoint.get("cleanup") != "completed"
        ):
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_NOT_COMPLETED",
                "Only a fully cleaned, completed filename verification history can be deleted.",
            )
        if (
            run.diagnostics_relative_path is not None
            or run.diagnostics_checksum_sha256 is not None
            or self._session.get(BrowserSelectionRetentionModel, run.source_upload_id) is not None
        ):
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_REFERENCED",
                "The filename verification history still has protected working data.",
            )
        has_output = self._session.scalar(
            select(func.count())
            .select_from(SemiAutomaticImageSelectionRangeModel)
            .where(
                SemiAutomaticImageSelectionRangeModel.run_id == run_id,
                SemiAutomaticImageSelectionRangeModel.output_checksum_sha256.is_not(None),
            )
        )
        if has_output:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_REFERENCED",
                "The filename verification history still has a protected output reference.",
            )
        try:
            with self._session.begin_nested():
                # A completed run normally has no heavy rows.  If a crash left
                # run-owned leftovers, remove them before the compact summary.
                self._session.execute(
                    delete(FilenameRangeVerificationReviewModel).where(
                        FilenameRangeVerificationReviewModel.run_id == run_id
                    )
                )
                self._session.execute(
                    delete(SemiAutomaticImageSelectionRangeModel).where(
                        SemiAutomaticImageSelectionRangeModel.run_id == run_id
                    )
                )
                deleted_run = self._session.execute(
                    delete(SemiAutomaticImageSelectionRunModel)
                    .where(
                        SemiAutomaticImageSelectionRunModel.id == run_id,
                        SemiAutomaticImageSelectionRunModel.job_id == job_id,
                    )
                    .returning(SemiAutomaticImageSelectionRunModel.id)
                ).scalar_one_or_none()
                deleted_job = self._session.execute(
                    delete(JobModel).where(JobModel.id == job_id).returning(JobModel.id)
                ).scalar_one_or_none()
                if deleted_run is None or deleted_job is None:
                    raise SemiAutomaticSelectionConflictError(
                        "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                        "The filename verification history changed before deletion.",
                    )
                self._session.flush()
        except IntegrityError as error:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_REFERENCED",
                "The filename verification history still has protected database references.",
            ) from error
        return FilenameVerificationHistoryDeletion(run_id=run_id, job_id=job_id)

    def list_ranges(
        self,
        run_id: UUID,
        *,
        after_expected_index: int | None,
        limit: int,
    ) -> tuple[SemiAutomaticSelectionRange, ...]:
        statement = select(SemiAutomaticImageSelectionRangeModel).where(
            SemiAutomaticImageSelectionRangeModel.run_id == run_id
        )
        if after_expected_index is not None:
            statement = statement.where(
                SemiAutomaticImageSelectionRangeModel.expected_index > after_expected_index
            )
        records = self._session.scalars(
            statement.order_by(SemiAutomaticImageSelectionRangeModel.expected_index).limit(limit)
        )
        items = tuple(_range_from_record(record) for record in records)
        if not any(item.v7_review is not None for item in items):
            return items
        latest: dict[UUID, V7OutputOperation] = {}
        operations = self._session.scalars(
            select(V7OutputOperationModel)
            .where(V7OutputOperationModel.range_id.in_([item.id for item in items]))
            .order_by(V7OutputOperationModel.created_at, V7OutputOperationModel.id)
        )
        for operation in operations:
            latest[operation.range_id] = _operation_from_record(operation)
        return tuple(_with_operation(item, latest.get(item.id)) for item in items)

    def get_range_for_update(
        self,
        run_id: UUID,
        expected_index: int,
    ) -> SemiAutomaticSelectionRange | None:
        record = self._session.scalar(
            select(SemiAutomaticImageSelectionRangeModel)
            .where(
                SemiAutomaticImageSelectionRangeModel.run_id == run_id,
                SemiAutomaticImageSelectionRangeModel.expected_index == expected_index,
            )
            .with_for_update()
        )
        return None if record is None else _range_from_record(record)

    def save_range(self, item: SemiAutomaticSelectionRange) -> SemiAutomaticSelectionRange:
        record = self._session.get(SemiAutomaticImageSelectionRangeModel, item.id)
        if record is None or record.run_id != item.run_id:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_RANGE_NOT_FOUND",
                "The expected range no longer exists.",
            )
        record.status = item.status.value
        record.source_index = item.source_index
        record.source_relative_path = item.source_relative_path
        record.source_size_bytes = item.source_size_bytes
        record.source_checksum_sha256 = item.source_checksum_sha256
        record.group_first_source_index = item.group_first_source_index
        record.group_last_source_index = item.group_last_source_index
        record.range_confidence = item.range_confidence
        record.selection_method = item.selection_method
        record.output_checksum_sha256 = item.output_checksum_sha256
        for key in (
            "v7_review",
            "v7_projection_fingerprint",
            "v7_confirmed_range_start",
            "v7_confirmed_range_end",
            "v7_output_owner_operation_id",
            "v7_output_generation",
        ):
            setattr(record, key, getattr(item, key))
        record.revision = item.revision
        record.updated_at = item.updated_at
        self._session.flush()
        return _range_from_record(record)

    def save_run_and_range(
        self,
        run: SemiAutomaticSelectionRun,
        item: SemiAutomaticSelectionRange,
    ) -> tuple[SemiAutomaticSelectionRun, SemiAutomaticSelectionRange]:
        stored_item = self.save_range(item)
        stored_run = self.save(run)
        return stored_run, stored_item

    def get_v7_pilot_gate(
        self, *, for_update: bool = False, for_share: bool = False
    ) -> V7PilotGate:
        statement = select(SemiAutomaticV7ActivationGateModel).where(
            SemiAutomaticV7ActivationGateModel.singleton.is_(True)
        )
        if for_update or for_share:
            statement = statement.with_for_update(read=for_share and not for_update)
        row = self._session.scalar(statement.execution_options(populate_existing=True))
        if row is None:
            return V7PilotGate()
        gate = V7PilotGate(
            status=row.pilot_status,
            generation=row.pilot_generation,
            mode=row.pilot_mode,
            geometry_family_id=row.pilot_geometry_family_id,
            source_game_ref=row.pilot_source_game_ref,
            source_policy=cast(V7SourcePolicy, row.pilot_source_policy),
            profile_fingerprint=row.pilot_profile_fingerprint,
            observer_fingerprint=row.pilot_observer_fingerprint,
            ocr_model_fingerprint=row.pilot_ocr_model_fingerprint,
            source_bindings=tuple(row.pilot_source_bindings),
            receipt_fingerprint=row.pilot_acceptance_receipt_fingerprint,
            accepted=row.pilot_accepted_at is not None and bool(row.pilot_accepted_by),
        )
        if not gate.enabled:
            return gate
        receipt = self._session.scalar(
            select(V7PilotAcceptanceModel).where(
                V7PilotAcceptanceModel.receipt_fingerprint == gate.receipt_fingerprint
            )
        )
        database_name = self._session.scalar(select(func.current_database()))
        if (
            receipt is None
            or receipt.resulting_generation != gate.generation
            or not receipt_matches_gate(
                receipt.receipt, receipt.receipt_fingerprint, gate, str(database_name)
            )
            or receipt.receipt.get("actor") != row.pilot_accepted_by
            or datetime.fromisoformat(str(receipt.receipt["acceptedAt"])) != row.pilot_accepted_at
        ):
            return replace(gate, status="blocked", accepted=False)
        return replace(gate, acceptance_receipt=dict(receipt.receipt))

    def get_v7_output_operation(
        self, operation_id: UUID, *, for_update: bool = False
    ) -> V7OutputOperation | None:
        statement = select(V7OutputOperationModel).where(V7OutputOperationModel.id == operation_id)
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement.execution_options(populate_existing=True))
        return None if row is None else _operation_from_record(row)

    def get_pending_v7_output(
        self, run_id: UUID, *, for_update: bool = False
    ) -> V7OutputOperation | None:
        statement = select(V7OutputOperationModel).where(
            V7OutputOperationModel.run_id == run_id,
            V7OutputOperationModel.state.in_(V7_PENDING_STATES),
        )
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement.execution_options(populate_existing=True))
        return None if row is None else _operation_from_record(row)

    def get_v7_output_root(self, run_id: UUID) -> str | None:
        model = V7OutputOperationModel
        base = select(model.context_payload["outputRoot"].as_string()).where(model.run_id == run_id)
        # Only the first owner and the one pending command can determine the pin.
        # Never deserialize every historical operation to display an output path.
        roots = self._session.scalars(
            union_all(
                base.where(model.state == "committed")
                .order_by(model.created_at, model.id)
                .limit(1),
                base.where(model.state.in_(V7_PENDING_STATES)).limit(1),
            )
        ).all()
        if len(set(roots)) > 1:
            raise V7DeliveryConflict(
                "V7_OUTPUT_ROOT_CONFLICT", "This run has conflicting output pins."
            )
        return None if not roots else (roots[0] or "")

    def save_v7_output_operation(self, operation: V7OutputOperation) -> V7OutputOperation:
        record = self._session.get(V7OutputOperationModel, operation.operation_id)
        if record is None:
            record = V7OutputOperationModel(
                id=operation.operation_id,
                run_id=operation.run_id,
                range_id=operation.range_id,
                request_fingerprint=operation.request_fingerprint,
                request_payload=operation.request_payload,
                context_payload=operation.context_payload,
                decision_generation=operation.decision_generation,
                reserved_revision=operation.reserved_revision,
                created_at=operation.created_at,
            )
            self._session.add(record)
        elif (
            record.request_fingerprint != operation.request_fingerprint
            or record.context_payload != operation.context_payload
            or record.decision_generation != operation.decision_generation
        ):
            raise SemiAutomaticSelectionConflictError(
                "V7_OPERATION_ID_CONFLICT", "Immutable command changed."
            )
        record.state = operation.state
        record.receipt = operation.receipt
        record.error_code = operation.error_code
        record.updated_at = operation.updated_at
        self._session.flush()
        return _operation_from_record(record)

    def get_v7_source_observations(
        self, run_id: UUID, source_indexes: Sequence[int]
    ) -> dict[int, dict[str, object]]:
        rows = self._session.scalars(
            select(V7SourceObservationModel).where(
                V7SourceObservationModel.run_id == run_id,
                V7SourceObservationModel.source_index.in_(source_indexes),
            )
        )
        return {
            row.source_index: {
                key: value for key, value in row.payload.items() if key != "resumeObservation"
            }
            for row in rows
        }


def _run_record(
    run: SemiAutomaticSelectionRun,
    *,
    identity_key: str,
) -> SemiAutomaticImageSelectionRunModel:
    return SemiAutomaticImageSelectionRunModel(
        id=run.id,
        job_id=run.job.id,
        source_upload_id=run.source.upload_id,
        source_display_name=run.source.display_name,
        source_manifest_checksum_sha256=run.source.manifest_checksum_sha256,
        source_fingerprint=run.source.source_fingerprint,
        source_count=run.source.source_count,
        source_total_bytes=run.source.source_total_bytes,
        first_sequence_number=run.first_sequence_number,
        last_sequence_number=run.last_sequence_number,
        direction=run.direction.value,
        workflow_mode=run.workflow_mode.value,
        range_convention=run.range_convention,
        full_range_size=run.full_range_size,
        expected_ranges_fingerprint=run.expected_ranges_fingerprint,
        recognizer_fingerprint=run.recognizer_fingerprint,
        grouping_policy_fingerprint=run.grouping_policy_fingerprint,
        identity_key=identity_key,
        status=run.status.value,
        checkpoint=dict(run.checkpoint),
        counters=dict(run.counters),
        diagnostics_relative_path=run.diagnostics_relative_path,
        diagnostics_checksum_sha256=run.diagnostics_checksum_sha256,
        v7_configuration=(
            None if run.v7_configuration is None else run.v7_configuration.as_payload()
        ),
        v7_calibration_fingerprint=(
            None if run.v7_configuration is None else run.v7_configuration.calibration_fingerprint
        ),
        revision=run.revision,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _range_record(item: SemiAutomaticSelectionRange) -> SemiAutomaticImageSelectionRangeModel:
    return SemiAutomaticImageSelectionRangeModel(
        id=item.id,
        run_id=item.run_id,
        expected_index=item.expected_index,
        range_start=item.range_start,
        range_end=item.range_end,
        status=item.status.value,
        source_index=item.source_index,
        source_relative_path=item.source_relative_path,
        source_size_bytes=item.source_size_bytes,
        source_checksum_sha256=item.source_checksum_sha256,
        group_first_source_index=item.group_first_source_index,
        group_last_source_index=item.group_last_source_index,
        range_confidence=item.range_confidence,
        selection_method=item.selection_method,
        output_checksum_sha256=item.output_checksum_sha256,
        v7_review=item.v7_review,
        v7_projection_fingerprint=item.v7_projection_fingerprint,
        v7_confirmed_range_start=item.v7_confirmed_range_start,
        v7_confirmed_range_end=item.v7_confirmed_range_end,
        v7_output_owner_operation_id=item.v7_output_owner_operation_id,
        v7_output_generation=item.v7_output_generation,
        revision=item.revision,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _run_from_records(
    record: SemiAutomaticImageSelectionRunModel,
    job_record: JobModel,
    *,
    checkpoint_override: dict[str, object] | None = None,
) -> SemiAutomaticSelectionRun:
    return SemiAutomaticSelectionRun(
        id=record.id,
        job=job_from_record(job_record),
        source=SemiAutomaticSelectionSourceManifest(
            upload_id=record.source_upload_id,
            display_name=record.source_display_name,
            manifest_checksum_sha256=record.source_manifest_checksum_sha256,
            source_fingerprint=record.source_fingerprint,
            source_count=record.source_count,
            source_total_bytes=record.source_total_bytes,
        ),
        first_sequence_number=record.first_sequence_number,
        last_sequence_number=record.last_sequence_number,
        direction=SemiAutomaticSelectionDirection(record.direction),
        workflow_mode=SemiAutomaticSelectionWorkflowMode(record.workflow_mode),
        v7_configuration=_v7_configuration_from_record(record),
        range_convention=record.range_convention,
        full_range_size=record.full_range_size,
        expected_ranges_fingerprint=record.expected_ranges_fingerprint,
        recognizer_fingerprint=record.recognizer_fingerprint,
        grouping_policy_fingerprint=record.grouping_policy_fingerprint,
        status=SemiAutomaticSelectionRunStatus(record.status),
        checkpoint=dict(record.checkpoint if checkpoint_override is None else checkpoint_override),
        counters={key: int(value) for key, value in record.counters.items()},
        diagnostics_relative_path=record.diagnostics_relative_path,
        diagnostics_checksum_sha256=record.diagnostics_checksum_sha256,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _range_from_record(
    record: SemiAutomaticImageSelectionRangeModel,
) -> SemiAutomaticSelectionRange:
    return SemiAutomaticSelectionRange(
        id=record.id,
        run_id=record.run_id,
        expected_index=record.expected_index,
        range_start=record.range_start,
        range_end=record.range_end,
        status=SemiAutomaticSelectionRangeStatus(record.status),
        source_index=record.source_index,
        source_relative_path=record.source_relative_path,
        source_size_bytes=record.source_size_bytes,
        source_checksum_sha256=record.source_checksum_sha256,
        group_first_source_index=record.group_first_source_index,
        group_last_source_index=record.group_last_source_index,
        range_confidence=record.range_confidence,
        selection_method=record.selection_method,
        output_checksum_sha256=record.output_checksum_sha256,
        v7_review=record.v7_review,
        v7_projection_fingerprint=record.v7_projection_fingerprint,
        v7_confirmed_range_start=record.v7_confirmed_range_start,
        v7_confirmed_range_end=record.v7_confirmed_range_end,
        v7_output_owner_operation_id=record.v7_output_owner_operation_id,
        v7_output_generation=record.v7_output_generation,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _review_from_record(
    record: FilenameRangeVerificationReviewModel,
) -> FilenameRangeVerificationReview:
    return FilenameRangeVerificationReview(
        run_id=record.run_id,
        source_index=record.source_index,
        source_checksum_sha256=record.source_checksum_sha256,
        decision=FilenameRangeVerificationReviewDecision(record.decision),
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


__all__ = ["SqlAlchemySemiAutomaticSelectionRepository"]


def _v7_configuration_from_record(
    record: SemiAutomaticImageSelectionRunModel,
) -> SemiAutomaticV7SelectionConfiguration | None:
    raw = record.v7_configuration
    if raw is None:
        return None
    try:
        if raw["version"] not in {
            V7_SELECTION_CONFIGURATION_VERSION,
            "v7-selection-configuration-v2",
        }:
            raise ValueError("unsupported V7 configuration version")
        configuration = SemiAutomaticV7SelectionConfiguration(
            mode=SemiAutomaticV7SelectionMode(str(raw["mode"])),
            direction=SemiAutomaticSelectionDirection(str(raw["direction"])),
            first_sequence_number=_v7_configuration_integer(raw, "firstSequenceNumber"),
            last_sequence_number=_v7_configuration_integer(raw, "lastSequenceNumber"),
            border_style=SemiAutomaticV7BorderStyle(str(raw["borderStyle"])),
            localizer_fingerprint=str(raw["localizerFingerprint"]),
            calibration_fingerprint=str(raw["calibrationFingerprint"]),
            output_directory=cast(str | None, raw.get("outputDirectory")),
            pilot=(
                None
                if raw["version"] == V7_SELECTION_CONFIGURATION_VERSION
                else V7PilotSnapshot.from_payload(raw.get("pilot"))
            ),
        )
        if record.v7_calibration_fingerprint != configuration.calibration_fingerprint:
            raise ValueError("V7 calibration fingerprint does not match configuration")
        return configuration
    except (KeyError, TypeError, ValueError) as error:
        raise SemiAutomaticSelectionConflictError(
            "SEMI_AUTOMATIC_SELECTION_V7_CONFIGURATION_INVALID",
            "The persisted V7 configuration is invalid.",
        ) from error


def _v7_configuration_integer(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"V7 configuration {key} must be an integer.")
    return value


def _operation_from_record(record: V7OutputOperationModel) -> V7OutputOperation:
    operation = V7OutputOperation(
        record.id,
        record.run_id,
        record.range_id,
        dict(record.request_payload),
        dict(record.context_payload),
        record.decision_generation,
        record.reserved_revision,
        record.state,
        record.receipt,
        record.error_code,
        record.created_at,
        record.updated_at,
    )
    if operation.request_fingerprint != record.request_fingerprint:
        raise V7DeliveryConflict(
            "V7_OPERATION_ID_CONFLICT", "Stored operation fingerprint changed."
        )
    return operation


def _with_operation(
    item: SemiAutomaticSelectionRange, operation: V7OutputOperation | None
) -> SemiAutomaticSelectionRange:
    return (
        item
        if operation is None
        else replace(
            item,
            output_operation=operation.as_response(),
            acknowledgement_receipt=operation.receipt,
        )
    )
