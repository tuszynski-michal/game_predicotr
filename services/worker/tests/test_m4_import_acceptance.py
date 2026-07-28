from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from game_predictor_worker.imports.fixtures import (
    deterministic_cells,
    write_blocked_layout_import_fixture,
    write_layout_import_fixture,
)
from game_predictor_worker.imports.parsing import parse_jsonl_record


def test_deterministic_cells_are_stable_and_unique() -> None:
    assert deterministic_cells(1, seed=7) == deterministic_cells(1, seed=7)
    assert deterministic_cells(1, seed=7) != deterministic_cells(2, seed=7)
    assert len(deterministic_cells(1)) == 15
    assert all(1 <= value <= 11 for value in deterministic_cells(1))


def test_fixture_is_streaming_deterministic_and_has_expected_duplicates(
    tmp_path: Path,
) -> None:
    first = write_layout_import_fixture(
        tmp_path / "first.jsonl",
        layout_count=20,
        seed=39,
        duplicate_group_count=2,
    )
    second = write_layout_import_fixture(
        tmp_path / "second.jsonl",
        layout_count=20,
        seed=39,
        duplicate_group_count=2,
    )

    assert first.maximum_buffered_record_count == 1
    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()
    records = [
        parse_jsonl_record(line, line_number=index)
        for index, line in enumerate(first.path.read_bytes().splitlines(), start=1)
    ]
    assert [record.sequence_number for record in records] == list(range(1, 21))
    signatures = [record.cells for record in records]
    assert signatures[-2:] == signatures[:2]
    assert len(set(signatures)) == 18
    assert hashlib.sha256(first.path.read_bytes()).hexdigest() == first.sha256


def test_blocked_fixture_has_duplicate_and_missing_sequence(
    tmp_path: Path,
) -> None:
    result = write_blocked_layout_import_fixture(
        tmp_path / "blocked.jsonl",
        layout_count=5,
        seed=11,
    )
    records = [
        parse_jsonl_record(line, line_number=index)
        for index, line in enumerate(result.path.read_bytes().splitlines(), start=1)
    ]

    assert [record.sequence_number for record in records] == [1, 1, 3, 4, 5]
    assert len({record.sequence_number for record in records}) == 4


@pytest.mark.parametrize(
    ("layout_count", "duplicates"),
    [(0, 0), (3, 2), (10, -1)],
)
def test_fixture_rejects_invalid_bounds(
    tmp_path: Path,
    layout_count: int,
    duplicates: int,
) -> None:
    with pytest.raises(ValueError):
        write_layout_import_fixture(
            tmp_path / "invalid.jsonl",
            layout_count=layout_count,
            duplicate_group_count=duplicates,
        )
