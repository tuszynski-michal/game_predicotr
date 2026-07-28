"""Bounded physical-line streaming for layout-import-v1 files."""

from __future__ import annotations

import hashlib
from typing import BinaryIO, Final

from game_predictor_worker.imports.contracts import (
    ImportFileFormat,
    LayoutImportStreamBatch,
    StagedLayoutImportRow,
)
from game_predictor_worker.imports.errors import ImportContractError, ImportErrorCode
from game_predictor_worker.imports.parsing import (
    parse_import_record,
    validate_csv_header,
)

DEFAULT_IMPORT_BATCH_SIZE: Final = 1000
MAX_IMPORT_LINE_BYTES: Final = 1024 * 1024
INITIAL_IMPORT_PREFIX_CHAIN: Final = hashlib.sha256(
    b"game-predictor-layout-import-prefix-v1"
).hexdigest()
_MAX_ERROR_MESSAGE_LENGTH: Final = 500


def read_import_batch(
    source: BinaryIO,
    *,
    file_format: ImportFileFormat,
    byte_offset: int,
    line_number: int,
    prefix_chain: str = INITIAL_IMPORT_PREFIX_CHAIN,
    batch_size: int = DEFAULT_IMPORT_BATCH_SIZE,
    max_line_bytes: int = MAX_IMPORT_LINE_BYTES,
) -> LayoutImportStreamBatch:
    """Read at most one bounded batch starting after a durable file cursor."""

    if byte_offset < 0 or line_number < 0:
        raise ValueError("Import stream cursor cannot be negative.")
    if batch_size < 1 or max_line_bytes < 1:
        raise ValueError("Import stream limits must be positive.")
    _validate_prefix_chain(prefix_chain)
    source.seek(byte_offset)
    current_line = line_number
    current_offset = byte_offset
    current_chain = prefix_chain

    if file_format is ImportFileFormat.CSV and byte_offset == 0:
        raw_header, current_offset, too_large, line_digest = _read_physical_line(
            source,
            max_line_bytes=max_line_bytes,
        )
        current_chain = _extend_prefix_chain(current_chain, line_digest)
        current_line = 1
        if too_large:
            raise ImportContractError(
                ImportErrorCode.HEADER_INVALID,
                f"Line 1 exceeds the {max_line_bytes}-byte physical-line limit.",
                line_number=1,
            )
        validate_csv_header(raw_header, line_number=1)

    rows: list[StagedLayoutImportRow] = []
    while len(rows) < batch_size:
        raw_line, next_offset, too_large, line_digest = _read_physical_line(
            source,
            max_line_bytes=max_line_bytes,
        )
        if not raw_line and next_offset == current_offset:
            return LayoutImportStreamBatch(
                rows=tuple(rows),
                byte_offset=current_offset,
                line_number=current_line,
                prefix_chain=current_chain,
                reached_eof=True,
            )
        current_line += 1
        current_offset = next_offset
        current_chain = _extend_prefix_chain(current_chain, line_digest)
        if not too_large and not raw_line.strip():
            continue
        if too_large:
            rows.append(
                _error_row(
                    line_number=current_line,
                    byte_offset_end=current_offset,
                    code=ImportErrorCode.RECORD_INVALID.value,
                    message=(
                        f"Line {current_line} exceeds the "
                        f"{max_line_bytes}-byte physical-line limit."
                    ),
                )
            )
            continue
        try:
            record = parse_import_record(
                file_format,
                raw_line,
                line_number=current_line,
            )
        except ImportContractError as error:
            rows.append(
                _error_row(
                    line_number=current_line,
                    byte_offset_end=current_offset,
                    code=error.code.value,
                    message=str(error),
                )
            )
        else:
            rows.append(
                StagedLayoutImportRow(
                    line_number=current_line,
                    byte_offset_end=current_offset,
                    sequence_number=record.sequence_number,
                    cells=record.cells,
                    error_code=None,
                    error_message=None,
                )
            )

    return LayoutImportStreamBatch(
        rows=tuple(rows),
        byte_offset=current_offset,
        line_number=current_line,
        prefix_chain=current_chain,
        reached_eof=False,
    )


def calculate_import_prefix_chain(
    source: BinaryIO,
    *,
    byte_offset: int,
    max_line_bytes: int = MAX_IMPORT_LINE_BYTES,
) -> str:
    """Recompute the physical-line chain through one checkpoint boundary."""

    if byte_offset < 0 or max_line_bytes < 1:
        raise ValueError("Import prefix limits cannot be negative or zero.")
    source.seek(0)
    chain = INITIAL_IMPORT_PREFIX_CHAIN
    current_offset = 0
    while current_offset < byte_offset:
        raw_line, next_offset, _too_large, line_digest = _read_physical_line(
            source,
            max_line_bytes=max_line_bytes,
        )
        if not raw_line or next_offset <= current_offset or next_offset > byte_offset:
            raise ValueError("Import checkpoint is not on a physical-line boundary.")
        chain = _extend_prefix_chain(chain, line_digest)
        current_offset = next_offset
    return chain


def _read_physical_line(
    source: BinaryIO,
    *,
    max_line_bytes: int,
) -> tuple[bytes, int, bool, bytes]:
    digest = hashlib.sha256()
    raw_line = source.readline(max_line_bytes + 1)
    digest.update(raw_line)
    if len(raw_line) <= max_line_bytes:
        return raw_line, source.tell(), False, digest.digest()

    first_chunk = raw_line
    while raw_line and not raw_line.endswith(b"\n"):
        raw_line = source.readline(max_line_bytes + 1)
        digest.update(raw_line)
    return first_chunk, source.tell(), True, digest.digest()


def _extend_prefix_chain(prefix_chain: str, line_digest: bytes) -> str:
    return hashlib.sha256(bytes.fromhex(prefix_chain) + line_digest).hexdigest()


def _validate_prefix_chain(prefix_chain: str) -> None:
    if (
        len(prefix_chain) != 64
        or prefix_chain.lower() != prefix_chain
        or any(character not in "0123456789abcdef" for character in prefix_chain)
    ):
        raise ValueError("Import prefix chain must be a lowercase SHA-256 hex value.")


def _error_row(
    *,
    line_number: int,
    byte_offset_end: int,
    code: str,
    message: str,
) -> StagedLayoutImportRow:
    return StagedLayoutImportRow(
        line_number=line_number,
        byte_offset_end=byte_offset_end,
        sequence_number=None,
        cells=None,
        error_code=code,
        error_message=message[:_MAX_ERROR_MESSAGE_LENGTH],
    )
