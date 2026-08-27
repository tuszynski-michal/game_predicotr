from __future__ import annotations

from game_predictor_api.storage.image_symbol_review_repository import (
    _iter_cell_insert_chunks,
)


def test_backfill_splits_two_hundred_boards_below_postgresql_parameter_limit() -> None:
    values = [{"cell_index": index} for index in range(200 * 15)]

    chunks = tuple(_iter_cell_insert_chunks(values))

    assert [len(chunk) for chunk in chunks] == [1_000, 1_000, 1_000]
    assert [value for chunk in chunks for value in chunk] == values
