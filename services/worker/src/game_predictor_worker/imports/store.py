"""PostgreSQL persistence for raw layout import staging rows."""

from __future__ import annotations

from uuid import UUID

from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.models import (
    JobModel,
    LayoutImportNormalizedRowModel,
    LayoutImportRowModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.imports.contracts import (
    LayoutImportNormalizationSource,
    NormalizedLayoutImportRow,
    RawLayoutImportRow,
    StagedLayoutImportRow,
)
from game_predictor_worker.jobs.runtime import JobHandlerError


class SqlAlchemyLayoutImportStagingStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert_rows(
        self,
        job_id: UUID,
        rows: tuple[StagedLayoutImportRow, ...],
    ) -> None:
        if not rows:
            return
        values = [
            {
                "job_id": job_id,
                "line_number": row.line_number,
                "byte_offset_end": row.byte_offset_end,
                "sequence_number": row.sequence_number,
                "cells": list(row.cells) if row.cells is not None else None,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
            for row in rows
        ]
        statement = insert(LayoutImportRowModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                LayoutImportRowModel.job_id,
                LayoutImportRowModel.line_number,
            ],
            set_={
                "byte_offset_end": statement.excluded.byte_offset_end,
                "sequence_number": statement.excluded.sequence_number,
                "cells": statement.excluded.cells,
                "error_code": statement.excluded.error_code,
                "error_message": statement.excluded.error_message,
            },
        )
        with self._session_factory() as session, session.begin():
            session.execute(statement)

    def delete_rows_after(
        self,
        job_id: UUID,
        *,
        line_number: int,
    ) -> None:
        if line_number < 0:
            raise ValueError("line_number cannot be negative.")
        with self._session_factory() as session, session.begin():
            session.execute(
                delete(LayoutImportRowModel).where(
                    LayoutImportRowModel.job_id == job_id,
                    LayoutImportRowModel.line_number > line_number,
                )
            )

    def load_normalization_source(
        self,
        *,
        validation_job_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> LayoutImportNormalizationSource:
        with self._session_factory() as session:
            validation_job = session.get(JobModel, validation_job_id)
            if (
                validation_job is None
                or validation_job.job_type is not JobType.VALIDATE
                or validation_job.game_id != game_id
            ):
                raise JobHandlerError(
                    "INVALID_LAYOUT_IMPORT_VALIDATION_JOB",
                    "The validation job identity is inconsistent.",
                )
            import_job = session.get(JobModel, import_job_id)
            if import_job is None or import_job.job_type is not JobType.IMPORT:
                raise JobHandlerError(
                    "LAYOUT_IMPORT_JOB_NOT_FOUND",
                    "The referenced layout import job does not exist.",
                )
            if import_job.game_id != game_id:
                raise JobHandlerError(
                    "LAYOUT_IMPORT_GAME_MISMATCH",
                    "The import job and validation job belong to different games.",
                )
            if import_job.status is not JobStatus.COMPLETED:
                raise JobHandlerError(
                    "LAYOUT_IMPORT_NOT_COMPLETED",
                    "The referenced layout import job is not completed.",
                )
            rules = session.get(RulesVersionModel, rules_version_id)
            if rules is None:
                raise JobHandlerError(
                    "RULES_VERSION_NOT_FOUND",
                    "The selected rules version does not exist.",
                )
            if rules.game_id != game_id:
                raise JobHandlerError(
                    "LAYOUT_IMPORT_RULES_GAME_MISMATCH",
                    "The selected rules version belongs to a different game.",
                )
            if rules.status is not RulesVersionStatus.PUBLISHED:
                raise JobHandlerError(
                    "RULES_VERSION_NOT_PUBLISHED",
                    "The selected rules version is not published.",
                )
            mobile_codes = tuple(
                session.scalars(
                    select(SymbolModel.mobile_code)
                    .join(
                        RulesVersionSymbolModel,
                        RulesVersionSymbolModel.symbol_id == SymbolModel.id,
                    )
                    .where(
                        RulesVersionSymbolModel.rules_version_id == rules_version_id,
                        RulesVersionSymbolModel.is_active.is_(True),
                        SymbolModel.game_id == game_id,
                    )
                    .order_by(SymbolModel.mobile_code)
                )
            )
            if not mobile_codes:
                raise JobHandlerError(
                    "LAYOUT_IMPORT_RULES_ALPHABET_EMPTY",
                    "The selected rules version has no active symbols.",
                )
            row_count = session.scalar(
                select(func.count())
                .select_from(LayoutImportRowModel)
                .where(LayoutImportRowModel.job_id == import_job_id)
            )
            return LayoutImportNormalizationSource(
                import_job_id=import_job_id,
                rules_version_id=rules_version_id,
                rows=rules.rows,
                columns=rules.columns,
                signature_cell_width=len(str(max(mobile_codes))),
                allowed_mobile_codes=frozenset(mobile_codes),
                row_count=int(row_count or 0),
            )

    def fetch_raw_rows(
        self,
        import_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
    ) -> tuple[RawLayoutImportRow, ...]:
        if after_line_number < 0 or limit < 1:
            raise ValueError("Raw import cursor and limit are invalid.")
        with self._session_factory() as session:
            records = tuple(
                session.scalars(
                    select(LayoutImportRowModel)
                    .where(
                        LayoutImportRowModel.job_id == import_job_id,
                        LayoutImportRowModel.line_number > after_line_number,
                    )
                    .order_by(LayoutImportRowModel.line_number)
                    .limit(limit)
                )
            )
        return tuple(
            RawLayoutImportRow(
                line_number=record.line_number,
                sequence_number=record.sequence_number,
                cells=None if record.cells is None else tuple(record.cells),
                error_code=record.error_code,
                error_message=record.error_message,
            )
            for record in records
        )

    def upsert_normalized_rows(
        self,
        validation_job_id: UUID,
        source: LayoutImportNormalizationSource,
        rows: tuple[NormalizedLayoutImportRow, ...],
    ) -> None:
        if not rows:
            return
        values = [
            {
                "validation_job_id": validation_job_id,
                "line_number": row.line_number,
                "import_job_id": source.import_job_id,
                "rules_version_id": source.rules_version_id,
                "sequence_number": row.sequence_number,
                "cells": None if row.cells is None else list(row.cells),
                "signature": row.signature,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
            for row in rows
        ]
        statement = insert(LayoutImportNormalizedRowModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                LayoutImportNormalizedRowModel.validation_job_id,
                LayoutImportNormalizedRowModel.line_number,
            ],
            set_={
                "import_job_id": statement.excluded.import_job_id,
                "rules_version_id": statement.excluded.rules_version_id,
                "sequence_number": statement.excluded.sequence_number,
                "cells": statement.excluded.cells,
                "signature": statement.excluded.signature,
                "error_code": statement.excluded.error_code,
                "error_message": statement.excluded.error_message,
            },
        )
        with self._session_factory() as session, session.begin():
            session.execute(statement)
