from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from game_predictor_worker.imports import (
    ImportContractError,
    ImportErrorCode,
    ImportFileFormat,
    LayoutImportRecord,
    decode_import_line,
    parse_csv_record,
    parse_import_record,
    parse_jsonl_record,
    validate_csv_header,
)

EXAMPLES_DIRECTORY = Path(__file__).parents[3] / "examples" / "imports"


def _assert_contract_error(
    expected_code: ImportErrorCode,
    callback: Callable[[], object],
    *,
    line_number: int,
) -> None:
    with pytest.raises(ImportContractError) as captured:
        callback()
    assert captured.value.code is expected_code
    assert captured.value.line_number == line_number


def test_csv_v1_example_has_exact_header_and_valid_records() -> None:
    lines = (EXAMPLES_DIRECTORY / "layout-import-v1.csv").read_bytes().splitlines()

    validate_csv_header(lines[0])
    records = [
        parse_csv_record(line, line_number=line_number)
        for line_number, line in enumerate(lines[1:], start=2)
    ]

    assert records == [
        LayoutImportRecord(
            schema_version=1,
            sequence_number=1,
            cells=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1, 2, 3, 4, 5),
        ),
        LayoutImportRecord(
            schema_version=1,
            sequence_number=2,
            cells=(5, 4, 3, 2, 1, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1),
        ),
    ]


def test_jsonl_v1_example_has_one_valid_record_per_line() -> None:
    lines = (EXAMPLES_DIRECTORY / "layout-import-v1.jsonl").read_bytes().splitlines()

    records = [
        parse_jsonl_record(line, line_number=line_number)
        for line_number, line in enumerate(lines, start=1)
    ]

    assert [record.sequence_number for record in records] == [1, 2]
    assert all(len(record.cells) == 15 for record in records)


@pytest.mark.parametrize(
    "header",
    [
        b"sequence_number,schema_version,cells",
        b"schema_version,sequence_number",
        b"schema_version,sequence_number,cells,extra",
        b"Schema_Version,sequence_number,cells",
        b"",
    ],
)
def test_csv_header_is_exact(header: bytes) -> None:
    _assert_contract_error(
        ImportErrorCode.HEADER_INVALID,
        lambda: validate_csv_header(header),
        line_number=1,
    )


def test_utf8_bom_and_invalid_utf8_have_distinct_stable_errors() -> None:
    _assert_contract_error(
        ImportErrorCode.ENCODING_BOM_FORBIDDEN,
        lambda: decode_import_line(b"\xef\xbb\xbfdata", line_number=1),
        line_number=1,
    )
    _assert_contract_error(
        ImportErrorCode.ENCODING_INVALID,
        lambda: decode_import_line(b"\xff", line_number=7),
        line_number=7,
    )


@pytest.mark.parametrize(
    ("record", "expected_code"),
    [
        ('2,1,"[1,2,3]"', ImportErrorCode.SCHEMA_VERSION_UNSUPPORTED),
        ('x,1,"[1,2,3]"', ImportErrorCode.SCHEMA_VERSION_UNSUPPORTED),
        ('1,0,"[1,2,3]"', ImportErrorCode.SEQUENCE_NUMBER_INVALID),
        ('1,-1,"[1,2,3]"', ImportErrorCode.SEQUENCE_NUMBER_INVALID),
        ('1,true,"[1,2,3]"', ImportErrorCode.SEQUENCE_NUMBER_INVALID),
        ('1,1,"[]"', ImportErrorCode.CELLS_INVALID),
        ('1,1,"[1,0,3]"', ImportErrorCode.CELLS_INVALID),
        ('1,1,"[1,32768,3]"', ImportErrorCode.CELLS_INVALID),
        ('1,1,"[1,true,3]"', ImportErrorCode.CELLS_INVALID),
        ('1,1,"not-json"', ImportErrorCode.CELLS_INVALID),
        ("1,1", ImportErrorCode.RECORD_INVALID),
        ("", ImportErrorCode.RECORD_INVALID),
    ],
)
def test_csv_records_report_stable_contract_errors(
    record: str,
    expected_code: ImportErrorCode,
) -> None:
    _assert_contract_error(
        expected_code,
        lambda: parse_csv_record(record, line_number=9),
        line_number=9,
    )


@pytest.mark.parametrize(
    ("record", "expected_code"),
    [
        (
            '{"schemaVersion":2,"sequenceNumber":1,"cells":[1]}',
            ImportErrorCode.SCHEMA_VERSION_UNSUPPORTED,
        ),
        (
            '{"schemaVersion":"1","sequenceNumber":1,"cells":[1]}',
            ImportErrorCode.SCHEMA_VERSION_UNSUPPORTED,
        ),
        (
            '{"schemaVersion":1,"sequenceNumber":0,"cells":[1]}',
            ImportErrorCode.SEQUENCE_NUMBER_INVALID,
        ),
        (
            '{"schemaVersion":1,"sequenceNumber":true,"cells":[1]}',
            ImportErrorCode.SEQUENCE_NUMBER_INVALID,
        ),
        (
            '{"schemaVersion":1,"sequenceNumber":1,"cells":[]}',
            ImportErrorCode.CELLS_INVALID,
        ),
        (
            '{"schemaVersion":1,"sequenceNumber":1,"cells":[1],"extra":2}',
            ImportErrorCode.RECORD_INVALID,
        ),
        (
            '{"schemaVersion":1,"sequenceNumber":1}',
            ImportErrorCode.RECORD_INVALID,
        ),
        (
            '{"schemaVersion":1,"schemaVersion":1,"sequenceNumber":1,"cells":[1]}',
            ImportErrorCode.RECORD_INVALID,
        ),
        ("[]", ImportErrorCode.RECORD_INVALID),
        ("", ImportErrorCode.RECORD_INVALID),
        ("{", ImportErrorCode.RECORD_INVALID),
    ],
)
def test_jsonl_records_report_stable_contract_errors(
    record: str,
    expected_code: ImportErrorCode,
) -> None:
    _assert_contract_error(
        expected_code,
        lambda: parse_jsonl_record(record, line_number=11),
        line_number=11,
    )


def test_dispatch_supports_only_public_v1_formats() -> None:
    csv_record = parse_import_record(
        ImportFileFormat.CSV,
        '1,3,"[1,2]"',
        line_number=2,
    )
    jsonl_record = parse_import_record(
        "jsonl",
        '{"schemaVersion":1,"sequenceNumber":3,"cells":[1,2]}',
        line_number=2,
    )

    assert csv_record == jsonl_record
    _assert_contract_error(
        ImportErrorCode.FORMAT_UNSUPPORTED,
        lambda: parse_import_record("json", "{}", line_number=1),
        line_number=1,
    )


def test_contract_parser_does_not_apply_game_specific_dimensions_or_symbols() -> None:
    record = parse_jsonl_record(
        '{"schemaVersion":1,"sequenceNumber":1,"cells":[32767]}',
        line_number=1,
    )

    assert record.cells == (32767,)
