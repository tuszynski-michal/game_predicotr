"""Pure validation of layout-import-v1 headers and individual records."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from typing import Any

from game_predictor_worker.imports.contracts import (
    CSV_V1_HEADERS,
    LAYOUT_IMPORT_SCHEMA_VERSION,
    MAX_SEQUENCE_NUMBER,
    MAX_SYMBOL_CODE,
    ImportFileFormat,
    LayoutImportRecord,
)
from game_predictor_worker.imports.errors import ImportContractError, ImportErrorCode

_UTF8_BOM = b"\xef\xbb\xbf"
_JSONL_V1_FIELDS = frozenset(("schemaVersion", "sequenceNumber", "cells"))


def decode_import_line(raw_line: bytes, *, line_number: int) -> str:
    """Decode exactly one physical line using the v1 encoding contract."""

    _validate_line_number(line_number)
    if raw_line.startswith(_UTF8_BOM):
        raise ImportContractError(
            ImportErrorCode.ENCODING_BOM_FORBIDDEN,
            f"Line {line_number} starts with a forbidden UTF-8 BOM.",
            line_number=line_number,
        )
    try:
        return raw_line.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ImportContractError(
            ImportErrorCode.ENCODING_INVALID,
            f"Line {line_number} is not valid UTF-8.",
            line_number=line_number,
        ) from error


def validate_csv_header(raw_line: bytes | str, *, line_number: int = 1) -> None:
    """Require the exact ordered v1 CSV header."""

    text = _coerce_text(raw_line, line_number=line_number)
    fields = _read_csv_fields(
        text,
        line_number=line_number,
        error_code=ImportErrorCode.HEADER_INVALID,
    )
    if tuple(fields) != CSV_V1_HEADERS:
        raise ImportContractError(
            ImportErrorCode.HEADER_INVALID,
            (f"Line {line_number} must contain the exact CSV header {','.join(CSV_V1_HEADERS)}."),
            line_number=line_number,
        )


def parse_csv_record(raw_line: bytes | str, *, line_number: int) -> LayoutImportRecord:
    """Parse one data row without applying game-specific validation."""

    text = _coerce_text(raw_line, line_number=line_number)
    fields = _read_csv_fields(
        text,
        line_number=line_number,
        error_code=ImportErrorCode.RECORD_INVALID,
    )
    if len(fields) != len(CSV_V1_HEADERS):
        raise ImportContractError(
            ImportErrorCode.RECORD_INVALID,
            f"Line {line_number} must contain exactly three CSV fields.",
            line_number=line_number,
        )

    schema_version = _parse_csv_schema_version(fields[0], line_number=line_number)
    sequence_number = _parse_csv_sequence_number(fields[1], line_number=line_number)
    try:
        cells_value = json.loads(fields[2])
    except json.JSONDecodeError as error:
        raise ImportContractError(
            ImportErrorCode.CELLS_INVALID,
            f"Line {line_number} contains an invalid JSON array in cells.",
            line_number=line_number,
        ) from error
    cells = _validate_cells(cells_value, line_number=line_number)
    return LayoutImportRecord(
        schema_version=schema_version,
        sequence_number=sequence_number,
        cells=cells,
    )


def parse_jsonl_record(raw_line: bytes | str, *, line_number: int) -> LayoutImportRecord:
    """Parse one strict JSON Lines record without game-specific validation."""

    text = _coerce_text(raw_line, line_number=line_number)
    if not text or text.isspace():
        raise ImportContractError(
            ImportErrorCode.RECORD_INVALID,
            f"Line {line_number} does not contain a JSON object.",
            line_number=line_number,
        )
    try:
        value = json.loads(text, object_pairs_hook=_object_from_unique_pairs)
    except _DuplicateJsonFieldError as error:
        raise ImportContractError(
            ImportErrorCode.RECORD_INVALID,
            f"Line {line_number} contains duplicate JSON fields.",
            line_number=line_number,
        ) from error
    except json.JSONDecodeError as error:
        raise ImportContractError(
            ImportErrorCode.RECORD_INVALID,
            f"Line {line_number} is not a valid JSON object.",
            line_number=line_number,
        ) from error

    if not isinstance(value, dict) or set(value) != _JSONL_V1_FIELDS:
        raise ImportContractError(
            ImportErrorCode.RECORD_INVALID,
            (f"Line {line_number} must contain exactly schemaVersion, sequenceNumber and cells."),
            line_number=line_number,
        )

    schema_version = _validate_schema_version(value["schemaVersion"], line_number=line_number)
    sequence_number = _validate_sequence_number(
        value["sequenceNumber"],
        line_number=line_number,
    )
    cells = _validate_cells(value["cells"], line_number=line_number)
    return LayoutImportRecord(
        schema_version=schema_version,
        sequence_number=sequence_number,
        cells=cells,
    )


def parse_import_record(
    file_format: ImportFileFormat | str,
    raw_line: bytes | str,
    *,
    line_number: int,
) -> LayoutImportRecord:
    """Dispatch a single record through the selected public format contract."""

    try:
        normalized_format = ImportFileFormat(file_format)
    except ValueError as error:
        raise ImportContractError(
            ImportErrorCode.FORMAT_UNSUPPORTED,
            f"Unsupported import format: {file_format!s}.",
            line_number=line_number,
        ) from error

    if normalized_format is ImportFileFormat.CSV:
        return parse_csv_record(raw_line, line_number=line_number)
    return parse_jsonl_record(raw_line, line_number=line_number)


def _coerce_text(raw_line: bytes | str, *, line_number: int) -> str:
    _validate_line_number(line_number)
    if isinstance(raw_line, bytes):
        text = decode_import_line(raw_line, line_number=line_number)
    else:
        text = raw_line
        if text.startswith("\ufeff"):
            raise ImportContractError(
                ImportErrorCode.ENCODING_BOM_FORBIDDEN,
                f"Line {line_number} starts with a forbidden UTF-8 BOM.",
                line_number=line_number,
            )
    return text.rstrip("\r\n")


def _read_csv_fields(
    text: str,
    *,
    line_number: int,
    error_code: ImportErrorCode,
) -> list[str]:
    if not text or text.isspace():
        raise ImportContractError(
            error_code,
            f"Line {line_number} is empty.",
            line_number=line_number,
        )
    try:
        rows = list(csv.reader((text,), strict=True))
    except csv.Error as error:
        raise ImportContractError(
            error_code,
            f"Line {line_number} is not valid CSV.",
            line_number=line_number,
        ) from error
    if len(rows) != 1:
        raise ImportContractError(
            error_code,
            f"Line {line_number} must contain exactly one CSV record.",
            line_number=line_number,
        )
    return rows[0]


def _parse_csv_schema_version(value: str, *, line_number: int) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ImportContractError(
            ImportErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            f"Line {line_number} has an unsupported schema version.",
            line_number=line_number,
        )
    return _validate_schema_version(int(value), line_number=line_number)


def _parse_csv_sequence_number(value: str, *, line_number: int) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ImportContractError(
            ImportErrorCode.SEQUENCE_NUMBER_INVALID,
            f"Line {line_number} has an invalid sequence number.",
            line_number=line_number,
        )
    return _validate_sequence_number(int(value), line_number=line_number)


def _validate_schema_version(value: Any, *, line_number: int) -> int:
    if type(value) is not int or value != LAYOUT_IMPORT_SCHEMA_VERSION:
        raise ImportContractError(
            ImportErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            f"Line {line_number} has an unsupported schema version.",
            line_number=line_number,
        )
    return value


def _validate_sequence_number(value: Any, *, line_number: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE_NUMBER:
        raise ImportContractError(
            ImportErrorCode.SEQUENCE_NUMBER_INVALID,
            f"Line {line_number} has an invalid sequence number.",
            line_number=line_number,
        )
    return value


def _validate_cells(value: Any, *, line_number: int) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(type(cell) is not int or not 1 <= cell <= MAX_SYMBOL_CODE for cell in value)
    ):
        raise ImportContractError(
            ImportErrorCode.CELLS_INVALID,
            f"Line {line_number} has invalid cells.",
            line_number=line_number,
        )
    return tuple(value)


class _DuplicateJsonFieldError(ValueError):
    pass


def _object_from_unique_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonFieldError(key)
        result[key] = value
    return result


def _validate_line_number(line_number: int) -> None:
    if line_number < 1:
        raise ValueError("line_number must be at least 1")
