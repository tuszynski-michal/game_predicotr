"""SQLAlchemy persistence for image-selection runs and bounded projections."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from game_predictor_api.application.image_selections import ImageSelectionRepository
from game_predictor_api.domain.image_selections import (
    ImageSelectionCandidate,
    ImageSelectionCandidateDecision,
    ImageSelectionConflictError,
    ImageSelectionGroup,
    ImageSelectionGroupStatus,
    ImageSelectionManualDecision,
    ImageSelectionManualResolution,
    ImageSelectionRun,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.storage.job_repository import (
    SqlAlchemyJobRepository,
    job_from_record,
    job_record_from_domain,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageSelectionCandidateModel,
    ImageSelectionGroupModel,
    ImageSelectionManualDecisionModel,
    ImageSelectionRunModel,
    JobModel,
)


class SqlAlchemyImageSelectionRepository(ImageSelectionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def game_exists(self, game_id: UUID) -> bool:
        return self._session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is not None

    def get_job_for_update(self, job_id: UUID) -> Job | None:
        return SqlAlchemyJobRepository(self._session).get_job_for_update(job_id)

    def save_job(self, job: Job) -> Job:
        return SqlAlchemyJobRepository(self._session).save_job(job)

    def find_run_by_identity(
        self,
        *,
        game_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
    ) -> ImageSelectionRun | None:
        row = self._session.execute(
            select(ImageSelectionRunModel, JobModel)
            .join(JobModel, JobModel.id == ImageSelectionRunModel.job_id)
            .where(
                ImageSelectionRunModel.game_id == game_id,
                ImageSelectionRunModel.input_manifest_sha256 == input_manifest_sha256,
                ImageSelectionRunModel.selector_fingerprint == selector_fingerprint,
            )
        ).one_or_none()
        return None if row is None else _run_from_records(*row)

    def add_run(self, run: ImageSelectionRun) -> tuple[ImageSelectionRun, bool]:
        record = ImageSelectionRunModel(
            id=run.id,
            game_id=run.game_id,
            job_id=run.job.id,
            source_selection_id=run.source_selection_id,
            input_manifest_sha256=run.input_manifest_sha256,
            selector_fingerprint=run.selector_fingerprint,
            ordering_policy=run.ordering_policy,
            contract_version=run.contract_version,
            output_manifest_sha256=run.output_manifest_sha256,
            output_manifest_relative_path=run.output_manifest_relative_path,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(job_record_from_domain(run.job))
                # There is no ORM relationship between the aggregate records,
                # so make the foreign-key ordering explicit. The savepoint
                # still rolls both inserts back if the run conflicts.
                self._session.flush()
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            existing = self.find_run_by_identity(
                game_id=run.game_id,
                input_manifest_sha256=run.input_manifest_sha256,
                selector_fingerprint=run.selector_fingerprint,
            )
            if existing is not None:
                return existing, False
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
                "Image selection run conflicts with persisted state.",
            ) from error
        return _run_from_records(record, self._session.get(JobModel, run.job.id)), True

    def get_run(self, run_id: UUID) -> ImageSelectionRun | None:
        row = self._session.execute(
            select(ImageSelectionRunModel, JobModel)
            .join(JobModel, JobModel.id == ImageSelectionRunModel.job_id)
            .where(ImageSelectionRunModel.id == run_id)
        ).one_or_none()
        return None if row is None else _run_from_records(*row)

    def save_run(self, run: ImageSelectionRun) -> ImageSelectionRun:
        record = self._session.get(ImageSelectionRunModel, run.id)
        if record is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_NOT_FOUND",
                "Image selection run no longer exists.",
            )
        if record.output_manifest_sha256 is not None and (
            record.output_manifest_sha256 != run.output_manifest_sha256
            or record.output_manifest_relative_path != run.output_manifest_relative_path
        ):
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "Image selection run already references another output.",
            )
        record.output_manifest_sha256 = run.output_manifest_sha256
        record.output_manifest_relative_path = run.output_manifest_relative_path
        record.updated_at = run.updated_at
        self._flush_or_conflict()
        job_record = self._session.get(JobModel, run.job.id)
        return _run_from_records(record, job_record)

    def list_groups(
        self,
        *,
        run_id: UUID,
        status: ImageSelectionGroupStatus | None,
        after_group_order: int,
        limit: int,
    ) -> list[ImageSelectionGroup]:
        selected = aliased(ImageSelectionCandidateModel)
        statement = (
            select(ImageSelectionGroupModel, selected.id)
            .outerjoin(
                selected,
                (selected.run_id == ImageSelectionGroupModel.run_id)
                & (selected.group_id == ImageSelectionGroupModel.id)
                & selected.decision.in_(
                    (
                        ImageSelectionCandidateDecision.SELECTED_AUTOMATIC.value,
                        ImageSelectionCandidateDecision.SELECTED_MANUAL.value,
                    )
                ),
            )
            .where(
                ImageSelectionGroupModel.run_id == run_id,
                ImageSelectionGroupModel.group_order > after_group_order,
            )
            .order_by(ImageSelectionGroupModel.group_order, ImageSelectionGroupModel.id)
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(ImageSelectionGroupModel.status == status.value)
        rows = self._session.execute(statement)
        return [_group_from_record(record, selected_id) for record, selected_id in rows]

    def add_group(self, group: ImageSelectionGroup) -> ImageSelectionGroup:
        record = ImageSelectionGroupModel(
            id=group.id,
            run_id=group.run_id,
            group_order=group.group_order,
            range_start=group.range_start,
            range_end=group.range_end,
            fingerprint_sha256=group.fingerprint_sha256,
            board_count_consensus=group.board_count_consensus,
            status=group.status.value,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
        self._session.add(record)
        self._flush_or_conflict()
        return _group_from_record(record, group.selected_candidate_id)

    def add_candidate(
        self,
        candidate: ImageSelectionCandidate,
    ) -> ImageSelectionCandidate:
        record = ImageSelectionCandidateModel(
            id=candidate.id,
            run_id=candidate.run_id,
            group_id=candidate.group_id,
            order_index=candidate.order_index,
            source_relative_path=candidate.source_relative_path,
            checksum_sha256=candidate.checksum_sha256,
            width=candidate.width,
            height=candidate.height,
            quality_metrics=candidate.quality_metrics,
            range_confidence=candidate.range_confidence,
            reason_codes=list(candidate.reason_codes),
            decision=candidate.decision.value,
            created_at=candidate.created_at,
        )
        self._session.add(record)
        self._flush_or_conflict()
        return _candidate_from_record(record)

    def get_group(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
    ) -> ImageSelectionGroup | None:
        selected = aliased(ImageSelectionCandidateModel)
        row = self._session.execute(
            select(ImageSelectionGroupModel, selected.id)
            .outerjoin(
                selected,
                (selected.run_id == ImageSelectionGroupModel.run_id)
                & (selected.group_id == ImageSelectionGroupModel.id)
                & selected.decision.in_(
                    (
                        ImageSelectionCandidateDecision.SELECTED_AUTOMATIC.value,
                        ImageSelectionCandidateDecision.SELECTED_MANUAL.value,
                    )
                ),
            )
            .where(
                ImageSelectionGroupModel.run_id == run_id,
                ImageSelectionGroupModel.id == group_id,
            )
        ).one_or_none()
        return None if row is None else _group_from_record(*row)

    def get_candidate(
        self,
        *,
        run_id: UUID,
        candidate_id: UUID,
    ) -> ImageSelectionCandidate | None:
        record = self._session.scalar(
            select(ImageSelectionCandidateModel).where(
                ImageSelectionCandidateModel.run_id == run_id,
                ImageSelectionCandidateModel.id == candidate_id,
            )
        )
        return None if record is None else _candidate_from_record(record)

    def find_candidate_by_checksum(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        checksum_sha256: str,
    ) -> ImageSelectionCandidate | None:
        record = self._session.scalar(
            select(ImageSelectionCandidateModel)
            .where(
                ImageSelectionCandidateModel.run_id == run_id,
                ImageSelectionCandidateModel.group_id == group_id,
                ImageSelectionCandidateModel.checksum_sha256 == checksum_sha256,
                ImageSelectionCandidateModel.reason_codes.contains(["manual_upload"]),
            )
            .order_by(ImageSelectionCandidateModel.created_at)
            .limit(1)
        )
        return None if record is None else _candidate_from_record(record)

    def next_candidate_order(self, run_id: UUID) -> int:
        value = self._session.scalar(
            select(func.max(ImageSelectionCandidateModel.order_index)).where(
                ImageSelectionCandidateModel.run_id == run_id
            )
        )
        return 0 if value is None else int(value) + 1

    def get_manual_decision(
        self,
        idempotency_key: UUID,
    ) -> ImageSelectionManualDecision | None:
        record = self._session.get(ImageSelectionManualDecisionModel, idempotency_key)
        return None if record is None else _manual_decision_from_record(record)

    def list_manual_decisions(
        self,
        *,
        run_id: UUID,
    ) -> list[ImageSelectionManualDecision]:
        records = self._session.scalars(
            select(ImageSelectionManualDecisionModel)
            .where(ImageSelectionManualDecisionModel.run_id == run_id)
            .order_by(
                ImageSelectionManualDecisionModel.group_id,
                ImageSelectionManualDecisionModel.revision,
            )
        )
        return [_manual_decision_from_record(record) for record in records]

    def next_manual_revision(self, *, run_id: UUID, group_id: UUID) -> int:
        value = self._session.scalar(
            select(func.max(ImageSelectionManualDecisionModel.revision)).where(
                ImageSelectionManualDecisionModel.run_id == run_id,
                ImageSelectionManualDecisionModel.group_id == group_id,
            )
        )
        return 1 if value is None else int(value) + 1

    def save_manual_decision(
        self,
        *,
        group: ImageSelectionGroup,
        decision: ImageSelectionManualDecision,
    ) -> tuple[ImageSelectionGroup, ImageSelectionManualDecision]:
        record = self._session.scalar(
            select(ImageSelectionGroupModel)
            .where(
                ImageSelectionGroupModel.run_id == group.run_id,
                ImageSelectionGroupModel.id == group.id,
            )
            .with_for_update()
        )
        if record is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_GROUP_NOT_FOUND",
                "Image-selection group no longer exists.",
            )
        self._session.execute(
            update(ImageSelectionCandidateModel)
            .where(
                ImageSelectionCandidateModel.run_id == group.run_id,
                ImageSelectionCandidateModel.group_id == group.id,
                ImageSelectionCandidateModel.decision
                == ImageSelectionCandidateDecision.SELECTED_MANUAL.value,
            )
            .values(decision=ImageSelectionCandidateDecision.ELIGIBLE.value)
        )
        selected = (
            None
            if decision.candidate_id is None
            else self._session.get(ImageSelectionCandidateModel, decision.candidate_id)
        )
        if decision.resolution is ImageSelectionManualResolution.SELECTED_IMAGE:
            if selected is None or selected.run_id != group.run_id or selected.group_id != group.id:
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_CANDIDATE_MISMATCH",
                    "The selected JPEG no longer belongs to this group.",
                )
            selected.decision = ImageSelectionCandidateDecision.SELECTED_MANUAL
        record.range_start = group.range_start
        record.range_end = group.range_end
        record.status = group.status
        record.updated_at = group.updated_at
        event = ImageSelectionManualDecisionModel(
            idempotency_key=decision.idempotency_key,
            run_id=decision.run_id,
            group_id=decision.group_id,
            candidate_id=decision.candidate_id,
            resolution=decision.resolution.value,
            range_start=decision.range_start,
            range_end=decision.range_end,
            revision=decision.revision,
            payload_sha256=decision.payload_sha256,
            created_at=decision.created_at,
        )
        self._session.add(event)
        self._flush_or_conflict()
        return _group_from_record(
            record,
            None if selected is None else selected.id,
        ), _manual_decision_from_record(event)

    def _flush_or_conflict(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
                "Image selection data conflicts with persisted state.",
            ) from error


def _run_from_records(
    record: ImageSelectionRunModel,
    job_record: JobModel | None,
) -> ImageSelectionRun:
    if job_record is None:
        raise ImageSelectionConflictError(
            "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
            "Image selection run has no durable job.",
        )
    return ImageSelectionRun(
        id=record.id,
        game_id=record.game_id,
        job=job_from_record(job_record),
        source_selection_id=record.source_selection_id,
        input_manifest_sha256=record.input_manifest_sha256,
        selector_fingerprint=record.selector_fingerprint,
        ordering_policy=record.ordering_policy,
        contract_version=record.contract_version,
        output_manifest_sha256=record.output_manifest_sha256,
        output_manifest_relative_path=record.output_manifest_relative_path,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _group_from_record(
    record: ImageSelectionGroupModel,
    selected_candidate_id: UUID | None,
) -> ImageSelectionGroup:
    return ImageSelectionGroup(
        id=record.id,
        run_id=record.run_id,
        group_order=record.group_order,
        range_start=record.range_start,
        range_end=record.range_end,
        fingerprint_sha256=record.fingerprint_sha256,
        board_count_consensus=record.board_count_consensus,
        status=ImageSelectionGroupStatus(record.status),
        selected_candidate_id=selected_candidate_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _candidate_from_record(
    record: ImageSelectionCandidateModel,
) -> ImageSelectionCandidate:
    return ImageSelectionCandidate(
        id=record.id,
        run_id=record.run_id,
        group_id=record.group_id,
        order_index=record.order_index,
        source_relative_path=record.source_relative_path,
        checksum_sha256=record.checksum_sha256,
        width=record.width,
        height=record.height,
        quality_metrics=dict(record.quality_metrics),
        range_confidence=record.range_confidence,
        reason_codes=tuple(record.reason_codes),
        decision=ImageSelectionCandidateDecision(record.decision),
        created_at=record.created_at,
    )


def _manual_decision_from_record(
    record: ImageSelectionManualDecisionModel,
) -> ImageSelectionManualDecision:
    return ImageSelectionManualDecision(
        idempotency_key=record.idempotency_key,
        run_id=record.run_id,
        group_id=record.group_id,
        candidate_id=record.candidate_id,
        resolution=ImageSelectionManualResolution(record.resolution),
        range_start=record.range_start,
        range_end=record.range_end,
        revision=record.revision,
        payload_sha256=record.payload_sha256,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyImageSelectionRepository"]
