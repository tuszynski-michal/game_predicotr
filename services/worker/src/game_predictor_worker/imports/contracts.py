"""Framework-independent manual import contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

LAYOUT_IMPORT_SCHEMA_VERSION = 1
CSV_V1_HEADERS = ("schema_version", "sequence_number", "cells")
MAX_SEQUENCE_NUMBER = 9_223_372_036_854_775_807
MAX_SYMBOL_CODE = 32_767


class ImportFileFormat(StrEnum):
    CSV = "csv"
    JSONL = "jsonl"


@dataclass(frozen=True)
class LayoutImportRecord:
    schema_version: int
    sequence_number: int
    cells: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StagedLayoutImportRow:
    line_number: int
    byte_offset_end: int
    sequence_number: int | None
    cells: tuple[int, ...] | None
    error_code: str | None
    error_message: str | None

    def __post_init__(self) -> None:
        success = (
            self.sequence_number is not None
            and self.cells is not None
            and self.error_code is None
            and self.error_message is None
        )
        failure = (
            self.sequence_number is None
            and self.cells is None
            and isinstance(self.error_code, str)
            and bool(self.error_code.strip())
            and isinstance(self.error_message, str)
            and bool(self.error_message.strip())
        )
        if self.line_number < 1 or self.byte_offset_end < 1:
            raise ValueError("Staged import row positions must be positive.")
        if not (success or failure):
            raise ValueError("A staged import row must contain one result variant.")

    @property
    def is_success(self) -> bool:
        return self.error_code is None


@dataclass(frozen=True, slots=True)
class LayoutImportStreamBatch:
    rows: tuple[StagedLayoutImportRow, ...]
    byte_offset: int
    line_number: int
    prefix_chain: str
    reached_eof: bool


class LayoutImportStagingStore(Protocol):
    def upsert_rows(
        self,
        job_id: UUID,
        rows: tuple[StagedLayoutImportRow, ...],
    ) -> None: ...

    def delete_rows_after(
        self,
        job_id: UUID,
        *,
        line_number: int,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RawLayoutImportRow:
    line_number: int
    sequence_number: int | None
    cells: tuple[int, ...] | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class LayoutImportNormalizationSource:
    import_job_id: UUID
    rules_version_id: UUID
    rows: int
    columns: int
    signature_cell_width: int
    allowed_mobile_codes: frozenset[int]
    row_count: int


@dataclass(frozen=True, slots=True)
class NormalizedLayoutImportRow:
    line_number: int
    sequence_number: int | None
    cells: tuple[int, ...] | None
    signature: str | None
    error_code: str | None
    error_message: str | None

    @property
    def is_success(self) -> bool:
        return self.error_code is None


class LayoutImportNormalizationStore(Protocol):
    def load_normalization_source(
        self,
        *,
        validation_job_id: UUID,
        game_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> LayoutImportNormalizationSource: ...

    def fetch_raw_rows(
        self,
        import_job_id: UUID,
        *,
        after_line_number: int,
        limit: int,
    ) -> tuple[RawLayoutImportRow, ...]: ...

    def upsert_normalized_rows(
        self,
        validation_job_id: UUID,
        source: LayoutImportNormalizationSource,
        rows: tuple[NormalizedLayoutImportRow, ...],
    ) -> None: ...
