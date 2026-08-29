"""Framework-independent dataset staging and deterministic mock generation."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.rules import RulesVersionStatus

MOCK_LAYOUT_COUNT = 1_000
MOCK_DUPLICATE_COUNT = 6
MOCK_GENERATOR_VERSION = "mock-v1"
MAX_GENERATOR_SEED = 2_147_483_647
MAX_SIGNATURE_CELL_WIDTH = 5
UNKNOWN_LAYOUT_MOBILE_CODE = 0
MAX_MOCK_CELL_COUNT = 100
VALIDATION_DIAGNOSTIC_LIMIT = 100
_DUPLICATE_SOURCE_SEQUENCES = (101, 102, 103, 104, 105, 106)


class DatasetVersionStatus(StrEnum):
    STAGING = "staging"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DatasetValidationCheckStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    BLOCKING = "blocking"


class DatasetValidationCheckCode(StrEnum):
    LAYOUT_COUNT_MISMATCH = "LAYOUT_COUNT_MISMATCH"
    MISSING_SEQUENCE_NUMBER = "MISSING_SEQUENCE_NUMBER"
    OUT_OF_RANGE_SEQUENCE_NUMBER = "OUT_OF_RANGE_SEQUENCE_NUMBER"
    DUPLICATE_SEQUENCE_NUMBER = "DUPLICATE_SEQUENCE_NUMBER"
    INVALID_CELL_COUNT = "INVALID_CELL_COUNT"
    FOREIGN_SYMBOL = "FOREIGN_SYMBOL"
    SIGNATURE_MISMATCH = "SIGNATURE_MISMATCH"
    DUPLICATE_SIGNATURE = "DUPLICATE_SIGNATURE"


class DatasetError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class DatasetNotFoundError(DatasetError):
    """Requested game, rules version, or dataset does not exist."""


class DatasetConflictError(DatasetError):
    """Current state cannot be used for the requested dataset operation."""


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    signature_cell_width: int
    expected_layout_count: int
    layout_count: int
    status: DatasetVersionStatus
    generation_seed: int
    generator_version: str
    source_job_id: UUID | None
    created_at: datetime
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class LayoutDraft:
    sequence_number: int
    signature: str
    cells: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DatasetGenerationSource:
    rules_version_id: UUID
    game_id: UUID
    rows: int
    columns: int
    rules_status: RulesVersionStatus
    symbol_mobile_codes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LayoutValidationRecord:
    sequence_number: int
    signature: str
    cells: tuple[int, ...]
    source_board_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DatasetLayoutPage:
    dataset_version_id: UUID
    dataset_version: int
    rows: int
    columns: int
    items: tuple[LayoutValidationRecord, ...]
    next_after_sequence_number: int | None


@dataclass(frozen=True, slots=True)
class DatasetValidationSource:
    dataset_version: DatasetVersion
    allowed_symbol_mobile_codes: tuple[int, ...]
    layouts: tuple[LayoutValidationRecord, ...]


@dataclass(frozen=True, slots=True)
class DatasetValidationCheck:
    code: DatasetValidationCheckCode
    status: DatasetValidationCheckStatus
    issue_count: int
    message: str
    sequence_numbers: tuple[int, ...] = ()
    mobile_codes: tuple[int, ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class DuplicateSignatureGroup:
    signature: str
    occurrence_count: int
    sequence_numbers: tuple[int, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class DatasetValidationReport:
    dataset_version_id: UUID
    dataset_version: int
    ready_for_publication: bool
    declared_layout_count: int
    actual_layout_count: int
    min_sequence_number: int | None
    max_sequence_number: int | None
    checks: tuple[DatasetValidationCheck, ...]
    duplicate_signature_group_count: int
    duplicate_signature_affected_layout_count: int
    duplicate_signature_excess_layout_count: int
    duplicate_signatures: tuple[DuplicateSignatureGroup, ...]
    duplicate_signatures_truncated: bool


def publish_dataset_version(
    dataset: DatasetVersion,
    *,
    published_at: datetime | None = None,
) -> DatasetVersion:
    if dataset.status is not DatasetVersionStatus.STAGING:
        raise DatasetConflictError(
            "DATASET_VERSION_NOT_STAGING",
            "Only a staging dataset version can be published.",
            details={"datasetVersionId": str(dataset.id)},
        )
    return replace(
        dataset,
        status=DatasetVersionStatus.PUBLISHED,
        published_at=published_at or datetime.now(UTC),
    )


def archive_dataset_version(dataset: DatasetVersion) -> DatasetVersion:
    if dataset.status is DatasetVersionStatus.ARCHIVED:
        return dataset
    if dataset.status is not DatasetVersionStatus.PUBLISHED:
        raise DatasetConflictError(
            "DATASET_VERSION_NOT_PUBLISHED",
            "Only a published dataset version can be archived.",
            details={"datasetVersionId": str(dataset.id)},
        )
    return replace(dataset, status=DatasetVersionStatus.ARCHIVED)


def validate_generation_seed(seed: int) -> int:
    if isinstance(seed, bool) or not 0 <= seed <= MAX_GENERATOR_SEED:
        raise DatasetError(
            "INVALID_GENERATION_SEED",
            "seed must be between 0 and 2147483647.",
            details={"field": "seed"},
        )
    return seed


def signature_cell_width(symbol_mobile_codes: Sequence[int]) -> int:
    if not symbol_mobile_codes:
        raise DatasetConflictError(
            "NO_ACTIVE_RULE_SYMBOLS",
            "The published rules version has no active symbols.",
        )
    maximum = max(symbol_mobile_codes)
    width = len(str(maximum))
    if width > MAX_SIGNATURE_CELL_WIDTH:
        raise DatasetConflictError(
            "SYMBOL_CODE_OUT_OF_RANGE",
            "An active symbol does not fit the supported signature codec.",
            details={"mobileCode": maximum},
        )
    return width


def encode_layout_signature(cells: Sequence[int], cell_width: int) -> str:
    if not 1 <= cell_width <= MAX_SIGNATURE_CELL_WIDTH:
        raise DatasetError(
            "INVALID_SIGNATURE_CELL_WIDTH",
            "signatureCellWidth must be between 1 and 5.",
        )
    encoded: list[str] = []
    for mobile_code in cells:
        if not UNKNOWN_LAYOUT_MOBILE_CODE <= mobile_code <= 32767:
            raise DatasetError(
                "INVALID_SYMBOL_CODE",
                "Every cell must contain a symbol mobile code or zero for unknown.",
            )
        value = str(mobile_code)
        if len(value) > cell_width:
            raise DatasetError(
                "SYMBOL_CODE_OUT_OF_RANGE",
                "A symbol mobile code does not fit signatureCellWidth.",
                details={"mobileCode": mobile_code},
            )
        encoded.append(value.zfill(cell_width))
    return "".join(encoded)


def generate_mock_layouts(
    source: DatasetGenerationSource,
    *,
    seed: int,
) -> tuple[LayoutDraft, ...]:
    """Generate the bounded M2 mock with deterministic controlled duplicates."""

    if source.rules_status is not RulesVersionStatus.PUBLISHED:
        raise DatasetConflictError(
            "RULES_VERSION_NOT_PUBLISHED",
            "Mock data can only be generated from a published rules version.",
            details={"rulesVersionId": str(source.rules_version_id)},
        )
    symbols = tuple(sorted(set(source.symbol_mobile_codes)))
    if len(symbols) < 2:
        raise DatasetConflictError(
            "INSUFFICIENT_ACTIVE_SYMBOLS",
            "At least two active rules symbols are required for mock generation.",
            details={"activeSymbolCount": len(symbols)},
        )
    cell_count = source.rows * source.columns
    if not 1 <= cell_count <= MAX_MOCK_CELL_COUNT:
        raise DatasetConflictError(
            "INVALID_DATASET_DIMENSIONS",
            "Mock dataset dimensions must contain between 1 and 100 cells.",
            details={"cellCount": cell_count},
        )
    unique_count = MOCK_LAYOUT_COUNT - MOCK_DUPLICATE_COUNT
    possible_unique = 1
    for _ in range(cell_count):
        possible_unique *= len(symbols)
        if possible_unique >= unique_count:
            break
    if possible_unique < unique_count:
        raise DatasetConflictError(
            "INSUFFICIENT_LAYOUT_VARIANTS",
            "The configured board and symbols cannot produce enough unique layouts.",
        )

    validated_seed = validate_generation_seed(seed)
    cell_width = signature_cell_width(symbols)
    random_source = random.Random(validated_seed)
    used_cells: set[tuple[int, ...]] = set()
    unique_cells: list[tuple[int, ...]] = []
    while len(unique_cells) < unique_count:
        cells = tuple(random_source.choice(symbols) for _ in range(cell_count))
        if cells in used_cells:
            continue
        used_cells.add(cells)
        unique_cells.append(cells)

    all_cells = unique_cells + [
        unique_cells[sequence_number - 1] for sequence_number in _DUPLICATE_SOURCE_SEQUENCES
    ]
    return tuple(
        LayoutDraft(
            sequence_number=sequence_number,
            signature=encode_layout_signature(cells, cell_width),
            cells=cells,
        )
        for sequence_number, cells in enumerate(all_cells, start=1)
    )


def validate_dataset(
    source: DatasetValidationSource,
) -> DatasetValidationReport:
    """Return every deterministic blocker and duplicate-signature warning."""

    dataset = source.dataset_version
    layouts = source.layouts
    sequence_numbers = tuple(item.sequence_number for item in layouts)
    sequence_counts = Counter(sequence_numbers)
    expected_numbers = set(range(1, dataset.expected_layout_count + 1))
    actual_numbers = set(sequence_counts)

    missing_numbers = expected_numbers - actual_numbers
    out_of_range_numbers = actual_numbers - expected_numbers
    duplicate_numbers = {number for number, count in sequence_counts.items() if count > 1}
    invalid_cell_records = [
        item for item in layouts if len(item.cells) != dataset.rows * dataset.columns
    ]
    allowed_codes = {UNKNOWN_LAYOUT_MOBILE_CODE, *source.allowed_symbol_mobile_codes}
    foreign_records = [
        item for item in layouts if any(cell not in allowed_codes for cell in item.cells)
    ]
    foreign_codes = {
        cell for item in foreign_records for cell in item.cells if cell not in allowed_codes
    }
    signature_mismatches: list[LayoutValidationRecord] = []
    for item in layouts:
        try:
            expected_signature = encode_layout_signature(
                item.cells,
                dataset.signature_cell_width,
            )
        except DatasetError:
            signature_mismatches.append(item)
            continue
        if expected_signature != item.signature:
            signature_mismatches.append(item)

    signatures: defaultdict[str, list[int]] = defaultdict(list)
    for item in layouts:
        signatures[item.signature].append(item.sequence_number)
    duplicate_groups_all = [
        (signature, tuple(sorted(numbers)))
        for signature, numbers in signatures.items()
        if len(numbers) > 1
    ]
    duplicate_groups_all.sort(key=lambda group: group[0])
    duplicate_groups = tuple(
        DuplicateSignatureGroup(
            signature=signature,
            occurrence_count=len(numbers),
            sequence_numbers=numbers[:VALIDATION_DIAGNOSTIC_LIMIT],
            truncated=len(numbers) > VALIDATION_DIAGNOSTIC_LIMIT,
        )
        for signature, numbers in duplicate_groups_all[:VALIDATION_DIAGNOSTIC_LIMIT]
    )

    count_difference = abs(dataset.expected_layout_count - len(layouts))
    checks = (
        _validation_check(
            DatasetValidationCheckCode.LAYOUT_COUNT_MISMATCH,
            issue_count=count_difference,
            message=(
                "Declared and actual layout counts match."
                if count_difference == 0
                else "Declared and actual layout counts differ."
            ),
        ),
        _validation_check(
            DatasetValidationCheckCode.MISSING_SEQUENCE_NUMBER,
            issue_count=len(missing_numbers),
            message=(
                "No sequence numbers are missing."
                if not missing_numbers
                else "The dataset has missing sequence numbers."
            ),
            sequence_numbers=missing_numbers,
        ),
        _validation_check(
            DatasetValidationCheckCode.OUT_OF_RANGE_SEQUENCE_NUMBER,
            issue_count=len(out_of_range_numbers),
            message=(
                "Every sequence number is inside the declared range."
                if not out_of_range_numbers
                else "The dataset has sequence numbers outside the declared range."
            ),
            sequence_numbers=out_of_range_numbers,
        ),
        _validation_check(
            DatasetValidationCheckCode.DUPLICATE_SEQUENCE_NUMBER,
            issue_count=len(duplicate_numbers),
            message=(
                "Every sequence number occurs once."
                if not duplicate_numbers
                else "The dataset has duplicate sequence numbers."
            ),
            sequence_numbers=duplicate_numbers,
        ),
        _validation_check(
            DatasetValidationCheckCode.INVALID_CELL_COUNT,
            issue_count=len(invalid_cell_records),
            message=(
                "Every layout has the expected number of cells."
                if not invalid_cell_records
                else "Some layouts have an invalid number of cells."
            ),
            sequence_numbers=(item.sequence_number for item in invalid_cell_records),
        ),
        _validation_check(
            DatasetValidationCheckCode.FOREIGN_SYMBOL,
            issue_count=len(foreign_records),
            message=(
                "Every layout cell belongs to the dataset game."
                if not foreign_records
                else "Some layouts contain symbols outside the dataset game."
            ),
            sequence_numbers=(item.sequence_number for item in foreign_records),
            mobile_codes=foreign_codes,
        ),
        _validation_check(
            DatasetValidationCheckCode.SIGNATURE_MISMATCH,
            issue_count=len(signature_mismatches),
            message=(
                "Every signature matches its cells and codec width."
                if not signature_mismatches
                else "Some signatures do not match their cells and codec width."
            ),
            sequence_numbers=(item.sequence_number for item in signature_mismatches),
        ),
        _validation_check(
            DatasetValidationCheckCode.DUPLICATE_SIGNATURE,
            issue_count=len(duplicate_groups_all),
            message=(
                "No duplicate layout signatures were found."
                if not duplicate_groups_all
                else "Duplicate layout signatures are allowed and were found."
            ),
            warning=bool(duplicate_groups_all),
        ),
    )
    return DatasetValidationReport(
        dataset_version_id=dataset.id,
        dataset_version=dataset.version,
        ready_for_publication=not any(
            check.status is DatasetValidationCheckStatus.BLOCKING for check in checks
        ),
        declared_layout_count=dataset.layout_count,
        actual_layout_count=len(layouts),
        min_sequence_number=min(sequence_numbers, default=None),
        max_sequence_number=max(sequence_numbers, default=None),
        checks=checks,
        duplicate_signature_group_count=len(duplicate_groups_all),
        duplicate_signature_affected_layout_count=sum(
            len(numbers) for _, numbers in duplicate_groups_all
        ),
        duplicate_signature_excess_layout_count=sum(
            len(numbers) - 1 for _, numbers in duplicate_groups_all
        ),
        duplicate_signatures=duplicate_groups,
        duplicate_signatures_truncated=(len(duplicate_groups_all) > VALIDATION_DIAGNOSTIC_LIMIT),
    )


def _validation_check(
    code: DatasetValidationCheckCode,
    *,
    issue_count: int,
    message: str,
    sequence_numbers: Iterable[int] = (),
    mobile_codes: Iterable[int] = (),
    warning: bool = False,
) -> DatasetValidationCheck:
    sampled_sequences, sequences_truncated = _diagnostic_sample(sequence_numbers)
    sampled_codes, codes_truncated = _diagnostic_sample(mobile_codes)
    return DatasetValidationCheck(
        code=code,
        status=(
            DatasetValidationCheckStatus.WARNING
            if warning
            else (
                DatasetValidationCheckStatus.BLOCKING
                if issue_count > 0
                else DatasetValidationCheckStatus.PASSED
            )
        ),
        issue_count=issue_count,
        message=message,
        sequence_numbers=sampled_sequences,
        mobile_codes=sampled_codes,
        truncated=sequences_truncated or codes_truncated,
    )


def _diagnostic_sample(values: Iterable[int]) -> tuple[tuple[int, ...], bool]:
    ordered = tuple(sorted(set(values)))
    return (
        ordered[:VALIDATION_DIAGNOSTIC_LIMIT],
        len(ordered) > VALIDATION_DIAGNOSTIC_LIMIT,
    )
