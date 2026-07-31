from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.layout_import_reports import (
    LayoutImportReportService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.datasets import DatasetVersion, DatasetVersionStatus
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.layout_import_reports import (
    LayoutImportDuplicateSequenceGroup,
    LayoutImportDuplicateSignatureGroup,
    LayoutImportErrorCodeCount,
    LayoutImportIntegrityCheckCode,
    LayoutImportIntegrityCheckStatus,
    LayoutImportIntegritySource,
    LayoutImportNormalizedRow,
    LayoutImportPublicationSource,
    LayoutImportRowStatus,
    LayoutImportStagingRejection,
    LayoutImportValidationReference,
    build_layout_import_integrity_report,
)
from game_predictor_api.main import create_app


class MemoryLayoutImportReportRepository:
    def __init__(
        self,
        reference: LayoutImportValidationReference,
        source: LayoutImportIntegritySource,
        rows: Sequence[LayoutImportNormalizedRow] = (),
    ) -> None:
        self.reference = reference
        self.source = source
        self.rows = tuple(rows)
        self.rejections: list[tuple[UUID, UUID]] = []
        self.game_id = uuid4()
        self.published_sources: list[LayoutImportPublicationSource] = []

    def get_validation_reference(
        self,
        validation_job_id: UUID,
    ) -> LayoutImportValidationReference | None:
        if validation_job_id != self.reference.validation_job_id:
            return None
        return self.reference

    def get_integrity_source(
        self,
        validation_job_id: UUID,
        *,
        sample_limit: int,
    ) -> LayoutImportIntegritySource:
        assert validation_job_id == self.reference.validation_job_id
        assert sample_limit == 100
        return self.source

    def list_normalized_rows(
        self,
        validation_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
        row_status: LayoutImportRowStatus,
        error_code: str | None,
    ) -> Sequence[LayoutImportNormalizedRow]:
        assert validation_job_id == self.reference.validation_job_id
        filtered = [
            row
            for row in self.rows
            if row.line_number > after_line_number
            and (
                row_status is LayoutImportRowStatus.ALL
                or (row_status is LayoutImportRowStatus.VALID and row.error_code is None)
                or (row_status is LayoutImportRowStatus.INVALID and row.error_code is not None)
            )
            and (error_code is None or row.error_code == error_code)
        ]
        return filtered[:limit]

    def reject_staging(
        self,
        validation_job_id: UUID,
        import_job_id: UUID,
    ) -> LayoutImportStagingRejection:
        self.rejections.append((validation_job_id, import_job_id))
        return LayoutImportStagingRejection(
            validation_job_id=validation_job_id,
            import_job_id=import_job_id,
            deleted_normalized_row_count=len(self.rows),
            deleted_raw_row_count=len(self.rows),
        )

    def get_locked_publication_source(
        self,
        validation_job_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> LayoutImportPublicationSource | None:
        assert validation_job_id == self.reference.validation_job_id
        assert import_job_id == self.reference.import_job_id
        assert rules_version_id == self.reference.rules_version_id
        return LayoutImportPublicationSource(
            reference=self.reference,
            integrity_source=self.source,
            game_id=self.game_id,
            signature_cell_width=2,
            expected_layout_count=self.source.valid_row_count,
            rules_are_published=True,
            existing_dataset=None,
        )

    def publish_staging(
        self,
        source: LayoutImportPublicationSource,
    ) -> DatasetVersion:
        self.published_sources.append(source)
        now = datetime.now(UTC)
        return DatasetVersion(
            id=uuid4(),
            game_id=source.game_id,
            version=1,
            rows=source.reference.rows or 0,
            columns=source.reference.columns or 0,
            signature_cell_width=source.signature_cell_width,
            expected_layout_count=source.expected_layout_count,
            layout_count=source.integrity_source.valid_row_count,
            status=DatasetVersionStatus.PUBLISHED,
            generation_seed=0,
            generator_version="layout-import-v1",
            source_job_id=source.reference.validation_job_id,
            created_at=now,
            published_at=now,
        )


def _reference() -> LayoutImportValidationReference:
    return LayoutImportValidationReference(
        validation_job_id=uuid4(),
        import_job_id=uuid4(),
        rules_version_id=uuid4(),
        is_layout_import_validation=True,
        is_completed=True,
        expected_row_count=6,
        rows=3,
        columns=5,
    )


def _integrity_source() -> LayoutImportIntegritySource:
    return LayoutImportIntegritySource(
        actual_row_count=6,
        valid_row_count=4,
        invalid_row_count=2,
        min_sequence_number=1,
        max_sequence_number=4,
        unique_sequence_count=3,
        missing_sequence_count=1,
        missing_sequence_numbers=(3,),
        duplicate_sequence_group_count=1,
        duplicate_sequence_affected_row_count=2,
        duplicate_sequence_excess_row_count=1,
        duplicate_sequences=(
            LayoutImportDuplicateSequenceGroup(
                sequence_number=2,
                occurrence_count=2,
                line_numbers=(2, 3),
                truncated=False,
            ),
        ),
        duplicate_signature_group_count=2,
        duplicate_signature_affected_row_count=4,
        duplicate_signature_excess_row_count=2,
        duplicate_signatures=(
            LayoutImportDuplicateSignatureGroup(
                signature="0101",
                occurrence_count=2,
                sequence_numbers=(1, 4),
                line_numbers=(1, 4),
                sequence_numbers_truncated=False,
                line_numbers_truncated=False,
            ),
            LayoutImportDuplicateSignatureGroup(
                signature="0202",
                occurrence_count=2,
                sequence_numbers=(2, 2),
                line_numbers=(2, 3),
                sequence_numbers_truncated=False,
                line_numbers_truncated=False,
            ),
        ),
        error_code_counts=(
            LayoutImportErrorCodeCount(
                code="import_record_invalid",
                count=1,
            ),
            LayoutImportErrorCodeCount(
                code="import_symbol_not_in_rules",
                count=1,
            ),
        ),
    )


def test_integrity_report_blocks_invalid_gaps_and_duplicate_numbers() -> None:
    report = build_layout_import_integrity_report(
        _reference(),
        _integrity_source(),
    )

    assert report.ready_for_publication is False
    assert report.expected_row_count == report.actual_row_count == 6
    assert report.missing_sequence_numbers == (3,)
    assert report.duplicate_sequences[0].line_numbers == (2, 3)
    checks = {check.code: check for check in report.checks}
    assert (
        checks[LayoutImportIntegrityCheckCode.INVALID_IMPORT_ROW].status
        is LayoutImportIntegrityCheckStatus.BLOCKING
    )
    assert (
        checks[LayoutImportIntegrityCheckCode.DUPLICATE_SIGNATURE].status
        is LayoutImportIntegrityCheckStatus.WARNING
    )


def test_duplicate_signature_warning_does_not_block_clean_import() -> None:
    source = replace(
        _integrity_source(),
        actual_row_count=4,
        valid_row_count=4,
        invalid_row_count=0,
        unique_sequence_count=4,
        missing_sequence_count=0,
        missing_sequence_numbers=(),
        duplicate_sequence_group_count=0,
        duplicate_sequence_affected_row_count=0,
        duplicate_sequence_excess_row_count=0,
        duplicate_sequences=(),
        duplicate_signature_group_count=1,
        duplicate_signature_affected_row_count=2,
        duplicate_signature_excess_row_count=1,
        duplicate_signatures=(_integrity_source().duplicate_signatures[0],),
        error_code_counts=(),
    )
    report = build_layout_import_integrity_report(
        replace(_reference(), expected_row_count=4),
        source,
    )

    assert report.ready_for_publication is True
    assert report.duplicate_signature_group_count == 1
    assert report.checks[-1].status is LayoutImportIntegrityCheckStatus.WARNING


def _clean_integrity_source() -> LayoutImportIntegritySource:
    return replace(
        _integrity_source(),
        actual_row_count=4,
        valid_row_count=4,
        invalid_row_count=0,
        unique_sequence_count=4,
        missing_sequence_count=0,
        missing_sequence_numbers=(),
        duplicate_sequence_group_count=0,
        duplicate_sequence_affected_row_count=0,
        duplicate_sequence_excess_row_count=0,
        duplicate_sequences=(),
        duplicate_signature_group_count=1,
        duplicate_signature_affected_row_count=2,
        duplicate_signature_excess_row_count=1,
        duplicate_signatures=(_integrity_source().duplicate_signatures[0],),
        error_code_counts=(),
    )


def test_service_publishes_only_ready_import_and_preserves_provenance() -> None:
    reference = replace(_reference(), expected_row_count=4)
    repository = MemoryLayoutImportReportRepository(
        reference,
        _clean_integrity_source(),
    )
    service = LayoutImportReportService(repository)

    dataset = service.publish_dataset(reference.validation_job_id)

    assert dataset.status is DatasetVersionStatus.PUBLISHED
    assert dataset.source_job_id == reference.validation_job_id
    assert dataset.generator_version == "layout-import-v1"
    assert dataset.layout_count == 4
    assert len(repository.published_sources) == 1


def test_service_does_not_publish_import_with_blockers() -> None:
    reference = _reference()
    repository = MemoryLayoutImportReportRepository(
        reference,
        _integrity_source(),
    )

    with pytest.raises(
        JobConflictError,
        match="publication blockers",
    ):
        LayoutImportReportService(repository).publish_dataset(reference.validation_job_id)

    assert repository.published_sources == []


def test_duplicate_number_check_bounds_flattened_line_sample() -> None:
    groups = tuple(
        LayoutImportDuplicateSequenceGroup(
            sequence_number=sequence_number,
            occurrence_count=2,
            line_numbers=(
                sequence_number * 2 - 1,
                sequence_number * 2,
            ),
            truncated=False,
        )
        for sequence_number in range(1, 61)
    )
    source = replace(
        _integrity_source(),
        duplicate_sequence_group_count=len(groups),
        duplicate_sequence_affected_row_count=120,
        duplicate_sequence_excess_row_count=60,
        duplicate_sequences=groups,
    )

    report = build_layout_import_integrity_report(_reference(), source)
    check = next(
        item
        for item in report.checks
        if item.code is LayoutImportIntegrityCheckCode.DUPLICATE_SEQUENCE_NUMBER
    )

    assert len(check.sequence_numbers) == 60
    assert len(check.line_numbers) == 100
    assert check.truncated is True


def test_service_rejects_unfinished_validation_and_conflicting_filter() -> None:
    reference = replace(_reference(), is_completed=False)
    repository = MemoryLayoutImportReportRepository(
        reference,
        _integrity_source(),
    )
    service = LayoutImportReportService(repository)

    with pytest.raises(
        JobConflictError,
        match="must be completed",
    ):
        service.get_integrity_report(reference.validation_job_id)

    reference = replace(reference, is_completed=True)
    repository.reference = reference
    with pytest.raises(JobConflictError, match="errorCode"):
        service.list_normalized_rows(
            reference.validation_job_id,
            after_line_number=0,
            limit=25,
            row_status=LayoutImportRowStatus.VALID,
            error_code="import_record_invalid",
        )


def test_service_rejects_exact_completed_import_staging() -> None:
    reference = _reference()
    repository = MemoryLayoutImportReportRepository(
        reference,
        _integrity_source(),
        (LayoutImportNormalizedRow(1, 1, (1, 2), "0102", None, None),),
    )
    service = LayoutImportReportService(repository)

    result = service.reject_staging(reference.validation_job_id)

    assert repository.rejections == [(reference.validation_job_id, reference.import_job_id)]
    assert result.deleted_normalized_row_count == 1
    assert result.deleted_raw_row_count == 1


def test_admin_api_exposes_report_and_keyset_filtered_rows() -> None:
    reference = replace(_reference(), expected_row_count=3)
    rows = (
        LayoutImportNormalizedRow(1, 1, (1, 2), "0102", None, None),
        LayoutImportNormalizedRow(
            2,
            2,
            (1, 99),
            None,
            "import_symbol_not_in_rules",
            "Line 2 contains a foreign symbol.",
        ),
        LayoutImportNormalizedRow(
            3,
            None,
            None,
            None,
            "import_record_invalid",
            "Line 3 is invalid.",
        ),
    )
    repository = MemoryLayoutImportReportRepository(
        reference,
        replace(
            _integrity_source(),
            actual_row_count=3,
        ),
        rows,
    )
    service = LayoutImportReportService(repository)
    client = TestClient(
        create_app(
            ApiSettings.from_environment({}),
            layout_import_report_service_dependency=lambda: service,
        )
    )

    with client:
        report = client.get(
            "/api/v1/admin/layout-import-validations/"
            f"{reference.validation_job_id}/integrity-report"
        )
        page = client.get(
            f"/api/v1/admin/layout-import-validations/{reference.validation_job_id}/rows",
            params={"status": "invalid", "limit": 1},
        )
        rejection = client.delete(
            f"/api/v1/admin/layout-import-validations/{reference.validation_job_id}/staging"
        )

    assert report.status_code == 200
    assert report.json()["validationJobId"] == str(reference.validation_job_id)
    assert report.json()["duplicateSignatureGroupCount"] == 2
    assert page.status_code == 200
    assert page.json()["items"][0]["lineNumber"] == 2
    assert page.json()["nextAfterLineNumber"] == 2
    assert rejection.status_code == 200
    assert rejection.json() == {
        "deletedNormalizedRowCount": 3,
        "deletedRawRowCount": 3,
        "importJobId": str(reference.import_job_id),
        "validationJobId": str(reference.validation_job_id),
    }


def test_admin_api_publishes_ready_layout_import_dataset() -> None:
    reference = replace(_reference(), expected_row_count=4)
    repository = MemoryLayoutImportReportRepository(
        reference,
        _clean_integrity_source(),
    )
    client = TestClient(
        create_app(
            ApiSettings.from_environment({}),
            layout_import_report_service_dependency=lambda: (LayoutImportReportService(repository)),
        )
    )

    with client:
        response = client.post(
            f"/api/v1/admin/layout-import-validations/{reference.validation_job_id}/publish"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["sourceJobId"] == str(reference.validation_job_id)
    assert response.json()["generatorVersion"] == "layout-import-v1"
