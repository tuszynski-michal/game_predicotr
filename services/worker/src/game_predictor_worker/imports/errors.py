"""Stable errors for the public manual import file contract."""

from __future__ import annotations

from enum import StrEnum


class ImportErrorCode(StrEnum):
    FORMAT_UNSUPPORTED = "import_format_unsupported"
    ENCODING_INVALID = "import_encoding_invalid"
    ENCODING_BOM_FORBIDDEN = "import_encoding_bom_forbidden"
    HEADER_INVALID = "import_header_invalid"
    RECORD_INVALID = "import_record_invalid"
    SCHEMA_VERSION_UNSUPPORTED = "import_schema_version_unsupported"
    SEQUENCE_NUMBER_INVALID = "import_sequence_number_invalid"
    CELLS_INVALID = "import_cells_invalid"


class ImportContractError(ValueError):
    """A deterministic failure at the layout import format boundary."""

    def __init__(
        self,
        code: ImportErrorCode,
        message: str,
        *,
        line_number: int,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.line_number = line_number
