"""Framework-independent dataset staging and deterministic mock generation."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.rules import RulesVersionStatus

MOCK_LAYOUT_COUNT = 1_000
MOCK_DUPLICATE_COUNT = 6
MOCK_GENERATOR_VERSION = "mock-v1"
MAX_GENERATOR_SEED = 2_147_483_647
MAX_SIGNATURE_CELL_WIDTH = 5
MAX_MOCK_CELL_COUNT = 100
_DUPLICATE_SOURCE_SEQUENCES = (101, 102, 103, 104, 105, 106)


class DatasetVersionStatus(StrEnum):
    STAGING = "staging"
    PUBLISHED = "published"
    ARCHIVED = "archived"


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
    """Current state cannot be used for deterministic generation."""


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    signature_cell_width: int
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
        if not 1 <= mobile_code <= 32767:
            raise DatasetError(
                "INVALID_SYMBOL_CODE",
                "Every cell must contain a valid positive symbol mobile code.",
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
        unique_cells[sequence_number - 1]
        for sequence_number in _DUPLICATE_SOURCE_SEQUENCES
    ]
    return tuple(
        LayoutDraft(
            sequence_number=sequence_number,
            signature=encode_layout_signature(cells, cell_width),
            cells=cells,
        )
        for sequence_number, cells in enumerate(all_cells, start=1)
    )
