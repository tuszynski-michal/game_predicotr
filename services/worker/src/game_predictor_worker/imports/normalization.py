"""Pure normalization of parser staging rows against one rules snapshot."""

from __future__ import annotations

from game_predictor_worker.domain.signature import encode_signature
from game_predictor_worker.imports.contracts import (
    LayoutImportNormalizationSource,
    NormalizedLayoutImportRow,
    RawLayoutImportRow,
)


def normalize_layout_import_row(
    row: RawLayoutImportRow,
    source: LayoutImportNormalizationSource,
) -> NormalizedLayoutImportRow:
    if row.error_code is not None:
        return NormalizedLayoutImportRow(
            line_number=row.line_number,
            sequence_number=None,
            cells=None,
            signature=None,
            error_code=row.error_code,
            error_message=row.error_message,
        )
    if row.sequence_number is None or row.cells is None:
        raise ValueError("A parser-success row must contain sequence number and cells.")

    expected_cell_count = source.rows * source.columns
    if len(row.cells) != expected_cell_count:
        return NormalizedLayoutImportRow(
            line_number=row.line_number,
            sequence_number=row.sequence_number,
            cells=row.cells,
            signature=None,
            error_code="import_cell_count_mismatch",
            error_message=(
                f"Layout contains {len(row.cells)} cells; expected {expected_cell_count}."
            ),
        )
    foreign_code = next(
        (code for code in row.cells if code not in source.allowed_mobile_codes),
        None,
    )
    if foreign_code is not None:
        return NormalizedLayoutImportRow(
            line_number=row.line_number,
            sequence_number=row.sequence_number,
            cells=row.cells,
            signature=None,
            error_code="import_symbol_not_in_rules",
            error_message=(
                f"Symbol code {foreign_code} is not active in the selected rules version."
            ),
        )
    return NormalizedLayoutImportRow(
        line_number=row.line_number,
        sequence_number=row.sequence_number,
        cells=row.cells,
        signature=encode_signature(row.cells, source.signature_cell_width),
        error_code=None,
        error_message=None,
    )
