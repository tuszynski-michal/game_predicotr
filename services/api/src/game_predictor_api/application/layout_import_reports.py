"""Application service and repository port for normalized import reports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.datasets import DatasetVersion
from game_predictor_api.domain.jobs import JobConflictError, JobNotFoundError
from game_predictor_api.domain.layout_import_reports import (
    IMPORT_REPORT_SAMPLE_LIMIT,
    LayoutImportIntegrityReport,
    LayoutImportIntegritySource,
    LayoutImportNormalizedRow,
    LayoutImportNormalizedRowPage,
    LayoutImportPublicationSource,
    LayoutImportRowStatus,
    LayoutImportStagingRejection,
    LayoutImportValidationReference,
    build_layout_import_integrity_report,
)


class LayoutImportReportRepository(Protocol):
    def get_validation_reference(
        self,
        validation_job_id: UUID,
    ) -> LayoutImportValidationReference | None: ...

    def get_integrity_source(
        self,
        validation_job_id: UUID,
        *,
        sample_limit: int,
    ) -> LayoutImportIntegritySource: ...

    def list_normalized_rows(
        self,
        validation_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
        row_status: LayoutImportRowStatus,
        error_code: str | None,
    ) -> Sequence[LayoutImportNormalizedRow]: ...

    def reject_staging(
        self,
        validation_job_id: UUID,
        import_job_id: UUID,
    ) -> LayoutImportStagingRejection: ...

    def get_locked_publication_source(
        self,
        validation_job_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> LayoutImportPublicationSource | None: ...

    def publish_staging(
        self,
        source: LayoutImportPublicationSource,
    ) -> DatasetVersion: ...


class LayoutImportReportService:
    def __init__(self, repository: LayoutImportReportRepository) -> None:
        self._repository = repository

    def get_integrity_report(
        self,
        validation_job_id: UUID,
    ) -> LayoutImportIntegrityReport:
        reference = self._completed_reference(validation_job_id)
        source = self._repository.get_integrity_source(
            validation_job_id,
            sample_limit=IMPORT_REPORT_SAMPLE_LIMIT,
        )
        return build_layout_import_integrity_report(reference, source)

    def list_normalized_rows(
        self,
        validation_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
        row_status: LayoutImportRowStatus,
        error_code: str | None,
    ) -> LayoutImportNormalizedRowPage:
        reference = self._completed_reference(validation_job_id)
        if row_status is LayoutImportRowStatus.VALID and error_code is not None:
            raise JobConflictError(
                "INVALID_LAYOUT_IMPORT_ROW_FILTER",
                "errorCode cannot be combined with the valid row status.",
            )
        records = tuple(
            self._repository.list_normalized_rows(
                validation_job_id,
                after_line_number=after_line_number,
                limit=limit + 1,
                row_status=row_status,
                error_code=error_code,
            )
        )
        has_next_page = len(records) > limit
        items = records[:limit]
        if (
            reference.import_job_id is None
            or reference.rules_version_id is None
            or reference.rows is None
            or reference.columns is None
        ):
            raise RuntimeError("Validated import metadata disappeared.")
        return LayoutImportNormalizedRowPage(
            validation_job_id=reference.validation_job_id,
            import_job_id=reference.import_job_id,
            rules_version_id=reference.rules_version_id,
            rows=reference.rows,
            columns=reference.columns,
            items=items,
            next_after_line_number=(items[-1].line_number if has_next_page and items else None),
        )

    def _completed_reference(
        self,
        validation_job_id: UUID,
    ) -> LayoutImportValidationReference:
        reference = self._repository.get_validation_reference(validation_job_id)
        if reference is None:
            raise JobNotFoundError(
                "LAYOUT_IMPORT_VALIDATION_NOT_FOUND",
                "Layout import validation job does not exist.",
                details={"validationJobId": str(validation_job_id)},
            )
        self._validate_completed_reference(reference)
        return reference

    def reject_staging(
        self,
        validation_job_id: UUID,
    ) -> LayoutImportStagingRejection:
        reference = self._completed_reference(validation_job_id)
        if reference.import_job_id is None:
            raise RuntimeError("Validated import metadata disappeared.")
        return self._repository.reject_staging(
            validation_job_id,
            reference.import_job_id,
        )

    def publish_dataset(
        self,
        validation_job_id: UUID,
    ) -> DatasetVersion:
        reference = self._completed_reference(validation_job_id)
        if reference.import_job_id is None or reference.rules_version_id is None:
            raise RuntimeError("Validated import metadata disappeared.")
        source = self._repository.get_locked_publication_source(
            validation_job_id,
            reference.import_job_id,
            reference.rules_version_id,
        )
        if source is None:
            raise JobConflictError(
                "LAYOUT_IMPORT_PUBLICATION_SOURCE_INVALID",
                "The locked layout import publication source is no longer valid.",
                details={"validationJobId": str(validation_job_id)},
            )
        self._validate_completed_reference(source.reference)
        if source.existing_dataset is not None:
            return source.existing_dataset
        if not source.rules_are_published:
            raise JobConflictError(
                "LAYOUT_IMPORT_RULES_NOT_PUBLISHED",
                "The validation rules version must remain published.",
                details={"rulesVersionId": str(source.reference.rules_version_id)},
            )
        report = build_layout_import_integrity_report(
            source.reference,
            source.integrity_source,
        )
        if not report.ready_for_publication:
            raise JobConflictError(
                "LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION",
                "The layout import has publication blockers.",
                details={
                    "validationJobId": str(validation_job_id),
                    "issues": [
                        {
                            "code": check.code,
                            "issueCount": check.issue_count,
                            "message": check.message,
                            "truncated": check.truncated,
                        }
                        for check in report.checks
                        if check.status.value == "blocking"
                    ],
                },
            )
        return self._repository.publish_staging(source)

    @staticmethod
    def _validate_completed_reference(
        reference: LayoutImportValidationReference,
    ) -> None:
        if not reference.is_layout_import_validation:
            raise JobConflictError(
                "LAYOUT_IMPORT_VALIDATION_KIND_MISMATCH",
                "The selected job is not a layout import validation.",
                details={"validationJobId": str(reference.validation_job_id)},
            )
        if not reference.is_completed:
            raise JobConflictError(
                "LAYOUT_IMPORT_VALIDATION_NOT_COMPLETED",
                "The layout import validation must be completed first.",
                details={"validationJobId": str(reference.validation_job_id)},
            )
        if (
            reference.import_job_id is None
            or reference.rules_version_id is None
            or reference.rows is None
            or reference.columns is None
        ):
            raise JobConflictError(
                "LAYOUT_IMPORT_VALIDATION_METADATA_INVALID",
                "The layout import validation metadata is incomplete.",
                details={"validationJobId": str(reference.validation_job_id)},
            )
