"""Framework-independent contracts for layout import integrity reporting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.datasets import DatasetVersion

IMPORT_REPORT_SAMPLE_LIMIT = 100
LAYOUT_IMPORT_GENERATOR_VERSION = "layout-import-v1"


class LayoutImportIntegrityCheckStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    BLOCKING = "blocking"


class LayoutImportIntegrityCheckCode(StrEnum):
    NORMALIZED_ROW_COUNT_MISMATCH = "NORMALIZED_ROW_COUNT_MISMATCH"
    NO_VALID_IMPORT_ROWS = "NO_VALID_IMPORT_ROWS"
    INVALID_IMPORT_ROW = "INVALID_IMPORT_ROW"
    MISSING_SEQUENCE_NUMBER = "MISSING_SEQUENCE_NUMBER"
    DUPLICATE_SEQUENCE_NUMBER = "DUPLICATE_SEQUENCE_NUMBER"
    DUPLICATE_SIGNATURE = "DUPLICATE_SIGNATURE"


class LayoutImportRowStatus(StrEnum):
    ALL = "all"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class LayoutImportValidationReference:
    validation_job_id: UUID
    import_job_id: UUID | None
    rules_version_id: UUID | None
    is_layout_import_validation: bool
    is_completed: bool
    expected_row_count: int | None
    rows: int | None
    columns: int | None


@dataclass(frozen=True, slots=True)
class LayoutImportDuplicateSequenceGroup:
    sequence_number: int
    occurrence_count: int
    line_numbers: tuple[int, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class LayoutImportDuplicateSignatureGroup:
    signature: str
    occurrence_count: int
    sequence_numbers: tuple[int, ...]
    line_numbers: tuple[int, ...]
    sequence_numbers_truncated: bool
    line_numbers_truncated: bool


@dataclass(frozen=True, slots=True)
class LayoutImportErrorCodeCount:
    code: str
    count: int


@dataclass(frozen=True, slots=True)
class LayoutImportIntegritySource:
    actual_row_count: int
    valid_row_count: int
    invalid_row_count: int
    min_sequence_number: int | None
    max_sequence_number: int | None
    unique_sequence_count: int
    missing_sequence_count: int
    missing_sequence_numbers: tuple[int, ...]
    duplicate_sequence_group_count: int
    duplicate_sequence_affected_row_count: int
    duplicate_sequence_excess_row_count: int
    duplicate_sequences: tuple[LayoutImportDuplicateSequenceGroup, ...]
    duplicate_signature_group_count: int
    duplicate_signature_affected_row_count: int
    duplicate_signature_excess_row_count: int
    duplicate_signatures: tuple[LayoutImportDuplicateSignatureGroup, ...]
    error_code_counts: tuple[LayoutImportErrorCodeCount, ...]


@dataclass(frozen=True, slots=True)
class LayoutImportIntegrityCheck:
    code: LayoutImportIntegrityCheckCode
    status: LayoutImportIntegrityCheckStatus
    issue_count: int
    message: str
    sequence_numbers: tuple[int, ...] = ()
    line_numbers: tuple[int, ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class LayoutImportIntegrityReport:
    validation_job_id: UUID
    import_job_id: UUID
    rules_version_id: UUID
    rows: int
    columns: int
    ready_for_publication: bool
    expected_row_count: int | None
    actual_row_count: int
    valid_row_count: int
    invalid_row_count: int
    min_sequence_number: int | None
    max_sequence_number: int | None
    unique_sequence_count: int
    checks: tuple[LayoutImportIntegrityCheck, ...]
    missing_sequence_count: int
    missing_sequence_numbers: tuple[int, ...]
    missing_sequence_numbers_truncated: bool
    duplicate_sequence_group_count: int
    duplicate_sequence_affected_row_count: int
    duplicate_sequence_excess_row_count: int
    duplicate_sequences: tuple[LayoutImportDuplicateSequenceGroup, ...]
    duplicate_sequences_truncated: bool
    duplicate_signature_group_count: int
    duplicate_signature_affected_row_count: int
    duplicate_signature_excess_row_count: int
    duplicate_signatures: tuple[LayoutImportDuplicateSignatureGroup, ...]
    duplicate_signatures_truncated: bool
    error_code_counts: tuple[LayoutImportErrorCodeCount, ...]


@dataclass(frozen=True, slots=True)
class LayoutImportNormalizedRow:
    line_number: int
    sequence_number: int | None
    cells: tuple[int, ...] | None
    signature: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class LayoutImportNormalizedRowPage:
    validation_job_id: UUID
    import_job_id: UUID
    rules_version_id: UUID
    rows: int
    columns: int
    items: tuple[LayoutImportNormalizedRow, ...]
    next_after_line_number: int | None


@dataclass(frozen=True, slots=True)
class LayoutImportStagingRejection:
    validation_job_id: UUID
    import_job_id: UUID
    deleted_normalized_row_count: int
    deleted_raw_row_count: int


@dataclass(frozen=True, slots=True)
class LayoutImportPublicationSource:
    reference: LayoutImportValidationReference
    integrity_source: LayoutImportIntegritySource
    game_id: UUID
    signature_cell_width: int
    expected_layout_count: int
    rules_are_published: bool
    existing_dataset: DatasetVersion | None


def build_layout_import_integrity_report(
    reference: LayoutImportValidationReference,
    source: LayoutImportIntegritySource,
) -> LayoutImportIntegrityReport:
    """Build the stable readiness decision from exact aggregates and bounded samples."""

    if (
        reference.import_job_id is None
        or reference.rules_version_id is None
        or reference.rows is None
        or reference.columns is None
    ):
        raise ValueError("A valid layout import validation reference is required.")

    expected_mismatch_count = (
        1
        if reference.expected_row_count is None
        else abs(reference.expected_row_count - source.actual_row_count)
    )
    no_valid_count = int(source.valid_row_count == 0)
    duplicate_sequence_numbers = tuple(
        group.sequence_number for group in source.duplicate_sequences
    )
    duplicate_sequence_all_lines = tuple(
        line_number for group in source.duplicate_sequences for line_number in group.line_numbers
    )
    duplicate_sequence_lines = duplicate_sequence_all_lines[:IMPORT_REPORT_SAMPLE_LIMIT]
    checks = (
        _check(
            LayoutImportIntegrityCheckCode.NORMALIZED_ROW_COUNT_MISMATCH,
            expected_mismatch_count,
            passed_message="The normalized row count matches the completed job.",
            issue_message="The normalized row count does not match the completed job.",
        ),
        _check(
            LayoutImportIntegrityCheckCode.NO_VALID_IMPORT_ROWS,
            no_valid_count,
            passed_message="The import contains at least one valid layout.",
            issue_message="The import does not contain any valid layouts.",
        ),
        _check(
            LayoutImportIntegrityCheckCode.INVALID_IMPORT_ROW,
            source.invalid_row_count,
            passed_message="Every normalized row is valid.",
            issue_message="Some normalized rows contain parser or domain errors.",
        ),
        _check(
            LayoutImportIntegrityCheckCode.MISSING_SEQUENCE_NUMBER,
            source.missing_sequence_count,
            passed_message="No sequence numbers are missing.",
            issue_message="The valid layouts have missing sequence numbers.",
            sequence_numbers=source.missing_sequence_numbers,
            truncated=(source.missing_sequence_count > len(source.missing_sequence_numbers)),
        ),
        _check(
            LayoutImportIntegrityCheckCode.DUPLICATE_SEQUENCE_NUMBER,
            source.duplicate_sequence_group_count,
            passed_message="Every valid sequence number occurs once.",
            issue_message="Some valid sequence numbers occur more than once.",
            sequence_numbers=duplicate_sequence_numbers,
            line_numbers=duplicate_sequence_lines,
            truncated=(
                source.duplicate_sequence_group_count > len(source.duplicate_sequences)
                or any(group.truncated for group in source.duplicate_sequences)
                or len(duplicate_sequence_all_lines) > IMPORT_REPORT_SAMPLE_LIMIT
            ),
        ),
        _check(
            LayoutImportIntegrityCheckCode.DUPLICATE_SIGNATURE,
            source.duplicate_signature_group_count,
            passed_message="No duplicate layout signatures were found.",
            issue_message="Duplicate layout signatures are allowed and were found.",
            warning=True,
            truncated=(
                source.duplicate_signature_group_count > len(source.duplicate_signatures)
                or any(
                    group.sequence_numbers_truncated or group.line_numbers_truncated
                    for group in source.duplicate_signatures
                )
            ),
        ),
    )
    return LayoutImportIntegrityReport(
        validation_job_id=reference.validation_job_id,
        import_job_id=reference.import_job_id,
        rules_version_id=reference.rules_version_id,
        rows=reference.rows,
        columns=reference.columns,
        ready_for_publication=not any(
            check.status is LayoutImportIntegrityCheckStatus.BLOCKING for check in checks
        ),
        expected_row_count=reference.expected_row_count,
        actual_row_count=source.actual_row_count,
        valid_row_count=source.valid_row_count,
        invalid_row_count=source.invalid_row_count,
        min_sequence_number=source.min_sequence_number,
        max_sequence_number=source.max_sequence_number,
        unique_sequence_count=source.unique_sequence_count,
        checks=checks,
        missing_sequence_count=source.missing_sequence_count,
        missing_sequence_numbers=source.missing_sequence_numbers,
        missing_sequence_numbers_truncated=(
            source.missing_sequence_count > len(source.missing_sequence_numbers)
        ),
        duplicate_sequence_group_count=source.duplicate_sequence_group_count,
        duplicate_sequence_affected_row_count=(source.duplicate_sequence_affected_row_count),
        duplicate_sequence_excess_row_count=(source.duplicate_sequence_excess_row_count),
        duplicate_sequences=source.duplicate_sequences,
        duplicate_sequences_truncated=(
            source.duplicate_sequence_group_count > len(source.duplicate_sequences)
        ),
        duplicate_signature_group_count=source.duplicate_signature_group_count,
        duplicate_signature_affected_row_count=(source.duplicate_signature_affected_row_count),
        duplicate_signature_excess_row_count=(source.duplicate_signature_excess_row_count),
        duplicate_signatures=source.duplicate_signatures,
        duplicate_signatures_truncated=(
            source.duplicate_signature_group_count > len(source.duplicate_signatures)
        ),
        error_code_counts=source.error_code_counts,
    )


def _check(
    code: LayoutImportIntegrityCheckCode,
    issue_count: int,
    *,
    passed_message: str,
    issue_message: str,
    sequence_numbers: tuple[int, ...] = (),
    line_numbers: tuple[int, ...] = (),
    warning: bool = False,
    truncated: bool = False,
) -> LayoutImportIntegrityCheck:
    status = LayoutImportIntegrityCheckStatus.PASSED
    if issue_count:
        status = (
            LayoutImportIntegrityCheckStatus.WARNING
            if warning
            else LayoutImportIntegrityCheckStatus.BLOCKING
        )
    return LayoutImportIntegrityCheck(
        code=code,
        status=status,
        issue_count=issue_count,
        message=issue_message if issue_count else passed_message,
        sequence_numbers=sequence_numbers,
        line_numbers=line_numbers,
        truncated=truncated,
    )
