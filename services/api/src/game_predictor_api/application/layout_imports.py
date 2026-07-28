"""Safe local-file boundary for manual layout import jobs."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final

from game_predictor_worker.imports import (
    LAYOUT_IMPORT_SCHEMA_VERSION,
    ImportContractError,
    ImportFileFormat,
    parse_jsonl_record,
    validate_csv_header,
)
from game_predictor_worker.imports.parsing import parse_csv_record

from game_predictor_api.domain.jobs import JobError, JobNotFoundError

_CHECKSUM_CHUNK_BYTES: Final = 1024 * 1024
_MAX_PREVIEW_LINE_BYTES: Final = 1024 * 1024
_MAX_SOURCE_PATH_LENGTH: Final = 500
_FORMAT_BY_SUFFIX: Final = {
    ".csv": ImportFileFormat.CSV,
    ".jsonl": ImportFileFormat.JSONL,
}


@dataclass(frozen=True, slots=True)
class InspectedLayoutImportSource:
    absolute_path: Path
    relative_path: str
    file_format: ImportFileFormat
    contract_version: int
    size_bytes: int
    checksum: str


class LayoutImportSourceInspector:
    """Resolve, preflight and attest a file below one configured root."""

    def __init__(self, import_root: Path, *, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._import_root = import_root
        self._max_bytes = max_bytes

    def inspect(
        self,
        source_path: str,
        *,
        contract_version: int,
    ) -> InspectedLayoutImportSource:
        if contract_version != LAYOUT_IMPORT_SCHEMA_VERSION:
            raise JobError(
                "UNSUPPORTED_LAYOUT_IMPORT_CONTRACT_VERSION",
                "Only layout import contract version 1 is supported.",
                details={"contractVersion": contract_version},
            )
        relative_path = _validate_relative_source_path(source_path)
        root = self._resolve_root()
        candidate = self._resolve_candidate(root, relative_path)
        file_format = _resolve_file_format(candidate)
        before = _stat_source(candidate)
        _validate_source_size(before.st_size, max_bytes=self._max_bytes)

        try:
            with candidate.open("rb") as source:
                opened_before = os.fstat(source.fileno())
                _require_same_source(before, opened_before)
                _validate_preview(source, file_format=file_format)
                source.seek(0)
                checksum = _sha256_stream(source)
                opened_after = os.fstat(source.fileno())
        except JobError:
            raise
        except OSError as error:
            raise JobError(
                "IMPORT_SOURCE_READ_FAILED",
                "The import source could not be read.",
            ) from error

        after = _stat_source(candidate)
        _require_same_source(opened_before, opened_after)
        _require_same_source(opened_after, after)
        _validate_source_size(after.st_size, max_bytes=self._max_bytes)
        return InspectedLayoutImportSource(
            absolute_path=candidate,
            relative_path=candidate.relative_to(root).as_posix(),
            file_format=file_format,
            contract_version=contract_version,
            size_bytes=after.st_size,
            checksum=checksum,
        )

    def _resolve_root(self) -> Path:
        try:
            root = self._import_root.resolve(strict=True)
        except OSError as error:
            raise JobError(
                "IMPORT_ROOT_UNAVAILABLE",
                "The configured import directory is unavailable.",
            ) from error
        if not root.is_dir():
            raise JobError(
                "IMPORT_ROOT_UNAVAILABLE",
                "The configured import path is not a directory.",
            )
        return root

    @staticmethod
    def _resolve_candidate(root: Path, relative_path: PurePosixPath) -> Path:
        unresolved = root.joinpath(*relative_path.parts)
        try:
            candidate = unresolved.resolve(strict=True)
        except FileNotFoundError as error:
            raise JobNotFoundError(
                "IMPORT_SOURCE_NOT_FOUND",
                "The import source does not exist.",
                details={"sourcePath": relative_path.as_posix()},
            ) from error
        except OSError as error:
            raise JobError(
                "IMPORT_SOURCE_UNAVAILABLE",
                "The import source cannot be resolved.",
                details={"sourcePath": relative_path.as_posix()},
            ) from error
        if not candidate.is_relative_to(root):
            raise JobError(
                "INVALID_IMPORT_SOURCE_PATH",
                "sourcePath must remain inside the configured import directory.",
            )
        if not candidate.is_file():
            raise JobError(
                "IMPORT_SOURCE_NOT_FILE",
                "The import source must be a regular file.",
                details={"sourcePath": relative_path.as_posix()},
            )
        return candidate


def _validate_relative_source_path(source_path: str) -> PurePosixPath:
    raw_parts = source_path.split("/")
    if (
        not source_path
        or len(source_path) > _MAX_SOURCE_PATH_LENGTH
        or source_path != source_path.strip()
        or "\\" in source_path
        or ":" in source_path
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise JobError(
            "INVALID_IMPORT_SOURCE_PATH",
            "sourcePath must be a relative POSIX path no longer than 500 characters.",
        )
    path = PurePosixPath(source_path)
    if path.is_absolute():
        raise JobError(
            "INVALID_IMPORT_SOURCE_PATH",
            "sourcePath must not contain absolute or parent-traversal segments.",
        )
    return path


def _resolve_file_format(candidate: Path) -> ImportFileFormat:
    file_format = _FORMAT_BY_SUFFIX.get(candidate.suffix.lower())
    if file_format is None:
        raise JobError(
            "IMPORT_SOURCE_FORMAT_UNSUPPORTED",
            "The import source must use the .csv or .jsonl extension.",
        )
    return file_format


def _stat_source(candidate: Path) -> os.stat_result:
    try:
        return candidate.stat()
    except OSError as error:
        raise JobError(
            "IMPORT_SOURCE_UNAVAILABLE",
            "The import source metadata could not be read.",
        ) from error


def _validate_source_size(size_bytes: int, *, max_bytes: int) -> None:
    if size_bytes == 0:
        raise JobError(
            "IMPORT_SOURCE_EMPTY",
            "The import source must not be empty.",
        )
    if size_bytes > max_bytes:
        raise JobError(
            "IMPORT_SOURCE_TOO_LARGE",
            "The import source exceeds the configured byte limit.",
            details={"maxBytes": max_bytes, "actualBytes": size_bytes},
        )


def _validate_preview(source: BinaryIO, *, file_format: ImportFileFormat) -> None:
    line_number = 1
    if file_format is ImportFileFormat.CSV:
        header = _read_bounded_line(source, line_number=line_number)
        _translate_contract_error(lambda: validate_csv_header(header))
        line_number += 1

    while True:
        line = _read_bounded_line(source, line_number=line_number)
        if not line:
            raise JobError(
                "IMPORT_SOURCE_NO_RECORDS",
                "The import source does not contain a layout record.",
            )
        if line.strip():
            break
        line_number += 1

    if file_format is ImportFileFormat.CSV:
        _translate_contract_error(lambda: parse_csv_record(line, line_number=line_number))
    else:
        _translate_contract_error(lambda: parse_jsonl_record(line, line_number=line_number))


def _read_bounded_line(source: BinaryIO, *, line_number: int) -> bytes:
    line = source.readline(_MAX_PREVIEW_LINE_BYTES + 1)
    if len(line) > _MAX_PREVIEW_LINE_BYTES:
        raise JobError(
            "IMPORT_SOURCE_LINE_TOO_LARGE",
            "An import preview line exceeds the 1 MiB limit.",
            details={"lineNumber": line_number, "maxBytes": _MAX_PREVIEW_LINE_BYTES},
        )
    return line


def _translate_contract_error(callback: Callable[[], object]) -> None:
    try:
        callback()
    except ImportContractError as error:
        raise JobError(
            error.code.value,
            str(error),
            details={"lineNumber": error.line_number},
        ) from error


def _sha256_stream(source: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(_CHECKSUM_CHUNK_BYTES):
        digest.update(chunk)
    return digest.hexdigest()


def _require_same_source(first: os.stat_result, second: os.stat_result) -> None:
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(first, field) != getattr(second, field) for field in identity):
        raise JobError(
            "IMPORT_SOURCE_CHANGED",
            "The import source changed while it was being inspected.",
        )
