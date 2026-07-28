from __future__ import annotations

from io import BytesIO

import pytest
from game_predictor_worker.imports import ImportContractError, ImportFileFormat
from game_predictor_worker.imports.streaming import read_import_batch


def test_csv_streams_batches_with_physical_offsets_and_isolated_errors() -> None:
    content = (
        b"schema_version,sequence_number,cells\r\n"
        b'1,1,"[1,2,3]"\r\n'
        b"\r\n"
        b'1,nope,"[1,2,3]"\r\n'
        b'1,3,"[3,2,1]"\r\n'
    )
    source = BytesIO(content)

    first = read_import_batch(
        source,
        file_format=ImportFileFormat.CSV,
        byte_offset=0,
        line_number=0,
        batch_size=2,
    )

    assert first.reached_eof is False
    assert first.line_number == 4
    assert first.rows[0].line_number == 2
    assert first.rows[0].sequence_number == 1
    assert first.rows[0].cells == (1, 2, 3)
    assert first.rows[1].line_number == 4
    assert first.rows[1].error_code == "import_sequence_number_invalid"
    assert first.byte_offset == first.rows[1].byte_offset_end

    second = read_import_batch(
        source,
        file_format=ImportFileFormat.CSV,
        byte_offset=first.byte_offset,
        line_number=first.line_number,
        batch_size=2,
    )

    assert second.reached_eof is True
    assert [row.sequence_number for row in second.rows] == [3]
    assert second.byte_offset == len(content)
    assert second.line_number == 5


def test_jsonl_resume_from_offset_matches_single_pass() -> None:
    content = (
        b'{"schemaVersion":1,"sequenceNumber":1,"cells":[1]}\n'
        b"\n"
        b'{"schemaVersion":1,"sequenceNumber":2,"cells":[2]}\n'
        b'{"schemaVersion":1,"sequenceNumber":3,"cells":[3]}\n'
    )
    source = BytesIO(content)
    first = read_import_batch(
        source,
        file_format=ImportFileFormat.JSONL,
        byte_offset=0,
        line_number=0,
        batch_size=1,
    )
    resumed = read_import_batch(
        source,
        file_format=ImportFileFormat.JSONL,
        byte_offset=first.byte_offset,
        line_number=first.line_number,
        batch_size=10,
    )
    all_at_once = read_import_batch(
        BytesIO(content),
        file_format=ImportFileFormat.JSONL,
        byte_offset=0,
        line_number=0,
        batch_size=10,
    )

    assert first.rows + resumed.rows == all_at_once.rows
    assert resumed.reached_eof is True
    assert resumed.byte_offset == len(content)


def test_oversized_line_is_drained_without_losing_next_record() -> None:
    content = (
        b'{"schemaVersion":1,"sequenceNumber":1,"cells":['
        + b"1," * 30
        + b"1]}\n"
        + b'{"schemaVersion":1,"sequenceNumber":2,"cells":[2]}\n'
    )

    batch = read_import_batch(
        BytesIO(content),
        file_format=ImportFileFormat.JSONL,
        byte_offset=0,
        line_number=0,
        batch_size=10,
        max_line_bytes=64,
    )

    assert batch.reached_eof is True
    assert len(batch.rows) == 2
    assert batch.rows[0].error_code == "import_record_invalid"
    assert "physical-line limit" in (batch.rows[0].error_message or "")
    assert batch.rows[1].sequence_number == 2
    assert batch.byte_offset == len(content)


def test_invalid_csv_header_is_a_file_level_contract_error() -> None:
    with pytest.raises(ImportContractError) as captured:
        read_import_batch(
            BytesIO(b"wrong,header\n"),
            file_format=ImportFileFormat.CSV,
            byte_offset=0,
            line_number=0,
        )

    assert captured.value.code.value == "import_header_invalid"
    assert captured.value.line_number == 1


@pytest.mark.parametrize(
    ("byte_offset", "line_number", "batch_size", "max_line_bytes"),
    [
        (-1, 0, 1, 1),
        (0, -1, 1, 1),
        (0, 0, 0, 1),
        (0, 0, 1, 0),
    ],
)
def test_stream_rejects_invalid_cursor_or_limits(
    byte_offset: int,
    line_number: int,
    batch_size: int,
    max_line_bytes: int,
) -> None:
    with pytest.raises(ValueError):
        read_import_batch(
            BytesIO(b""),
            file_format=ImportFileFormat.JSONL,
            byte_offset=byte_offset,
            line_number=line_number,
            batch_size=batch_size,
            max_line_bytes=max_line_bytes,
        )
