"""PostgreSQL aggregates and bounded samples for normalized import reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, insert, literal, null, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from game_predictor_api.application.layout_import_reports import (
    LayoutImportReportRepository,
)
from game_predictor_api.domain.datasets import DatasetVersion, DatasetVersionStatus
from game_predictor_api.domain.jobs import JobConflictError, JobStatus, JobType
from game_predictor_api.domain.layout_import_reports import (
    IMPORT_REPORT_SAMPLE_LIMIT,
    LAYOUT_IMPORT_GENERATOR_VERSION,
    LayoutImportDuplicateSequenceGroup,
    LayoutImportDuplicateSignatureGroup,
    LayoutImportErrorCodeCount,
    LayoutImportIntegritySource,
    LayoutImportNormalizedRow,
    LayoutImportPublicationSource,
    LayoutImportRowStatus,
    LayoutImportStagingRejection,
    LayoutImportValidationReference,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    JobModel,
    LayoutImportNormalizedRowModel,
    LayoutImportRowModel,
    LayoutModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)


class SqlAlchemyLayoutImportReportRepository(LayoutImportReportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_validation_reference(
        self,
        validation_job_id: UUID,
    ) -> LayoutImportValidationReference | None:
        job = self._session.get(JobModel, validation_job_id)
        if job is None:
            return None
        payload = dict(job.input_payload)
        import_job_id = _payload_uuid(payload, "import_job_id")
        rules_version_id = _payload_uuid(payload, "rules_version_id")
        rules = (
            None
            if rules_version_id is None
            else self._session.get(RulesVersionModel, rules_version_id)
        )
        return LayoutImportValidationReference(
            validation_job_id=job.id,
            import_job_id=import_job_id,
            rules_version_id=rules_version_id,
            is_layout_import_validation=(
                job.job_type is JobType.VALIDATE
                and payload.get("validation_kind") == "layout_import"
            ),
            is_completed=job.status is JobStatus.COMPLETED,
            expected_row_count=job.progress_total,
            rows=None if rules is None else rules.rows,
            columns=None if rules is None else rules.columns,
        )

    def get_integrity_source(
        self,
        validation_job_id: UUID,
        *,
        sample_limit: int,
    ) -> LayoutImportIntegritySource:
        row = self._session.execute(
            select(
                func.count(LayoutImportNormalizedRowModel.line_number),
                func.count(LayoutImportNormalizedRowModel.line_number).filter(
                    LayoutImportNormalizedRowModel.error_code.is_(None)
                ),
                func.count(LayoutImportNormalizedRowModel.line_number).filter(
                    LayoutImportNormalizedRowModel.error_code.is_not(None)
                ),
                func.min(LayoutImportNormalizedRowModel.sequence_number).filter(
                    LayoutImportNormalizedRowModel.error_code.is_(None)
                ),
                func.max(LayoutImportNormalizedRowModel.sequence_number).filter(
                    LayoutImportNormalizedRowModel.error_code.is_(None)
                ),
                func.count(func.distinct(LayoutImportNormalizedRowModel.sequence_number)).filter(
                    LayoutImportNormalizedRowModel.error_code.is_(None)
                ),
            ).where(LayoutImportNormalizedRowModel.validation_job_id == validation_job_id)
        ).one()
        (
            actual_row_count,
            valid_row_count,
            invalid_row_count,
            min_sequence_number,
            max_sequence_number,
            unique_sequence_count,
        ) = row
        maximum = None if max_sequence_number is None else int(max_sequence_number)
        unique_count = int(unique_sequence_count)
        missing_count = 0 if maximum is None else maximum - unique_count

        duplicate_sequence_query = (
            select(
                LayoutImportNormalizedRowModel.sequence_number.label("sequence_number"),
                func.count().label("occurrence_count"),
            )
            .where(
                LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
                LayoutImportNormalizedRowModel.error_code.is_(None),
            )
            .group_by(LayoutImportNormalizedRowModel.sequence_number)
            .having(func.count() > 1)
        )
        duplicate_sequence_groups = duplicate_sequence_query.subquery()
        sequence_aggregate = self._session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(duplicate_sequence_groups.c.occurrence_count),
                    0,
                ),
                func.coalesce(
                    func.sum(duplicate_sequence_groups.c.occurrence_count - 1),
                    0,
                ),
            ).select_from(duplicate_sequence_groups)
        ).one()
        sequence_group_count = int(sequence_aggregate[0])
        sampled_sequence_rows = self._session.execute(
            duplicate_sequence_query.order_by(LayoutImportNormalizedRowModel.sequence_number).limit(
                sample_limit
            )
        ).all()
        sampled_sequence_numbers = tuple(
            int(item.sequence_number) for item in sampled_sequence_rows
        )
        sequence_lines = self._sample_lines_by_sequence(
            validation_job_id,
            sampled_sequence_numbers,
            sample_limit=sample_limit,
        )
        duplicate_sequences = tuple(
            LayoutImportDuplicateSequenceGroup(
                sequence_number=int(item.sequence_number),
                occurrence_count=int(item.occurrence_count),
                line_numbers=sequence_lines[int(item.sequence_number)],
                truncated=int(item.occurrence_count) > sample_limit,
            )
            for item in sampled_sequence_rows
        )

        duplicate_signature_query = (
            select(
                LayoutImportNormalizedRowModel.signature.label("signature"),
                func.count().label("occurrence_count"),
            )
            .where(
                LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
                LayoutImportNormalizedRowModel.error_code.is_(None),
            )
            .group_by(LayoutImportNormalizedRowModel.signature)
            .having(func.count() > 1)
        )
        duplicate_signature_groups = duplicate_signature_query.subquery()
        signature_aggregate = self._session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(duplicate_signature_groups.c.occurrence_count),
                    0,
                ),
                func.coalesce(
                    func.sum(duplicate_signature_groups.c.occurrence_count - 1),
                    0,
                ),
            ).select_from(duplicate_signature_groups)
        ).one()
        signature_group_count = int(signature_aggregate[0])
        sampled_signature_rows = self._session.execute(
            duplicate_signature_query.order_by(LayoutImportNormalizedRowModel.signature).limit(
                sample_limit
            )
        ).all()
        sampled_signatures = tuple(str(item.signature) for item in sampled_signature_rows)
        signature_lines = self._sample_signature_values(
            validation_job_id,
            sampled_signatures,
            value_column="line_number",
            sample_limit=sample_limit,
        )
        signature_sequences = self._sample_signature_values(
            validation_job_id,
            sampled_signatures,
            value_column="sequence_number",
            sample_limit=sample_limit,
        )
        duplicate_signatures = tuple(
            LayoutImportDuplicateSignatureGroup(
                signature=str(item.signature),
                occurrence_count=int(item.occurrence_count),
                sequence_numbers=signature_sequences[str(item.signature)],
                line_numbers=signature_lines[str(item.signature)],
                sequence_numbers_truncated=(int(item.occurrence_count) > sample_limit),
                line_numbers_truncated=(int(item.occurrence_count) > sample_limit),
            )
            for item in sampled_signature_rows
        )

        error_code_counts = tuple(
            LayoutImportErrorCodeCount(code=str(code), count=int(count))
            for code, count in self._session.execute(
                select(
                    LayoutImportNormalizedRowModel.error_code,
                    func.count(),
                )
                .where(
                    LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
                    LayoutImportNormalizedRowModel.error_code.is_not(None),
                )
                .group_by(LayoutImportNormalizedRowModel.error_code)
                .order_by(LayoutImportNormalizedRowModel.error_code)
            ).all()
        )
        return LayoutImportIntegritySource(
            actual_row_count=int(actual_row_count),
            valid_row_count=int(valid_row_count),
            invalid_row_count=int(invalid_row_count),
            min_sequence_number=(None if min_sequence_number is None else int(min_sequence_number)),
            max_sequence_number=maximum,
            unique_sequence_count=unique_count,
            missing_sequence_count=missing_count,
            missing_sequence_numbers=self._sample_missing_sequence_numbers(
                validation_job_id,
                sample_limit=sample_limit,
            ),
            duplicate_sequence_group_count=sequence_group_count,
            duplicate_sequence_affected_row_count=int(sequence_aggregate[1]),
            duplicate_sequence_excess_row_count=int(sequence_aggregate[2]),
            duplicate_sequences=duplicate_sequences,
            duplicate_signature_group_count=signature_group_count,
            duplicate_signature_affected_row_count=int(signature_aggregate[1]),
            duplicate_signature_excess_row_count=int(signature_aggregate[2]),
            duplicate_signatures=duplicate_signatures,
            error_code_counts=error_code_counts,
        )

    def list_normalized_rows(
        self,
        validation_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
        row_status: LayoutImportRowStatus,
        error_code: str | None,
    ) -> list[LayoutImportNormalizedRow]:
        statement = select(LayoutImportNormalizedRowModel).where(
            LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
            LayoutImportNormalizedRowModel.line_number > after_line_number,
        )
        if row_status is LayoutImportRowStatus.VALID:
            statement = statement.where(LayoutImportNormalizedRowModel.error_code.is_(None))
        elif row_status is LayoutImportRowStatus.INVALID:
            statement = statement.where(LayoutImportNormalizedRowModel.error_code.is_not(None))
        if error_code is not None:
            statement = statement.where(LayoutImportNormalizedRowModel.error_code == error_code)
        records = self._session.scalars(
            statement.order_by(LayoutImportNormalizedRowModel.line_number).limit(limit)
        )
        return [
            LayoutImportNormalizedRow(
                line_number=record.line_number,
                sequence_number=record.sequence_number,
                cells=None if record.cells is None else tuple(record.cells),
                signature=record.signature,
                error_code=record.error_code,
                error_message=record.error_message,
            )
            for record in records
        ]

    def reject_staging(
        self,
        validation_job_id: UUID,
        import_job_id: UUID,
    ) -> LayoutImportStagingRejection:
        import_job = self._session.scalar(
            select(JobModel).where(JobModel.id == import_job_id).with_for_update()
        )
        if import_job is None:
            raise JobConflictError(
                "LAYOUT_IMPORT_PUBLICATION_SOURCE_INVALID",
                "The raw layout import job no longer exists.",
                details={"importJobId": str(import_job_id)},
            )
        validation_jobs = tuple(
            self._session.scalars(
                select(JobModel)
                .where(
                    JobModel.job_type == JobType.VALIDATE,
                    JobModel.input_payload["validation_kind"].astext == "layout_import",
                    JobModel.input_payload["import_job_id"].astext == str(import_job_id),
                )
                .order_by(JobModel.id)
                .with_for_update()
            )
        )
        active_validation = next(
            (
                job
                for job in validation_jobs
                if job.status
                in {
                    JobStatus.CREATED,
                    JobStatus.PROCESSING,
                    JobStatus.WAITING_FOR_REVIEW,
                }
            ),
            None,
        )
        if active_validation is not None:
            raise JobConflictError(
                "LAYOUT_IMPORT_STAGING_VALIDATION_ACTIVE",
                "The import staging is used by an active validation job.",
                details={
                    "importJobId": str(import_job_id),
                    "validationJobId": str(active_validation.id),
                },
            )

        source_job_ids = [import_job_id, *(job.id for job in validation_jobs)]
        dataset = self._session.execute(
            select(
                DatasetVersionModel.id,
                DatasetVersionModel.status,
            )
            .where(DatasetVersionModel.source_job_id.in_(source_job_ids))
            .limit(1)
        ).one_or_none()
        if dataset is not None:
            dataset_id, dataset_status = dataset
            raise JobConflictError(
                "LAYOUT_IMPORT_STAGING_IN_USE",
                "The import staging is already referenced by a dataset.",
                details={
                    "datasetVersionId": str(dataset_id),
                    "datasetStatus": DatasetVersionStatus(dataset_status).value,
                    "importJobId": str(import_job_id),
                },
            )

        normalized_delete = cast(
            CursorResult[Any],
            self._session.execute(
                delete(LayoutImportNormalizedRowModel).where(
                    LayoutImportNormalizedRowModel.import_job_id == import_job_id
                )
            ),
        )
        raw_delete = cast(
            CursorResult[Any],
            self._session.execute(
                delete(LayoutImportRowModel).where(LayoutImportRowModel.job_id == import_job_id)
            ),
        )
        return LayoutImportStagingRejection(
            validation_job_id=validation_job_id,
            import_job_id=import_job_id,
            deleted_normalized_row_count=int(normalized_delete.rowcount or 0),
            deleted_raw_row_count=int(raw_delete.rowcount or 0),
        )

    def get_locked_publication_source(
        self,
        validation_job_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> LayoutImportPublicationSource | None:
        import_job = self._session.scalar(
            select(JobModel).where(JobModel.id == import_job_id).with_for_update()
        )
        if (
            import_job is None
            or import_job.job_type is not JobType.IMPORT
            or import_job.status is not JobStatus.COMPLETED
        ):
            return None
        validation_jobs = tuple(
            self._session.scalars(
                select(JobModel)
                .where(
                    JobModel.job_type == JobType.VALIDATE,
                    JobModel.input_payload["validation_kind"].astext == "layout_import",
                    JobModel.input_payload["import_job_id"].astext == str(import_job_id),
                )
                .order_by(JobModel.id)
                .with_for_update()
            )
        )
        validation_job = next(
            (job for job in validation_jobs if job.id == validation_job_id),
            None,
        )
        if validation_job is None:
            return None
        payload = dict(validation_job.input_payload)
        if _payload_uuid(payload, "rules_version_id") != rules_version_id:
            return None
        rules = self._session.scalar(
            select(RulesVersionModel)
            .where(RulesVersionModel.id == rules_version_id)
            .with_for_update()
        )
        if (
            rules is None
            or validation_job.game_id is None
            or rules.game_id != validation_job.game_id
        ):
            return None
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == validation_job.game_id).with_for_update()
        )
        if game is None:
            return None
        maximum_mobile_code = self._session.scalar(
            select(func.max(SymbolModel.mobile_code))
            .join(
                RulesVersionSymbolModel,
                RulesVersionSymbolModel.symbol_id == SymbolModel.id,
            )
            .where(
                RulesVersionSymbolModel.rules_version_id == rules_version_id,
                RulesVersionSymbolModel.is_active.is_(True),
                SymbolModel.game_id == validation_job.game_id,
            )
        )
        if maximum_mobile_code is None:
            return None
        reference = LayoutImportValidationReference(
            validation_job_id=validation_job.id,
            import_job_id=import_job.id,
            rules_version_id=rules.id,
            is_layout_import_validation=(
                validation_job.job_type is JobType.VALIDATE
                and payload.get("validation_kind") == "layout_import"
            ),
            is_completed=validation_job.status is JobStatus.COMPLETED,
            expected_row_count=validation_job.progress_total,
            rows=rules.rows,
            columns=rules.columns,
        )
        existing_record = self._session.scalar(
            select(DatasetVersionModel).where(
                DatasetVersionModel.source_job_id == validation_job_id
            )
        )
        return LayoutImportPublicationSource(
            reference=reference,
            integrity_source=self.get_integrity_source(
                validation_job_id,
                sample_limit=IMPORT_REPORT_SAMPLE_LIMIT,
            ),
            game_id=validation_job.game_id,
            signature_cell_width=len(str(int(maximum_mobile_code))),
            expected_layout_count=game.expected_layout_count,
            rules_are_published=rules.status is RulesVersionStatus.PUBLISHED,
            existing_dataset=(
                None if existing_record is None else _to_dataset_version(existing_record)
            ),
        )

    def publish_staging(
        self,
        source: LayoutImportPublicationSource,
    ) -> DatasetVersion:
        latest_version = self._session.scalar(
            select(func.max(DatasetVersionModel.version)).where(
                DatasetVersionModel.game_id == source.game_id
            )
        )
        record = DatasetVersionModel(
            game_id=source.game_id,
            version=(latest_version or 0) + 1,
            rows=source.reference.rows,
            columns=source.reference.columns,
            signature_cell_width=source.signature_cell_width,
            expected_layout_count=source.expected_layout_count,
            layout_count=source.integrity_source.valid_row_count,
            status=DatasetVersionStatus.STAGING,
            generation_seed=0,
            generator_version=LAYOUT_IMPORT_GENERATOR_VERSION,
            source_job_id=source.reference.validation_job_id,
        )
        self._session.add(record)
        self._session.flush()
        self._session.execute(
            insert(LayoutModel).from_select(
                [
                    "dataset_version_id",
                    "sequence_number",
                    "signature",
                    "cells",
                    "source_board_id",
                ],
                select(
                    literal(record.id),
                    LayoutImportNormalizedRowModel.sequence_number,
                    LayoutImportNormalizedRowModel.signature,
                    LayoutImportNormalizedRowModel.cells,
                    null(),
                ).where(
                    LayoutImportNormalizedRowModel.validation_job_id
                    == source.reference.validation_job_id,
                    LayoutImportNormalizedRowModel.error_code.is_(None),
                ),
            )
        )
        inserted_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(LayoutModel)
                .where(LayoutModel.dataset_version_id == record.id)
            )
            or 0
        )
        if inserted_count != source.integrity_source.valid_row_count:
            raise JobConflictError(
                "LAYOUT_IMPORT_PUBLICATION_ROW_COUNT_CHANGED",
                "The normalized staging changed during dataset publication.",
                details={
                    "expectedRowCount": source.integrity_source.valid_row_count,
                    "insertedRowCount": inserted_count,
                    "validationJobId": str(source.reference.validation_job_id),
                },
            )
        record.status = DatasetVersionStatus.PUBLISHED
        record.published_at = datetime.now(UTC)
        self._session.flush()
        return _to_dataset_version(record)

    def _sample_missing_sequence_numbers(
        self,
        validation_job_id: UUID,
        *,
        sample_limit: int,
    ) -> tuple[int, ...]:
        distinct_numbers = (
            select(LayoutImportNormalizedRowModel.sequence_number.label("sequence_number"))
            .where(
                LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
                LayoutImportNormalizedRowModel.error_code.is_(None),
            )
            .distinct()
            .subquery()
        )
        with_previous = select(
            distinct_numbers.c.sequence_number,
            func.lag(
                distinct_numbers.c.sequence_number,
                1,
                0,
            )
            .over(order_by=distinct_numbers.c.sequence_number)
            .label("previous_sequence_number"),
        ).subquery()
        intervals = self._session.execute(
            select(
                (with_previous.c.previous_sequence_number + 1).label("gap_start"),
                (with_previous.c.sequence_number - 1).label("gap_end"),
            )
            .where(with_previous.c.sequence_number > with_previous.c.previous_sequence_number + 1)
            .order_by(with_previous.c.sequence_number)
            .limit(sample_limit + 1)
        ).all()
        missing: list[int] = []
        for interval in intervals:
            for sequence_number in range(
                int(interval.gap_start),
                int(interval.gap_end) + 1,
            ):
                missing.append(sequence_number)
                if len(missing) == sample_limit:
                    return tuple(missing)
        return tuple(missing)

    def _sample_lines_by_sequence(
        self,
        validation_job_id: UUID,
        sequence_numbers: tuple[int, ...],
        *,
        sample_limit: int,
    ) -> defaultdict[int, tuple[int, ...]]:
        result: defaultdict[int, tuple[int, ...]] = defaultdict(tuple)
        if not sequence_numbers:
            return result
        ranked = select(
            LayoutImportNormalizedRowModel.sequence_number.label("sequence_number"),
            LayoutImportNormalizedRowModel.line_number.label("line_number"),
            func.row_number()
            .over(
                partition_by=LayoutImportNormalizedRowModel.sequence_number,
                order_by=LayoutImportNormalizedRowModel.line_number,
            )
            .label("occurrence_index"),
        ).where(
            LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
            LayoutImportNormalizedRowModel.error_code.is_(None),
            LayoutImportNormalizedRowModel.sequence_number.in_(sequence_numbers),
        )
        ranked_rows = ranked.subquery()
        sampled = self._session.execute(
            select(
                ranked_rows.c.sequence_number,
                ranked_rows.c.line_number,
            )
            .where(ranked_rows.c.occurrence_index <= sample_limit)
            .order_by(
                ranked_rows.c.sequence_number,
                ranked_rows.c.line_number,
            )
        ).all()
        mutable: defaultdict[int, list[int]] = defaultdict(list)
        for sequence_number, line_number in sampled:
            mutable[int(sequence_number)].append(int(line_number))
        for sequence_number, line_numbers in mutable.items():
            result[sequence_number] = tuple(line_numbers)
        return result

    def _sample_signature_values(
        self,
        validation_job_id: UUID,
        signatures: tuple[str, ...],
        *,
        value_column: str,
        sample_limit: int,
    ) -> defaultdict[str, tuple[int, ...]]:
        result: defaultdict[str, tuple[int, ...]] = defaultdict(tuple)
        if not signatures:
            return result
        selected_value = (
            LayoutImportNormalizedRowModel.line_number
            if value_column == "line_number"
            else LayoutImportNormalizedRowModel.sequence_number
        )
        ranked = select(
            LayoutImportNormalizedRowModel.signature.label("signature"),
            selected_value.label("sample_value"),
            func.row_number()
            .over(
                partition_by=LayoutImportNormalizedRowModel.signature,
                order_by=selected_value,
            )
            .label("occurrence_index"),
        ).where(
            LayoutImportNormalizedRowModel.validation_job_id == validation_job_id,
            LayoutImportNormalizedRowModel.error_code.is_(None),
            LayoutImportNormalizedRowModel.signature.in_(signatures),
        )
        ranked_rows = ranked.subquery()
        sampled = self._session.execute(
            select(
                ranked_rows.c.signature,
                ranked_rows.c.sample_value,
            )
            .where(ranked_rows.c.occurrence_index <= sample_limit)
            .order_by(
                ranked_rows.c.signature,
                ranked_rows.c.sample_value,
            )
        ).all()
        mutable: defaultdict[str, list[int]] = defaultdict(list)
        for signature, value in sampled:
            mutable[str(signature)].append(int(value))
        for signature, values in mutable.items():
            result[signature] = tuple(values)
        return result


def _payload_uuid(payload: dict[str, object], key: str) -> UUID | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _to_dataset_version(record: DatasetVersionModel) -> DatasetVersion:
    return DatasetVersion(
        id=record.id,
        game_id=record.game_id,
        version=record.version,
        rows=record.rows,
        columns=record.columns,
        signature_cell_width=record.signature_cell_width,
        expected_layout_count=record.expected_layout_count,
        layout_count=record.layout_count,
        status=record.status,
        generation_seed=record.generation_seed,
        generator_version=record.generator_version,
        source_job_id=record.source_job_id,
        created_at=record.created_at,
        published_at=record.published_at,
    )
